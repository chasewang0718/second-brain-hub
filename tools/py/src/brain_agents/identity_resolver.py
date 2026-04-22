"""Map channel-specific identifiers (phone, email, wxid, …) to persons + merge tiers T1/T2/T3."""

from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache
from typing import Any

from brain_memory.structured import execute, fetch_one, query

try:  # pragma: no cover - always available in prod (pinned in pyproject)
    import phonenumbers as _pn
    from phonenumbers import PhoneNumberFormat as _PNFormat

    _HAS_PHONENUMBERS = True
except ImportError:  # pragma: no cover
    _HAS_PHONENUMBERS = False

# Mainland China mobile, national significant number (11 digits, leading 1).
# Tuned to avoid treating NANP domestic numbers like 14155550123 as CN (collision with coarse 1[3-9]… rules).
_CN_DOMESTIC_MOBILE = re.compile(
    r"^1(?:3\d{9}|4[5-9]\d{8}|5[0-35-9]\d{8}|6[2567]\d{8}|7[0-8]\d{8}|8\d{9}|9[0-35-9]\d{8})$"
)


@lru_cache(maxsize=1)
def _default_phone_region() -> str | None:
    """Read `identity.phone_default_region` from thresholds.yaml (cached, lazy)."""
    try:
        from brain_core.config import load_thresholds_config

        cfg = load_thresholds_config() or {}
        region = (cfg.get("identity") or {}).get("phone_default_region")
        if isinstance(region, str) and region.strip():
            return region.strip().upper()
    except Exception:
        # Config missing / malformed: fall back to region-less parsing.
        return None
    return None


def normalize_phone_digits(raw: str, *, default_region: str | None = None) -> str:
    """Normalize phone for matching: digits-only canonical E.164 body (no leading ``+``).

    Parsing order:

    1. Bare CN domestic mobile (11 digits matching ``_CN_DOMESTIC_MOBILE``) and
       the ``0086…`` IDD variant are short-circuited to ``86…`` — this preserves
       the CN-first semantics regardless of ``default_region``.
    2. libphonenumber (``phonenumbers``) is asked to parse the raw string with
       ``default_region`` as context (letting it pick up NL ``06…`` / UK ``07…``
       / DE ``01…`` etc. without a ``+`` prefix). On success the E.164 form is
       returned with the leading ``+`` stripped.
    3. Last resort: return digits-only (``re.sub(\\D, "")``), matching pre-0.1
       behavior for exotic inputs.

    ``default_region`` is an ISO 3166-1 alpha-2 code (e.g. ``"NL"``). When
    ``None`` (default), falls back to ``thresholds.yaml → identity.phone_default_region``.
    """
    s = (raw or "").strip()
    if not s:
        return ""

    # Step 1: CN short-circuits (keep existing semantics / tests stable).
    d = re.sub(r"\D", "", s)
    if d.startswith("0086"):
        d = "86" + d[4:]
        if len(d) == 13 and d.startswith("86") and _CN_DOMESTIC_MOBILE.match(d[2:]):
            return d
        # Still a CN IDD-prefixed number, but not a recognized mobile pattern; return as-is.
        return d
    if _CN_DOMESTIC_MOBILE.match(d):
        return "86" + d

    # Step 2: libphonenumber with region context.
    if _HAS_PHONENUMBERS:
        region = default_region if default_region is not None else _default_phone_region()
        try:
            parsed = _pn.parse(s, region)
            if _pn.is_valid_number(parsed) or _pn.is_possible_number(parsed):
                e164 = _pn.format_number(parsed, _PNFormat.E164)
                if e164.startswith("+"):
                    return e164[1:]
                return e164
        except _pn.phonenumberutil.NumberParseException:
            pass  # fall through

    # Step 3: legacy digits-only fallback.
    return d


def normalize_value(kind: str, value: str, *, default_region: str | None = None) -> str:
    k = kind.lower()
    raw = value.strip()
    if k in ("email", "gmail_addr"):
        return raw.lower()
    if k == "phone":
        return normalize_phone_digits(raw, default_region=default_region)
    return raw.lower()


def _repair_identifier_kind_group(
    kinds_lower: tuple[str, ...],
    *,
    dry_run: bool,
    reason_prefix: str,
) -> dict[str, Any]:
    """
    Rewrite person_identifiers rows whose lower(kind) is in kinds_lower.

    Collision / duplicate semantics match repair_phone_identifiers (T3 on cross-person conflict).
    """
    if not kinds_lower:
        return {
            "rows_scanned": 0,
            "skipped_unchanged": 0,
            "updated": 0,
            "deleted_duplicate": 0,
            "merge_candidates": 0,
            "dry_run": dry_run,
            "status": "dry_run" if dry_run else "ok",
        }
    ph = ",".join(["?"] * len(kinds_lower))
    rows = query(
        f"""
        SELECT id, person_id, kind, value_normalized, value_original
        FROM person_identifiers
        WHERE lower(kind) IN ({ph})
        ORDER BY id
        """,
        list(kinds_lower),
    )
    stats: dict[str, Any] = {
        "rows_scanned": 0,
        "skipped_unchanged": 0,
        "updated": 0,
        "deleted_duplicate": 0,
        "merge_candidates": 0,
        "merge_candidate_collisions": 0,
        "merge_candidate_skipped_existing": 0,
        "dry_run": dry_run,
    }
    # B-ING-1.10: pair-level dedupe within this run. Under non-dry-run the DB
    # existence check is authoritative, but under dry-run (no commits) we also
    # need to remember pairs we've seen earlier in the same loop to avoid
    # double-counting "would enqueue" for several colliding rows on the same pair.
    seen_pairs: set[tuple[str, str]] = set()

    for r in rows:
        stats["rows_scanned"] += 1
        oid = int(r["id"])
        pid = str(r["person_id"])
        kind_k = str(r["kind"]).lower()
        old_norm = str(r["value_normalized"] or "")
        original = r["value_original"]
        seed = str(original).strip() if original else old_norm
        new_norm = normalize_value(kind_k, seed)
        if new_norm == old_norm:
            stats["skipped_unchanged"] += 1
            continue

        dup_same = query(
            """
            SELECT id FROM person_identifiers
            WHERE person_id = ? AND lower(kind) = ? AND value_normalized = ? AND id <> ?
            """,
            [pid, kind_k, new_norm, oid],
        )
        if dup_same:
            if not dry_run:
                execute("DELETE FROM person_identifiers WHERE id = ?", [oid])
            stats["deleted_duplicate"] += 1
            continue

        others = query(
            """
            SELECT DISTINCT person_id FROM person_identifiers
            WHERE lower(kind) = ? AND value_normalized = ? AND person_id <> ?
            """,
            [kind_k, new_norm, pid],
        )
        opids = [str(x["person_id"]) for x in others]
        if opids:
            ambiguous = len(opids) > 1
            other = opids[0]
            pair = tuple(sorted([pid, other]))
            stats["merge_candidate_collisions"] += 1
            if pair in seen_pairs:
                stats["merge_candidate_skipped_existing"] += 1
                continue
            seen_pairs.add(pair)
            detail: dict[str, Any] = {
                "kind": kind_k,
                "new_norm": new_norm,
                "old_normalized": old_norm,
                "row_id": oid,
            }
            if ambiguous:
                detail["owners"] = opids
            enqueued = _enqueue_merge_candidate(
                pid,
                other,
                0.45 if ambiguous else 0.6,
                f"{reason_prefix}_repair_{'ambiguous' if ambiguous else 'collision'}",
                detail,
                dry_run=dry_run,
            )
            if enqueued:
                stats["merge_candidates"] += 1
            else:
                stats["merge_candidate_skipped_existing"] += 1
            continue

        if not dry_run:
            execute(
                "UPDATE person_identifiers SET value_normalized = ? WHERE id = ?",
                [new_norm, oid],
            )
        stats["updated"] += 1

    stats["status"] = "dry_run" if dry_run else "ok"
    return stats


def repair_phone_identifiers(*, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite phone rows (compat wrapper)."""
    return _repair_identifier_kind_group(("phone",), dry_run=dry_run, reason_prefix="phone")


def repair_email_identifiers(*, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite email + gmail_addr rows to lowercase canonical form."""
    return _repair_identifier_kind_group(("email", "gmail_addr"), dry_run=dry_run, reason_prefix="email")


def repair_wxid_identifiers(*, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite wxid rows to lowercase canonical form."""
    return _repair_identifier_kind_group(("wxid",), dry_run=dry_run, reason_prefix="wxid")


def parse_identifiers_repair_kinds(kinds_str: str) -> dict[str, Any]:
    """
    Parse CLI / MCP ``--kinds`` string.

    Returns ``{"ok": True, "kinds": set(...)}`` or ``{"ok": False, "reason": "bad_kind", "value": ...}``.
    """
    raw = kinds_str.strip().lower().replace(" ", "")
    if raw == "all":
        return {"ok": True, "kinds": {"phone", "email", "wxid"}}
    req: set[str] = set()
    for part in (p.strip() for p in raw.split(",") if p.strip()):
        if part in ("phone", "email", "wxid"):
            req.add(part)
        else:
            return {"ok": False, "reason": "bad_kind", "value": part}
    if not req:
        req.add("phone")
    return {"ok": True, "kinds": req}


def run_identifiers_repair(*, kinds: set[str], dry_run: bool = False) -> dict[str, Any]:
    """
    Run repair for requested kind groups: phone, email (includes gmail_addr), wxid.

    Returns per-group stats under ``results`` plus optional ``totals``.
    """
    allowed = {"phone", "email", "wxid"}
    unknown = kinds - allowed
    if unknown:
        return {"status": "error", "reason": "unknown_kinds", "unknown": sorted(unknown)}
    out: dict[str, Any] = {"dry_run": dry_run, "kinds_requested": sorted(kinds), "results": {}}
    totals = {
        "rows_scanned": 0,
        "skipped_unchanged": 0,
        "updated": 0,
        "deleted_duplicate": 0,
        "merge_candidates": 0,
        "merge_candidate_collisions": 0,
        "merge_candidate_skipped_existing": 0,
    }
    if "phone" in kinds:
        st = repair_phone_identifiers(dry_run=dry_run)
        out["results"]["phone"] = st
        for k in totals:
            totals[k] += int(st.get(k, 0))
    if "email" in kinds:
        st = repair_email_identifiers(dry_run=dry_run)
        out["results"]["email"] = st
        for k in totals:
            totals[k] += int(st.get(k, 0))
    if "wxid" in kinds:
        st = repair_wxid_identifiers(dry_run=dry_run)
        out["results"]["wxid"] = st
        for k in totals:
            totals[k] += int(st.get(k, 0))
    out["totals"] = totals
    out["status"] = "dry_run" if dry_run else "ok"
    return out


def list_persons_for_identifier(kind: str, value: str) -> list[str]:
    norm = normalize_value(kind, value)
    rows = query(
        """
        SELECT DISTINCT person_id
        FROM person_identifiers
        WHERE kind = ? AND value_normalized = ?
        """,
        [kind.lower(), norm],
    )
    return [str(r["person_id"]) for r in rows]


def resolve_identifier(kind: str, value: str) -> str | None:
    """Return person_id if unambiguous; None if unknown; never auto-merges (use register_*)."""
    ids = list_persons_for_identifier(kind, value)
    if len(ids) == 1:
        return ids[0]
    return None


def _enqueue_merge_candidate(
    person_a: str,
    person_b: str,
    score: float,
    reason: str,
    detail: dict[str, Any],
    *,
    dry_run: bool = False,
) -> bool:
    """Enqueue a merge_candidates row for a ``(person_a, person_b)`` pair.

    B-ING-1.10 guarantees:

    1. **Pair-dedupe.** The pair is always normalized to ``(smaller_id, larger_id)``
       and a new row is inserted only when no existing row targets the same pair
       (any status). Prevents the "N rows per pair" spam observed during B-ING-1.8
       pass-2 where multiple stale ``06…`` numbers on the same person all fired
       independent collisions against the same survivor.
    2. **Honor ``dry_run``.** Under ``dry_run=True`` this never writes to the DB.
       The existence check still runs so callers can count would-enqueue pairs
       accurately.

    Returns ``True`` when a row was inserted (or *would have been* inserted under
    dry-run), ``False`` when the pair was already present and we skipped.
    """
    if person_a > person_b:
        person_a, person_b = person_b, person_a
    existing = fetch_one(
        "SELECT id FROM merge_candidates WHERE person_a = ? AND person_b = ? LIMIT 1",
        [person_a, person_b],
    )
    if existing is not None:
        return False
    if dry_run:
        return True
    execute(
        """
        INSERT INTO merge_candidates (person_a, person_b, score, reason, detail_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        [person_a, person_b, score, reason, json.dumps(detail, ensure_ascii=False)],
    )
    return True


def register_identifier(
    person_id: str,
    kind: str,
    value: str,
    *,
    source_kind: str = "",
    confidence: float = 1.0,
    value_original: str | None = None,
) -> dict[str, Any]:
    """
    Insert identifier for person_id.

    Strong kinds (phone/email/wxid/wa_jid/gmail_addr):
    - If exactly one other person holds the same normalized value, T2 auto-merge into
      the lexicographically smaller person_id, then attach the identifier to the survivor.
    - If multiple other owners (ambiguous), enqueue merge_candidates (T3).

    **Caller contract (B-ING-1.12)**: when strong-kind auto-merge fires, the
    caller's ``person_id`` may no longer exist (it was absorbed). Always follow
    the returned ``person_id`` on subsequent operations::

        r = register_identifier(pid, "phone", x)
        pid = r.get("person_id") or pid  # ← track the merge survivor

    Ignoring the return value and reusing the stale ``pid`` for the next
    ``register_identifier`` call leaks orphan ``person_identifiers`` rows whose
    ``person_id`` no longer has a matching ``persons`` row.
    """
    k = kind.lower()
    norm = normalize_value(k, value)
    original = value_original if value_original is not None else value
    strong = k in ("phone", "email", "wxid", "wa_jid", "gmail_addr")

    owners = list_persons_for_identifier(k, value)
    owners = [p for p in owners if p != person_id]
    if strong:
        if len(owners) == 1:
            other = owners[0]
            kept, absorbed = sorted([person_id, other])
            merge_persons(kept, absorbed, "auto_t2_strong_identifier", {"kind": k, "value_normalized": norm})
            person_id = kept
        elif len(owners) > 1:
            _enqueue_merge_candidate(
                person_id,
                owners[0],
                0.5,
                "ambiguous_strong_identifier",
                {"kind": k, "value_normalized": norm, "owners": owners},
            )
            return {
                "status": "collision_ambiguous",
                "person_id": person_id,
                "kind": k,
                "owners": owners,
            }

    execute(
        """
        INSERT INTO person_identifiers
            (person_id, kind, value_normalized, value_original, confidence, source_kind)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (person_id, kind, value_normalized) DO NOTHING
        """,
        [person_id, k, norm, original, confidence, source_kind],
    )
    return {"status": "ok", "person_id": person_id, "kind": k}


def ensure_person_with_seed(
    primary_name: str,
    *,
    seed_identifiers: list[tuple[str, str]] | None = None,
    source_kind: str = "resolver",
) -> str:
    """Create a new person row and optional seed identifiers; returns person_id.

    If any seed identifier triggers an auto-T2 merge (strong-kind collision), the
    returned ``person_id`` is the merge survivor, not necessarily the freshly
    generated one. (B-ING-1.12)
    """
    pid = f"p_{uuid.uuid4().hex[:12]}"
    execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES (?, ?, '[]', '[]', CURRENT_TIMESTAMP)
        """,
        [pid, primary_name],
    )
    if seed_identifiers:
        for kind, val in seed_identifiers:
            r = register_identifier(pid, kind, val, source_kind=source_kind)
            followed = r.get("person_id") if isinstance(r, dict) else None
            if followed:
                pid = followed
    return pid


def _merge_aliases_payload(
    *,
    kept_primary: str,
    kept_aliases_json: str,
    absorbed_primary: str,
    absorbed_aliases_json: str,
) -> str:
    """Return the new kept ``aliases_json`` after absorbing another person.

    Combines ``kept.aliases`` + ``absorbed.primary_name`` + ``absorbed.aliases``,
    dropping any token that case-insensitively matches ``kept_primary`` (redundant
    with the primary name itself) and deduping case-insensitively while preserving
    first-seen order. Absorbed's primary_name is added before absorbed's aliases
    so it lands near the front of the list — this is the value users most often
    search for via `who`.
    """

    def _as_list(raw: str) -> list[str]:
        try:
            val = json.loads(raw or "[]")
        except (TypeError, ValueError):
            return []
        if not isinstance(val, list):
            return []
        return [str(x).strip() for x in val if str(x).strip()]

    seen: set[str] = {kept_primary.strip().lower()}
    result: list[str] = []
    for candidate in [*_as_list(kept_aliases_json), absorbed_primary.strip(), *_as_list(absorbed_aliases_json)]:
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return json.dumps(result, ensure_ascii=False)


def merge_persons(kept_person_id: str, absorbed_person_id: str, reason: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """Re-point foreign keys and delete absorbed person (T2 merge).

    B-ING-1.11: before detaching the absorbed row, append its ``primary_name``
    (and any pre-existing aliases) into ``kept.aliases_json`` so `who` / alias
    search can still resolve the historical spelling / nickname / translation.
    """
    detail = detail or {}

    absorbed_row = fetch_one(
        "SELECT primary_name, aliases_json FROM persons WHERE person_id = ?",
        [absorbed_person_id],
    )
    kept_row = fetch_one(
        "SELECT primary_name, aliases_json FROM persons WHERE person_id = ?",
        [kept_person_id],
    )
    if absorbed_row is not None and kept_row is not None:
        new_aliases_json = _merge_aliases_payload(
            kept_primary=str(kept_row["primary_name"] or ""),
            kept_aliases_json=str(kept_row["aliases_json"] or "[]"),
            absorbed_primary=str(absorbed_row["primary_name"] or ""),
            absorbed_aliases_json=str(absorbed_row["aliases_json"] or "[]"),
        )
        execute(
            "UPDATE persons SET aliases_json = ? WHERE person_id = ?",
            [new_aliases_json, kept_person_id],
        )

    execute(
        """
        DELETE FROM person_identifiers AS pi
        WHERE pi.person_id = ?
          AND EXISTS (
            SELECT 1 FROM person_identifiers pk
            WHERE pk.person_id = ?
              AND pk.kind = pi.kind
              AND pk.value_normalized = pi.value_normalized
          )
        """,
        [absorbed_person_id, kept_person_id],
    )
    execute(
        "UPDATE interactions SET person_id = ? WHERE person_id = ?",
        [kept_person_id, absorbed_person_id],
    )
    execute(
        "UPDATE person_identifiers SET person_id = ? WHERE person_id = ?",
        [kept_person_id, absorbed_person_id],
    )
    execute(
        "UPDATE person_notes SET person_id = ? WHERE person_id = ?",
        [kept_person_id, absorbed_person_id],
    )
    execute("DELETE FROM persons WHERE person_id = ?", [absorbed_person_id])
    execute(
        """
        INSERT INTO merge_log (kept_person_id, absorbed_person_id, reason, detail_json)
        VALUES (?, ?, ?, ?)
        """,
        [kept_person_id, absorbed_person_id, reason, json.dumps(detail, ensure_ascii=False)],
    )
    return {"status": "merged", "kept": kept_person_id, "absorbed": absorbed_person_id}

