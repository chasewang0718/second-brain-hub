"""Tests for T3 merge_candidates list/accept/reject."""

from __future__ import annotations

import json

from brain_agents.identity_resolver import ensure_person_with_seed
from brain_agents.merge_candidates import accept_candidate, list_candidates, reject_candidate
from brain_memory.structured import execute, fetch_one, query


def _seed_candidate(pa: str, pb: str, *, reason: str = "test_reason") -> int:
    execute(
        """
        INSERT INTO merge_candidates (person_a, person_b, score, reason, detail_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        [pa, pb, 0.5, reason, json.dumps({"test": True})],
    )
    row = fetch_one(
        "SELECT id FROM merge_candidates WHERE person_a = ? AND person_b = ? ORDER BY id DESC LIMIT 1",
        [pa, pb],
    )
    assert row is not None
    return int(row["id"])


def test_reject_marks_rejected_and_is_idempotent() -> None:
    a = ensure_person_with_seed("T Reject A", source_kind="test")
    b = ensure_person_with_seed("T Reject B", source_kind="test")
    cid = _seed_candidate(a, b)

    first = reject_candidate(cid)
    assert first["status"] == "ok"
    row = fetch_one("SELECT status FROM merge_candidates WHERE id = ?", [cid])
    assert row and row["status"] == "rejected"

    second = reject_candidate(cid)
    assert second["status"] == "noop"


def test_accept_merges_persons_default_keeps_smaller_id() -> None:
    a = ensure_person_with_seed("T Acc A", source_kind="test")
    b = ensure_person_with_seed("T Acc B", source_kind="test")
    cid = _seed_candidate(a, b)

    r = accept_candidate(cid)
    assert r["status"] == "merged"
    kept, absorbed = sorted([a, b])
    assert r["kept"] == kept and r["absorbed"] == absorbed

    # absorbed person is gone; kept remains
    rows_kept = query("SELECT person_id FROM persons WHERE person_id = ?", [kept])
    rows_abs = query("SELECT person_id FROM persons WHERE person_id = ?", [absorbed])
    assert len(rows_kept) == 1 and len(rows_abs) == 0

    status_row = fetch_one("SELECT status FROM merge_candidates WHERE id = ?", [cid])
    assert status_row and status_row["status"] == "accepted"


def test_accept_with_explicit_keep_param() -> None:
    a = ensure_person_with_seed("T Keep A", source_kind="test")
    b = ensure_person_with_seed("T Keep B", source_kind="test")
    cid = _seed_candidate(a, b)
    larger = a if a > b else b
    smaller = b if larger == a else a

    r = accept_candidate(cid, kept_person_id=larger)
    assert r["status"] == "merged"
    assert r["kept"] == larger and r["absorbed"] == smaller


def test_accept_rejects_unknown_keep_value() -> None:
    a = ensure_person_with_seed("T Bad A", source_kind="test")
    b = ensure_person_with_seed("T Bad B", source_kind="test")
    cid = _seed_candidate(a, b)
    r = accept_candidate(cid, kept_person_id="p_not_in_pair")
    assert r["status"] == "error" and r["reason"] == "kept_not_in_pair"


def test_list_candidates_filters_by_status() -> None:
    rows_all = list_candidates(status="all", limit=500)
    rows_pending = list_candidates(status="pending", limit=500)
    assert all(str(r["status"]).lower() == "pending" for r in rows_pending)
    assert len(rows_all) >= len(rows_pending)
