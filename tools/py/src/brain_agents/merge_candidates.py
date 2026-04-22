"""T3 merge queue: list / accept / reject manual identity merge candidates.

Also provides :func:`sync_from_graph` which pulls cross-person
``shared_identifier`` pairs out of the F3 Kuzu view and enqueues any
that DuckDB has not already captured (via merge_candidates or
merge_log). This is the "graph → queue" belt-and-suspenders against
identifiers that slipped past the ingest-time auto-merge.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from brain_memory.structured import execute, fetch_one, query

from brain_agents.identity_resolver import merge_persons


# Fallback values if thresholds.yaml is missing keys. Kept identical to the
# shipped defaults in ``config/thresholds.yaml`` so behavior is stable when
# the YAML is stripped (e.g. in minimal test fixtures or legacy checkouts).
_GRAPH_KIND_SCORES_DEFAULT: dict[str, float] = {
    "phone": 0.95,
    "email": 0.92,
    "gmail_addr": 0.92,
    "wxid": 0.93,
    "wa_jid": 0.93,
    "ios_contact_row": 0.8,
}
_GRAPH_DEFAULT_SCORE_FALLBACK = 0.6
_AUTO_APPLY_MIN_SCORE_FALLBACK: float | None = None


@lru_cache(maxsize=1)
def _load_merge_queue_config() -> dict[str, Any]:
    """Read the `merge_queue` block from thresholds.yaml (cached, lazy).

    Returns a dict with at least ``graph_kind_scores`` (dict[str, float]),
    ``graph_default_score`` (float), and ``auto_apply_min_score``
    (float | None). Missing / malformed values fall back to the shipped
    defaults so callers never have to handle partial configs.
    """
    kind_scores: dict[str, float] = dict(_GRAPH_KIND_SCORES_DEFAULT)
    default_score = _GRAPH_DEFAULT_SCORE_FALLBACK
    default_min_apply: float | None = _AUTO_APPLY_MIN_SCORE_FALLBACK

    try:
        from brain_core.config import load_thresholds_config

        cfg = load_thresholds_config() or {}
        block = cfg.get("merge_queue") or {}

        raw_scores = block.get("graph_kind_scores")
        if isinstance(raw_scores, dict):
            for k, v in raw_scores.items():
                try:
                    kind_scores[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue

        raw_default = block.get("graph_default_score")
        if raw_default is not None:
            try:
                default_score = float(raw_default)
            except (TypeError, ValueError):
                pass

        raw_min = block.get("auto_apply_min_score")
        if raw_min is not None:
            try:
                parsed = float(raw_min)
                if 0 < parsed <= 1.0:
                    default_min_apply = parsed
                else:
                    # <=0 means "disabled" in the YAML contract; leave as None.
                    default_min_apply = None
            except (TypeError, ValueError):
                default_min_apply = None
    except Exception:
        # Config missing / malformed: fall through to defaults, never raise.
        pass

    return {
        "graph_kind_scores": kind_scores,
        "graph_default_score": default_score,
        "auto_apply_min_score": default_min_apply,
    }


def _graph_kind_scores() -> dict[str, float]:
    return _load_merge_queue_config()["graph_kind_scores"]


def _graph_default_score() -> float:
    return _load_merge_queue_config()["graph_default_score"]


def _config_auto_apply_min_score() -> float | None:
    return _load_merge_queue_config()["auto_apply_min_score"]


# Back-compat aliases. Some older callers / tests may import these; they now
# resolve to whatever ``thresholds.yaml`` currently holds (reloaded on import,
# cached after first access).
_GRAPH_KIND_SCORES = _graph_kind_scores()
_GRAPH_DEFAULT_SCORE = _graph_default_score()


def list_candidates(*, status: str | None = "pending", limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    st = (status or "pending").strip().lower()
    if st == "all":
        return query(
            """
            SELECT id, person_a, person_b, score, reason, status, detail_json, created_at
            FROM merge_candidates
            ORDER BY id DESC
            LIMIT ?
            """,
            [lim],
        )
    return query(
        """
        SELECT id, person_a, person_b, score, reason, status, detail_json, created_at
        FROM merge_candidates
        WHERE lower(status) = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        [st, lim],
    )


def reject_candidate(candidate_id: int) -> dict[str, Any]:
    rows = query(
        """
        UPDATE merge_candidates
        SET status = 'rejected'
        WHERE id = ? AND lower(status) = 'pending'
        RETURNING id
        """,
        [candidate_id],
    )
    n = len(rows)
    return {"status": "ok" if n else "noop", "merge_candidate_id": candidate_id, "updated": n}


def accept_candidate(candidate_id: int, *, kept_person_id: str | None = None) -> dict[str, Any]:
    row = fetch_one(
        "SELECT id, person_a, person_b, reason, detail_json, status FROM merge_candidates WHERE id = ?",
        [candidate_id],
    )
    if not row:
        return {"status": "error", "reason": "not_found", "merge_candidate_id": candidate_id}
    if str(row.get("status") or "").lower() != "pending":
        return {"status": "error", "reason": "not_pending", "merge_candidate_id": candidate_id, "status": row.get("status")}

    pa = str(row["person_a"])
    pb = str(row["person_b"])
    if kept_person_id:
        k = kept_person_id.strip()
        if k not in (pa, pb):
            return {
                "status": "error",
                "reason": "kept_not_in_pair",
                "merge_candidate_id": candidate_id,
                "person_a": pa,
                "person_b": pb,
                "kept_person_id": k,
            }
        kept = k
        absorbed = pb if kept == pa else pa
    else:
        kept, absorbed = sorted([pa, pb])

    merge_persons(
        kept,
        absorbed,
        "manual_merge_candidate",
        {"merge_candidate_id": candidate_id, "reason": row.get("reason")},
    )
    execute(
        "UPDATE merge_candidates SET status = 'accepted' WHERE id = ?",
        [candidate_id],
    )
    return {"status": "merged", "kept": kept, "absorbed": absorbed, "merge_candidate_id": candidate_id}


def enqueue_manual_candidate(
    person_a: str,
    person_b: str,
    *,
    reason: str,
    score: float = 1.0,
    auto_apply: bool = False,
) -> dict[str, Any]:
    """Manually queue a ``(person_a, person_b)`` merge for human review.

    B-ING-1.6 motivation: :func:`sync_from_graph` only surfaces pairs that
    already share an identifier in Kuzu. Plenty of real duplicates don't
    share ANY identifier (Cheng Wang's personal vs work email, Alice
    Klamer's phone-only vs email-only split) and the graph never finds
    them. This is the human-driven entry point.

    Guarantees:

    - Both ``person_a`` and ``person_b`` must exist in ``persons``.
    - Same id → error.
    - Pair is normalized to ``(smaller_id, larger_id)`` so (A,B) == (B,A).
    - If the pair is already present in ``merge_log`` OR any row of
      ``merge_candidates`` (any status), returns ``status="noop"`` with
      the existing row's id/status — no double-queue.
    - ``reason`` is stored prefixed as ``manual:<text>`` so audit queries
      can distinguish manual vs graph-derived entries.
    - ``auto_apply=True`` immediately calls :func:`accept_candidate`.

    Returns (on success): ``{"status": "queued" | "merged", ...}``.
    """
    if not person_a or not person_b:
        return {"status": "error", "reason": "missing_person_id"}
    pa = person_a.strip()
    pb = person_b.strip()
    if not pa or not pb:
        return {"status": "error", "reason": "missing_person_id"}
    if pa == pb:
        return {"status": "error", "reason": "same_person", "person_id": pa}

    for pid in (pa, pb):
        if fetch_one("SELECT 1 AS n FROM persons WHERE person_id = ?", [pid]) is None:
            return {"status": "error", "reason": "person_not_found", "person_id": pid}

    ca, cb = sorted([pa, pb])
    pair = (ca, cb)
    if pair in _already_handled_pairs():
        existing = fetch_one(
            "SELECT id, status FROM merge_candidates WHERE person_a = ? AND person_b = ? ORDER BY id DESC LIMIT 1",
            [ca, cb],
        )
        return {
            "status": "noop",
            "reason": "already_handled",
            "person_a": ca,
            "person_b": cb,
            "existing_merge_candidate_id": int(existing["id"]) if existing else None,
            "existing_status": (
                str(existing["status"]).lower() if existing and existing.get("status") is not None else None
            ),
        }

    raw_reason = (reason or "").strip() or "unspecified"
    try:
        s = float(score)
    except (TypeError, ValueError):
        s = 1.0
    s = max(0.0, min(1.0, s))

    cand = {
        "person_a": ca,
        "person_b": cb,
        "score": s,
        "reason": f"manual:{raw_reason}",
        "detail": {"source": "manual_cli", "raw_reason": raw_reason},
    }
    if auto_apply:
        out = _insert_and_accept(cand)
        return {
            "status": "merged" if out.get("accepted") else "pending_accept_failed",
            "person_a": ca,
            "person_b": cb,
            "merge_candidate_id": out.get("merge_candidate_id"),
            "kept": out.get("kept"),
            "absorbed": out.get("absorbed"),
            "error": out.get("error"),
        }
    mid = _insert_pending(cand)
    return {
        "status": "queued",
        "person_a": ca,
        "person_b": cb,
        "score": s,
        "reason": cand["reason"],
        "merge_candidate_id": mid,
    }


def _enumerate_shared_identifier_pairs() -> list[dict[str, Any]]:
    """Query the built Kuzu graph for cross-person shared-identifier pairs.

    Raises ``RuntimeError`` with ``"kuzu_missing:..."`` or
    ``"kuzu_not_built:..."`` when the view cannot be opened; callers
    should catch and convert into a ``{"status":"skipped"}`` result.

    Returns rows shaped ``{"person_a", "person_b", "kind", "value"}``
    with ``person_a < person_b`` guaranteed.
    """
    from brain_agents.graph_query import _open, _result_rows

    conn = _open()
    res = conn.execute(
        "MATCH (a:Person)-[:HasIdentifier]->(i:Identifier)<-[:HasIdentifier]-(b:Person) "
        "WHERE a.person_id < b.person_id "
        "RETURN a.person_id AS person_a, b.person_id AS person_b, "
        "       i.kind AS kind, i.value_normalized AS value"
    )
    return _result_rows(res)


def _already_handled_pairs() -> set[tuple[str, str]]:
    """Pairs that should NOT be re-queued: already merged OR already
    in ``merge_candidates`` (any status). Returned as canonical
    (lesser, greater) tuples.
    """
    handled: set[tuple[str, str]] = set()
    for r in query(
        "SELECT kept_person_id AS a, absorbed_person_id AS b FROM merge_log"
    ):
        a, b = str(r["a"]), str(r["b"])
        if a and b:
            handled.add(tuple(sorted([a, b])))  # type: ignore[arg-type]
    for r in query(
        "SELECT person_a AS a, person_b AS b FROM merge_candidates"
    ):
        a, b = str(r["a"]), str(r["b"])
        if a and b:
            handled.add(tuple(sorted([a, b])))  # type: ignore[arg-type]
    return handled


def sync_from_graph(
    *,
    dry_run: bool = False,
    max_inserts: int = 500,
    auto_apply_min_score: float | None = None,
) -> dict[str, Any]:
    """Pull fresh shared-identifier pairs from Kuzu and enqueue those
    DuckDB hasn't seen yet.

    When ``auto_apply_min_score`` is a float in ``(0, 1]`` and
    ``dry_run`` is False, any proposed pair whose score is **>=**
    the threshold is auto-merged through :func:`accept_candidate`
    (i.e. inserted as pending, immediately accepted, and
    absorbed->kept recorded in ``merge_log``). Lower-scoring pairs
    stay pending for human review.

    Per-kind scores, the default-kind score, and the default
    ``auto_apply_min_score`` (used when the caller passes ``None``)
    are read from ``config/thresholds.yaml → merge_queue`` at
    process start and cached. Callers passing an explicit
    ``auto_apply_min_score`` override the YAML default for that
    invocation only. (B-ING-2)

    In ``dry_run=True`` mode nothing is written, but the summary
    still reports how many pairs *would* auto-apply vs stay pending,
    so the weekly cron can surface the counts.

    Returns a summary dict with ``proposed`` (total candidate pairs),
    ``inserted`` (rows written as pending), ``auto_applied`` (rows
    written as pending AND immediately accepted/merged), and
    ``auto_apply_min_score`` (echoed for audit).

    Graceful ``{"status": "skipped", ...}`` when Kuzu is not
    installed or the graph has not been built.
    """
    try:
        rows = _enumerate_shared_identifier_pairs()
    except RuntimeError as exc:
        return {"status": "skipped", "reason": str(exc), "dry_run": bool(dry_run)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "skipped", "reason": f"runtime:{exc.__class__.__name__}", "dry_run": bool(dry_run)}

    # Explicit caller value wins; otherwise fall back to
    # ``thresholds.yaml → merge_queue.auto_apply_min_score`` (default 0.0 /
    # disabled in shipped config → same behavior as before B-ING-2).
    if auto_apply_min_score is None:
        effective_min_score = _config_auto_apply_min_score()
    else:
        effective_min_score = auto_apply_min_score
    threshold = _coerce_threshold(effective_min_score)

    kind_scores = _graph_kind_scores()
    default_score = _graph_default_score()

    handled = _already_handled_pairs()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        a = str(r.get("person_a") or "")
        b = str(r.get("person_b") or "")
        if not a or not b:
            continue
        pair = tuple(sorted([a, b]))
        if pair in handled:
            continue
        grouped.setdefault(pair, []).append({"kind": str(r.get("kind") or ""), "value": str(r.get("value") or "")})

    proposed: list[dict[str, Any]] = []
    for (a, b), evidence in grouped.items():
        kinds = sorted({e["kind"] for e in evidence if e["kind"]})
        score = max(
            (kind_scores.get(k, default_score) for k in kinds),
            default=default_score,
        )
        proposed.append(
            {
                "person_a": a,
                "person_b": b,
                "score": score,
                "reason": "graph:shared_identifier:" + ",".join(kinds) if kinds else "graph:shared_identifier",
                "detail": {"identifiers": evidence, "source": "kuzu"},
            }
        )

    proposed.sort(key=lambda r: (-r["score"], r["person_a"], r["person_b"]))

    # Bucket by threshold so both dry-run and apply paths see the
    # same split. ``would_auto_apply`` previews the auto-merge bucket
    # in dry-run.
    would_auto_apply: list[dict[str, Any]] = []
    would_stay_pending: list[dict[str, Any]] = []
    for cand in proposed:
        if threshold is not None and float(cand["score"]) >= threshold:
            would_auto_apply.append(cand)
        else:
            would_stay_pending.append(cand)

    inserted = 0
    auto_applied = 0
    auto_applied_samples: list[dict[str, Any]] = []
    if not dry_run:
        cap = max(0, int(max_inserts))
        budget = cap
        # Auto-apply bucket first so the safety cap favors high-confidence
        # pairs when the day's haul exceeds ``max_inserts``.
        for cand in would_auto_apply:
            if budget <= 0:
                break
            result = _insert_and_accept(cand)
            inserted += 1
            budget -= 1
            if result.get("accepted"):
                auto_applied += 1
                if len(auto_applied_samples) < 5:
                    auto_applied_samples.append(
                        {
                            "person_a": cand["person_a"],
                            "person_b": cand["person_b"],
                            "score": cand["score"],
                            "kept": result.get("kept"),
                            "absorbed": result.get("absorbed"),
                            "merge_candidate_id": result.get("merge_candidate_id"),
                        }
                    )
        for cand in would_stay_pending:
            if budget <= 0:
                break
            _insert_pending(cand)
            inserted += 1
            budget -= 1

    return {
        "status": "ok",
        "proposed": len(proposed),
        "inserted": inserted,
        "auto_applied": auto_applied,
        "auto_apply_min_score": threshold,
        "would_auto_apply": len(would_auto_apply),
        "would_stay_pending": len(would_stay_pending),
        "dry_run": bool(dry_run),
        "samples": proposed[:5],
        "auto_applied_samples": auto_applied_samples,
    }


def _coerce_threshold(val: float | None) -> float | None:
    """Normalize ``auto_apply_min_score``. Returns ``None`` when the
    caller did not opt in, or a float in ``(0, 1]`` otherwise.
    Non-positive or NaN values are treated as "not set" so callers
    get the safe default (no auto-merge) instead of silently merging
    everything.
    """
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if not (f > 0 and f <= 1.0):
        return None
    return f


def _insert_pending(cand: dict[str, Any]) -> int:
    """Insert a single proposed pair as ``status='pending'`` and
    return the new merge_candidates.id.
    """
    rows = query(
        "INSERT INTO merge_candidates (person_a, person_b, score, reason, status, detail_json) "
        "VALUES (?, ?, ?, ?, 'pending', ?) RETURNING id",
        [
            cand["person_a"],
            cand["person_b"],
            float(cand["score"]),
            cand["reason"],
            json.dumps(cand["detail"], ensure_ascii=False),
        ],
    )
    return int(rows[0]["id"]) if rows else 0


def _insert_and_accept(cand: dict[str, Any]) -> dict[str, Any]:
    """Insert as pending AND immediately accept (merge). Returns a
    dict with ``merge_candidate_id``, ``accepted`` (bool),
    ``kept``, ``absorbed``. If the merge step fails for any reason
    (e.g. one of the person_ids has since been absorbed), the row
    stays pending and a human can sort it out — the insert is not
    rolled back so the audit trail survives.
    """
    candidate_id = _insert_pending(cand)
    try:
        accept_out = accept_candidate(candidate_id)
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "merge_candidate_id": candidate_id,
            "accepted": False,
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    accepted = accept_out.get("status") == "merged"
    return {
        "merge_candidate_id": candidate_id,
        "accepted": accepted,
        "kept": accept_out.get("kept"),
        "absorbed": accept_out.get("absorbed"),
        "accept_status": accept_out.get("status"),
        "accept_reason": accept_out.get("reason"),
    }


def enqueue_stale_merge_candidates_for_cloud(*, dry_run: bool = True) -> dict[str, Any]:
    """Enqueue ``merge-t3-review`` for ``merge_candidates`` rows still ``pending`` and older than
    ``cloud_queue.merge_t3_pending_days`` in ``thresholds.yaml`` (default 14). Skips candidate ids
    already present in a pending ``cloud_queue`` row.
    """
    from brain_agents.cloud_queue import enqueue
    from brain_core.config import load_thresholds_config

    cfg = (load_thresholds_config() or {}).get("cloud_queue") or {}
    days = int(cfg.get("merge_t3_pending_days") or 14)
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

    rows = query(
        """
        SELECT id, person_a, person_b, score, reason, created_at
        FROM merge_candidates
        WHERE lower(trim(status)) = 'pending' AND created_at < ?
        ORDER BY id ASC
        """,
        [cutoff],
    )
    pending_rows = query(
        """
        SELECT payload_json FROM cloud_queue
        WHERE status = 'pending' AND task_kind = 'merge-t3-review'
        """
    )
    seen_mc: set[int] = set()
    for pr in pending_rows:
        try:
            j = json.loads(pr["payload_json"])
            mid = j.get("merge_candidate_id")
            if mid is not None:
                seen_mc.add(int(mid))
        except Exception:
            continue

    enqueued = 0
    skipped_dup = 0
    sample: list[dict[str, Any]] = []
    for r in rows:
        mid = int(r["id"])
        if mid in seen_mc:
            skipped_dup += 1
            continue
        payload = {
            "merge_candidate_id": mid,
            "person_a": r["person_a"],
            "person_b": r["person_b"],
            "reason": str(r.get("reason") or ""),
            "score": float(r["score"]) if r.get("score") is not None else None,
        }
        if dry_run:
            enqueued += 1
            if len(sample) < 15:
                sample.append(payload)
            continue
        enqueue("merge-t3-review", payload)
        enqueued += 1
        seen_mc.add(mid)

    return {
        "status": "dry_run" if dry_run else "ok",
        "days_threshold": days,
        "cutoff_utc": cutoff.isoformat(),
        "pending_candidates_found": len(rows),
        "enqueued": enqueued,
        "skipped_already_queued": skipped_dup,
        "sample": sample,
    }
