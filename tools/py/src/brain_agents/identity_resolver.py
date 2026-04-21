"""Map channel-specific identifiers (phone, email, wxid, …) to persons + merge tiers T1/T2/T3."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from brain_memory.structured import execute, query


def normalize_value(kind: str, value: str) -> str:
    k = kind.lower()
    raw = value.strip()
    if k in ("email", "gmail_addr"):
        return raw.lower()
    if k == "phone":
        digits = re.sub(r"\D", "", raw)
        return digits
    return raw.lower()


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

