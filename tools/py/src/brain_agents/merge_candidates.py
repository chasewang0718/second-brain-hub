"""T3 merge queue: list / accept / reject manual identity merge candidates."""

from __future__ import annotations

from typing import Any

from brain_memory.structured import execute, fetch_one, query

from brain_agents.identity_resolver import merge_persons


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
