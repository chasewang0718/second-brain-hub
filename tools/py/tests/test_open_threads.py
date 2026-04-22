"""Phase A6 Sprint 2 · open_threads commitment/due logic."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from brain_agents import open_threads as ot
from brain_memory import structured


@pytest.fixture
def isolated_duckdb(tmp_path: Path, monkeypatch):
    db = tmp_path / "threads.duckdb"
    monkeypatch.setattr(structured, "_db_path", lambda: db)
    structured.ensure_schema()
    return db


def test_add_thread_minimal(isolated_duckdb):
    r = ot.add_thread("p1", "下周三寄书")
    assert r["status"] == "ok"
    assert r["id"] is not None
    assert r["body_hash"] is None  # manual without hash

    row = ot.get_thread(r["id"])
    assert row is not None
    assert row["body"] == "下周三寄书"
    assert row["status"] == "open"
    assert row["due_utc"] is None
    assert row["source_kind"] == "manual"


def test_add_thread_with_due_iso_and_promised_by(isolated_duckdb):
    r = ot.add_thread(
        "p1",
        "下周三寄书",
        due_utc="2026-04-30T15:00:00",
        promised_by="self",
    )
    assert r["status"] == "ok"
    assert r["due_utc"].startswith("2026-04-30")
    assert r["promised_by"] == "self"


def test_add_thread_date_only_gets_end_of_day(isolated_duckdb):
    r = ot.add_thread("p1", "send book", due_utc="2026-05-01")
    row = ot.get_thread(r["id"])
    assert row["due_utc"].hour == 23
    assert row["due_utc"].minute == 59


def test_add_thread_requires_person_and_body(isolated_duckdb):
    with pytest.raises(ValueError):
        ot.add_thread("", "body")
    with pytest.raises(ValueError):
        ot.add_thread("p1", "   ")


def test_add_thread_rejects_bad_promised_by(isolated_duckdb):
    with pytest.raises(ValueError):
        ot.add_thread("p1", "x", promised_by="both")


def test_llm_source_auto_hashes_and_dedupes(isolated_duckdb):
    r1 = ot.add_thread(
        "p1",
        "帮他改简历",
        source_kind="llm_extracted",
        source_interaction_id=42,
    )
    assert r1["status"] == "ok"
    assert r1["body_hash"] is not None

    # Same person + same body from a different interaction → dedupe
    r2 = ot.add_thread(
        "p1",
        "帮他改简历",
        source_kind="llm_extracted",
        source_interaction_id=99,
    )
    assert r2["status"] == "noop"
    assert r2["id"] == r1["id"]

    # Only one physical row
    rows = ot.list_threads(person_id="p1", status=None)
    assert len(rows) == 1


def test_manual_writes_are_never_deduped(isolated_duckdb):
    a = ot.add_thread("p1", "ping again", source_kind="manual")
    b = ot.add_thread("p1", "ping again", source_kind="manual")
    assert a["status"] == "ok" and b["status"] == "ok"
    assert a["id"] != b["id"]


def test_force_bypasses_dedupe(isolated_duckdb):
    r1 = ot.add_thread("p1", "hashed", source_kind="llm_extracted")
    r2 = ot.add_thread("p1", "hashed", source_kind="llm_extracted", force=True)
    assert r2["status"] == "ok"
    assert r2["id"] != r1["id"]


def test_close_thread_done_and_dropped_state_machine(isolated_duckdb):
    r = ot.add_thread("p1", "thing")
    tid = r["id"]

    done = ot.close_thread(tid, status="done")
    assert done["status"] == "ok" and done["to"] == "done"

    # Re-closing to same status is noop
    again = ot.close_thread(tid, status="done")
    assert again["status"] == "noop"

    # Can still transition done → dropped
    dropped = ot.close_thread(tid, status="dropped")
    assert dropped["status"] == "ok"
    assert dropped["from"] == "done" and dropped["to"] == "dropped"


def test_close_thread_rejects_unknown_status(isolated_duckdb):
    r = ot.add_thread("p1", "thing")
    with pytest.raises(ValueError):
        ot.close_thread(r["id"], status="pending")


def test_close_thread_not_found(isolated_duckdb):
    assert ot.close_thread(999_999)["status"] == "error"


def test_reopen_thread(isolated_duckdb):
    r = ot.add_thread("p1", "thing")
    ot.close_thread(r["id"], status="done")
    reopened = ot.reopen_thread(r["id"])
    assert reopened["status"] == "ok" and reopened["to"] == "open"

    # No-op if already open
    noop = ot.reopen_thread(r["id"])
    assert noop["status"] == "noop"


def test_update_due_set_and_clear(isolated_duckdb):
    r = ot.add_thread("p1", "thing")
    tid = r["id"]

    u = ot.update_due(tid, due_utc="2026-05-10T12:00:00")
    assert u["status"] == "ok" and u["due_utc"].startswith("2026-05-10")

    cleared = ot.update_due(tid, due_utc=None)
    assert cleared["status"] == "ok" and cleared["due_utc"] is None


def test_list_threads_filters_by_person_and_status(isolated_duckdb):
    ot.add_thread("p1", "a")
    ot.add_thread("p1", "b")
    ot.add_thread("p2", "c")
    done = ot.add_thread("p1", "d")
    ot.close_thread(done["id"], status="done")

    open_p1 = ot.list_threads(person_id="p1", status="open")
    assert len(open_p1) == 2

    all_p1 = ot.list_threads(person_id="p1", status=None)
    assert len(all_p1) == 3

    all_open = ot.list_threads(status="open")
    assert len(all_open) == 3  # p1 x2 + p2 x1


def test_list_due_includes_overdue_and_future(isolated_duckdb):
    now = ot._utc_now()

    ot.add_thread("p1", "overdue", due_utc=now - timedelta(days=3))
    ot.add_thread("p1", "today", due_utc=now)
    ot.add_thread("p1", "in-3-days", due_utc=now + timedelta(days=3))
    ot.add_thread("p1", "in-20-days", due_utc=now + timedelta(days=20))
    ot.add_thread("p1", "no-due")

    within_7 = ot.list_due(within_days=7, include_overdue=True)
    bodies = {r["body"] for r in within_7}
    assert bodies == {"overdue", "today", "in-3-days"}

    within_7_no_overdue = ot.list_due(within_days=7, include_overdue=False)
    bodies = {r["body"] for r in within_7_no_overdue}
    assert "overdue" not in bodies
    assert "today" in bodies


def test_list_due_excludes_closed(isolated_duckdb):
    now = ot._utc_now()
    r = ot.add_thread("p1", "closed-one", due_utc=now + timedelta(days=1))
    ot.close_thread(r["id"], status="done")
    assert ot.list_due(within_days=7) == []


def test_classify_due_buckets():
    now = datetime(2026, 4, 22, 12, 0, 0)
    assert ot.classify_due(None, now=now) == "none"
    assert ot.classify_due(now - timedelta(days=1), now=now) == "overdue"
    assert ot.classify_due(now.replace(hour=23), now=now) == "today"
    assert ot.classify_due(now + timedelta(days=3), now=now) == "soon"
    assert ot.classify_due(now + timedelta(days=30), now=now) == "later"
