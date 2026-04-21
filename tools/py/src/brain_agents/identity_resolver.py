"""Map channel-specific identifiers (phone, email, wxid, …) to persons + merge tiers T1/T2/T3."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from brain_memory.structured import execute, query

# Mainland China mobile, national significant number (11 digits, leading 1).
# Tuned to avoid treating NANP domestic numbers like 14155550123 as CN (collision with coarse 1[3-9]… rules).
_CN_DOMESTIC_MOBILE = re.compile(
    r"^1(?:3\d{9}|4[5-9]\d{8}|5[0-35-9]\d{8}|6[2567]\d{8}|7[0-8]\d{8}|8\d{9}|9[0-35-9]\d{8})$"
)


def normalize_phone_digits(raw: str) -> str:
    """Normalize phone for matching: digits-only canonical form; CN mobiles → leading 86."""
    d = re.sub(r"\D", "", raw or "")
    if not d:
        return ""
    # Common dial-out prefix 0086xxxxxxxxxxx → 86xxxxxxxxxxxx
    if d.startswith("0086"):
        d = "86" + d[4:]
    # Already E.164-like China (+86 …)
    if len(d) == 13 and d.startswith("86"):
        rest = d[2:]
        if _CN_DOMESTIC_MOBILE.match(rest):
            return d
        return d
    # 11-digit domestic CN mobile
    if _CN_DOMESTIC_MOBILE.match(d):
        return "86" + d
    return d


def normalize_value(kind: str, value: str) -> str:
    k = kind.lower()
    raw = value.strip()
    if k in ("email", "gmail_addr"):
        return raw.lower()
    if k == "phone":
        return normalize_phone_digits(raw)
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
        "dry_run": dry_run,
    }
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
        if len(opids) > 1:
            _enqueue_merge_candidate(
                pid,
                opids[0],
                0.45,
                f"{reason_prefix}_repair_ambiguous",
                {
                    "kind": kind_k,
                    "new_norm": new_norm,
                    "old_normalized": old_norm,
                    "row_id": oid,
                    "owners": opids,
                },
            )
            stats["merge_candidates"] += 1
            continue
        if len(opids) == 1:
            _enqueue_merge_candidate(
                pid,
                opids[0],
                0.6,
                f"{reason_prefix}_repair_collision",
                {"kind": kind_k, "new_norm": new_norm, "old_normalized": old_norm, "row_id": oid},
            )
            stats["merge_candidates"] += 1
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
    totals = {"rows_scanned": 0, "skipped_unchanged": 0, "updated": 0, "deleted_duplicate": 0, "merge_candidates": 0}
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
) -> None:
    if person_a > person_b:
        person_a, person_b = person_b, person_a
    execute(
        """
        INSERT INTO merge_candidates (person_a, person_b, score, reason, detail_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        [person_a, person_b, score, reason, json.dumps(detail, ensure_ascii=False)],
    )


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
    """Create a new person row and optional seed identifiers; returns person_id."""
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
            register_identifier(pid, kind, val, source_kind=source_kind)
    return pid


def merge_persons(kept_person_id: str, absorbed_person_id: str, reason: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """Re-point foreign keys and delete absorbed person (T2 merge)."""
    detail = detail or {}
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

