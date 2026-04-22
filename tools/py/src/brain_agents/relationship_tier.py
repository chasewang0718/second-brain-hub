"""Relationship tier + cadence alarm (Phase A6 Sprint 4).

Storage model:

- **Authoritative tier** lives in ``person_facts`` under
  ``key='relationship_tier'`` with ``value_json`` being a JSON-encoded
  string ∈ ``{"inner","close","working","acquaintance","dormant"}``. Using
  ``person_facts`` gives us bi-temporal history for free: you can always
  answer "was she inner in 2026-Q1" via ``get_fact(..., at=...)``.
- **AI suggestions** live in ``person_insights`` with
  ``insight_type='tier_suggestion'`` and use the same ``superseded_by``
  versioning chain as ``topics_30d`` / ``weekly_digest``. Suggestions are
  **never** auto-promoted; human-set facts always win. ``suggest_tier_all``
  writes suggestions but does not touch ``person_facts``.

Cadence model:

- Each tier maps to a target "max days since last contact" via
  ``config/thresholds.yaml → people_cadence``. ``dormancy_days`` (from
  ``person_metrics``) over the target → flagged as overdue. ``null``
  disables the alarm (used for ``dormant``).

Design guardrails:

- Tier values are validated against :data:`ALLOWED_TIERS` on every write.
- ``list_overdue_by_tier`` does NOT consider people without a tier fact:
  those fall through to the legacy flat 45-day alert path
  (:func:`brain_agents.digest.generate_relationship_alerts` base behavior).
  This keeps A6 Sprint 4 strictly additive over A5.
"""

from __future__ import annotations

import json
from typing import Any

from brain_agents.person_facts import add_fact, get_fact
from brain_memory.structured import query, transaction

ALLOWED_TIERS = ("inner", "close", "working", "acquaintance", "dormant")
TIER_FACT_KEY = "relationship_tier"
INSIGHT_TIER_SUGGEST = "tier_suggestion"

# Hard-coded safety net: if ``config/thresholds.yaml`` is missing
# ``people_cadence:`` entirely, or YAML parsing fails, we still want
# ``list_overdue_by_tier`` to return something reasonable.
_DEFAULT_CADENCE_DAYS: dict[str, int | None] = {
    "inner": 14,
    "close": 30,
    "working": 60,
    "acquaintance": 120,
    "dormant": None,
}


def _coerce_tier(tier: str) -> str:
    s = str(tier or "").strip().lower()
    if s not in ALLOWED_TIERS:
        raise ValueError(
            f"unknown tier: {tier!r} (allowed: {', '.join(ALLOWED_TIERS)})"
        )
    return s


def load_cadence_config() -> dict[str, int | None]:
    """Read ``people_cadence`` from ``thresholds.yaml``.

    Falls back to :data:`_DEFAULT_CADENCE_DAYS` on:
    - YAML parse / file-not-found errors,
    - missing ``people_cadence`` section,
    - per-tier values that aren't ``int`` / ``None``.

    Known-good entries override defaults; unknown/garbage entries are
    silently ignored (safer than crashing the daily digest over a typo).
    """
    merged: dict[str, int | None] = dict(_DEFAULT_CADENCE_DAYS)
    try:
        from brain_core.config import load_thresholds_config

        data = load_thresholds_config()
    except Exception:  # pragma: no cover - defensive, covered via fallback
        return merged

    section = data.get("people_cadence") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return merged

    for tier_name in ALLOWED_TIERS:
        if tier_name not in section:
            continue
        raw = section[tier_name]
        if raw is None:
            merged[tier_name] = None
            continue
        try:
            days = int(raw)
        except (TypeError, ValueError):
            continue
        if days <= 0:
            merged[tier_name] = None
        else:
            merged[tier_name] = days
    return merged


def set_tier(
    person_id: str,
    tier: str,
    *,
    note: str = "",
    source_kind: str = "manual",
    confidence: float = 1.0,
) -> dict[str, Any]:
    """Write an authoritative tier fact. Bi-temporal: old fact auto-closes.

    ``note`` is stored for provenance on the fact row via
    :func:`brain_agents.person_facts.add_fact`'s ``value_json`` path — we
    JSON-encode a string (just the tier name) so queries stay simple, and
    if a caller wants to attach reasoning they should fall back to the
    ``tier_suggestion`` insight path instead.
    """
    pid = (person_id or "").strip()
    if not pid:
        raise ValueError("person_id is required")
    t = _coerce_tier(tier)
    result = add_fact(
        pid,
        TIER_FACT_KEY,
        value=t,
        confidence=float(confidence),
        source_kind=source_kind,
    )
    result["tier"] = t
    result["note"] = note
    return result


def get_tier(person_id: str) -> str | None:
    """Return the current tier string, or ``None`` if no fact has been set."""
    pid = (person_id or "").strip()
    if not pid:
        return None
    row = get_fact(pid, TIER_FACT_KEY)
    if not row:
        return None
    raw = row.get("value_json")
    if raw is None:
        return None
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(decoded, str) and decoded.strip().lower() in ALLOWED_TIERS:
        return decoded.strip().lower()
    return None


def list_tiers(
    *,
    tier: str | None = None,
    include_history: bool = False,
) -> list[dict[str, Any]]:
    """Return current (or historical) tier rows across all people.

    Shape: ``[{person_id, tier, confidence, source_kind, valid_from, ...}]``.

    ``include_history=False`` (default): only currently-valid facts
    (``valid_to IS NULL``). ``include_history=True``: all tier rows, ordered
    by person_id, valid_from DESC.
    """
    if include_history:
        rows = query(
            """
            SELECT id, person_id, key, value_json, valid_from, valid_to,
                   confidence, source_kind, source_interaction_id
            FROM person_facts
            WHERE key = ?
            ORDER BY person_id, valid_from DESC, id DESC
            """,
            [TIER_FACT_KEY],
        )
    else:
        rows = query(
            """
            SELECT id, person_id, key, value_json, valid_from, valid_to,
                   confidence, source_kind, source_interaction_id
            FROM person_facts
            WHERE key = ? AND valid_to IS NULL
            ORDER BY person_id
            """,
            [TIER_FACT_KEY],
        )

    wanted = _coerce_tier(tier) if tier else None
    out: list[dict[str, Any]] = []
    for r in rows:
        raw = r.get("value_json")
        try:
            decoded = json.loads(raw) if raw is not None else None
        except json.JSONDecodeError:
            decoded = None
        if not isinstance(decoded, str):
            continue
        t = decoded.strip().lower()
        if t not in ALLOWED_TIERS:
            continue
        if wanted and t != wanted:
            continue
        out.append(
            {
                "person_id": r.get("person_id"),
                "tier": t,
                "confidence": r.get("confidence"),
                "source_kind": r.get("source_kind"),
                "valid_from": r.get("valid_from"),
                "valid_to": r.get("valid_to"),
                "fact_id": r.get("id"),
            }
        )
    return out


# --- Heuristic suggester ----------------------------------------------------


def _suggest_from_metrics(metrics: dict[str, Any] | None) -> tuple[str, float, str]:
    """Deterministic fallback suggestor. Returns (tier, confidence, reason).

    The thresholds here are intentionally conservative — AI only hints,
    human always decides. Tuning guidance is in the acceptance doc.
    """
    if not metrics:
        return ("acquaintance", 0.3, "no metrics available")
    i30 = int(metrics.get("interactions_30d") or 0)
    i90 = int(metrics.get("interactions_90d") or 0)
    dormancy = metrics.get("dormancy_days")
    dormancy_v = int(dormancy) if dormancy is not None else 9999

    if dormancy_v > 365:
        return ("dormant", 0.7, f"dormancy_days={dormancy_v} > 365")
    if i30 >= 20 and i90 >= 50:
        return ("inner", 0.7, f"interactions_30d={i30}, interactions_90d={i90}")
    if i30 >= 5 and i90 >= 15:
        return ("close", 0.6, f"interactions_30d={i30}, interactions_90d={i90}")
    if i30 >= 1 or i90 >= 5:
        return ("working", 0.5, f"interactions_30d={i30}, interactions_90d={i90}")
    if dormancy_v > 180:
        return ("dormant", 0.5, f"dormancy_days={dormancy_v} > 180")
    return ("acquaintance", 0.4, f"interactions_30d={i30}, interactions_90d={i90}")


def _fetch_metrics(person_id: str) -> dict[str, Any] | None:
    rows = query(
        """
        SELECT interactions_all, interactions_30d, interactions_90d,
               dormancy_days, last_seen_utc, first_seen_utc
        FROM person_metrics
        WHERE person_id = ?
        LIMIT 1
        """,
        [person_id],
    )
    return rows[0] if rows else None


def _latest_current_suggestion(person_id: str) -> dict[str, Any] | None:
    rows = query(
        """
        SELECT id, body, detail_json, created_at
        FROM person_insights
        WHERE person_id = ?
          AND insight_type = ?
          AND superseded_by IS NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        [person_id, INSIGHT_TIER_SUGGEST],
    )
    return rows[0] if rows else None


def _insert_suggestion_and_supersede(
    *,
    person_id: str,
    suggested_tier: str,
    confidence: float,
    reason: str,
    prior_id: int | None,
    source_kind: str,
) -> int:
    detail = {
        "suggested_tier": suggested_tier,
        "confidence": float(confidence),
        "reason": reason,
        "source_kind": source_kind,
    }
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO person_insights
              (person_id, insight_type, body, detail_json, source_kind)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                person_id,
                INSIGHT_TIER_SUGGEST,
                suggested_tier,
                json.dumps(detail, ensure_ascii=False),
                source_kind,
            ],
        )
        row = conn.execute(
            """
            SELECT id FROM person_insights
            WHERE person_id = ? AND insight_type = ? AND superseded_by IS NULL
            ORDER BY id DESC LIMIT 1
            """,
            [person_id, INSIGHT_TIER_SUGGEST],
        ).fetchone()
        new_id = int(row[0]) if row else 0
        if prior_id is not None and new_id != prior_id:
            conn.execute(
                "UPDATE person_insights SET superseded_by = ? WHERE id = ?",
                [new_id, prior_id],
            )
    return new_id


def suggest_tier(person_id: str, *, apply_as_fact: bool = False) -> dict[str, Any]:
    """Suggest a tier for one person based on metrics. Writes an insight
    row regardless; only touches ``person_facts`` if ``apply_as_fact=True``.

    Returns ``{person_id, suggested_tier, confidence, reason, current_tier,
    insight_id, prior_insight_id, applied_as_fact}``.
    """
    pid = (person_id or "").strip()
    if not pid:
        raise ValueError("person_id is required")

    metrics = _fetch_metrics(pid)
    suggested, confidence, reason = _suggest_from_metrics(metrics)
    current = get_tier(pid)

    prior = _latest_current_suggestion(pid)
    new_id = _insert_suggestion_and_supersede(
        person_id=pid,
        suggested_tier=suggested,
        confidence=confidence,
        reason=reason,
        prior_id=int(prior["id"]) if prior else None,
        source_kind="heuristic",
    )

    applied = False
    if apply_as_fact and current is None:
        # Only auto-apply when there's NO human-set fact yet. Never overwrite
        # human input; that's the single hard rule of this module.
        set_tier(pid, suggested, source_kind="ai_suggestion", confidence=float(confidence))
        applied = True

    return {
        "person_id": pid,
        "suggested_tier": suggested,
        "confidence": confidence,
        "reason": reason,
        "current_tier": current,
        "insight_id": new_id,
        "prior_insight_id": int(prior["id"]) if prior else None,
        "applied_as_fact": applied,
    }


def suggest_tier_all(
    *,
    min_interactions_all: int = 1,
    max_persons: int = 2000,
    apply_as_fact: bool = False,
) -> dict[str, Any]:
    """Suggest for every person who has at least ``min_interactions_all``
    interactions in ``person_metrics``."""
    rows = query(
        """
        SELECT person_id
        FROM person_metrics
        WHERE COALESCE(interactions_all, 0) >= ?
        ORDER BY COALESCE(interactions_30d, 0) DESC,
                 COALESCE(interactions_all, 0) DESC
        LIMIT ?
        """,
        [int(min_interactions_all), int(max_persons)],
    )
    scanned = 0
    applied = 0
    by_tier: dict[str, int] = {t: 0 for t in ALLOWED_TIERS}
    errors: list[dict[str, str]] = []
    samples: list[dict[str, Any]] = []
    for r in rows:
        pid = str(r.get("person_id") or "").strip()
        if not pid:
            continue
        scanned += 1
        try:
            res = suggest_tier(pid, apply_as_fact=apply_as_fact)
        except Exception as exc:
            errors.append({"person_id": pid, "error": str(exc)[:240]})
            continue
        by_tier[res["suggested_tier"]] = by_tier.get(res["suggested_tier"], 0) + 1
        if res["applied_as_fact"]:
            applied += 1
        if len(samples) < 20:
            samples.append(res)
    return {
        "status": "ok",
        "scanned": scanned,
        "applied_as_fact": applied,
        "by_tier": by_tier,
        "errors": errors,
        "samples": samples,
    }


# --- Overdue / cadence alarm ------------------------------------------------


def list_overdue_by_tier(
    *,
    tiers: list[str] | None = None,
    cadence: dict[str, int | None] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Group overdue people by tier.

    A person is "overdue for their tier" iff:
    - they have a current ``relationship_tier`` fact,
    - the tier has a non-null ``cadence_target_days`` in config,
    - ``person_metrics.dormancy_days`` is defined and exceeds the target.

    Returns ``{tier: [{person_id, primary_name, dormancy_days,
    cadence_target_days, tier}, ...]}``. People without a tier fact are
    excluded (they fall through to legacy flat-threshold alerts).
    """
    cadence_map = cadence if cadence is not None else load_cadence_config()
    wanted = set(_coerce_tier(t) for t in tiers) if tiers else set(ALLOWED_TIERS)

    tier_rows = list_tiers()
    out: dict[str, list[dict[str, Any]]] = {t: [] for t in wanted}
    if not tier_rows:
        return out

    person_ids = [r["person_id"] for r in tier_rows if r.get("person_id")]
    if not person_ids:
        return out

    placeholders = ",".join(["?"] * len(person_ids))
    metric_rows = query(
        f"""
        SELECT m.person_id,
               m.dormancy_days,
               m.last_seen_utc,
               m.interactions_30d,
               COALESCE(p.primary_name, '') AS primary_name
        FROM person_metrics m
        LEFT JOIN persons p ON p.person_id = m.person_id
        WHERE m.person_id IN ({placeholders})
        """,
        person_ids,
    )
    metrics_by_id = {r["person_id"]: r for r in metric_rows}

    for tr in tier_rows:
        t = tr["tier"]
        if t not in wanted:
            continue
        target = cadence_map.get(t)
        if target is None:
            continue
        pid = tr["person_id"]
        m = metrics_by_id.get(pid)
        if not m:
            continue
        dormancy = m.get("dormancy_days")
        if dormancy is None:
            continue
        if int(dormancy) <= int(target):
            continue
        out.setdefault(t, []).append(
            {
                "person_id": pid,
                "primary_name": m.get("primary_name") or "",
                "tier": t,
                "dormancy_days": int(dormancy),
                "cadence_target_days": int(target),
                "days_overdue": int(dormancy) - int(target),
                "last_seen_utc": m.get("last_seen_utc"),
                "interactions_30d": int(m.get("interactions_30d") or 0),
            }
        )

    for t in out:
        out[t].sort(key=lambda x: -x["days_overdue"])
    return out


def get_tier_suggestion(person_id: str) -> dict[str, Any] | None:
    """Return the current (``superseded_by IS NULL``) tier suggestion
    decorated with its parsed detail_json, or ``None``."""
    pid = (person_id or "").strip()
    if not pid:
        return None
    row = _latest_current_suggestion(pid)
    if not row:
        return None
    try:
        detail = json.loads(row.get("detail_json") or "{}")
    except json.JSONDecodeError:
        detail = {}
    return {
        "id": int(row.get("id") or 0),
        "suggested_tier": str(row.get("body") or ""),
        "created_at": row.get("created_at"),
        "detail": detail,
    }
