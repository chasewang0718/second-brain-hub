"""Phase A6 Sprint 1 · bi-temporal person_facts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from brain_agents import person_facts as pf
from brain_memory import structured


@pytest.fixture
def isolated_duckdb(tmp_path: Path, monkeypatch):
    db = tmp_path / "facts.duckdb"
    monkeypatch.setattr(structured, "_db_path", lambda: db)
    structured.ensure_schema()
    return db


def _current(person_id: str, key: str):
    rows = pf.list_facts(person_id, key=key)
    return rows[0] if rows else None


def test_add_fact_inserts_current_row(isolated_duckdb):
    out = pf.add_fact("p1", "residence", "Hangzhou")
    assert out["status"] == "ok"
    assert out["inserted_id"] is not None
    assert out["closed_id"] is None
    assert json.loads(out["value_json"]) == "Hangzhou"

    cur = _current("p1", "residence")
    assert cur is not None
    assert pf.decode_value(cur) == "Hangzhou"
    assert cur["valid_to"] is None
    assert float(cur["confidence"]) == 1.0


def test_add_fact_with_structured_value_json(isolated_duckdb):
    payload = {"city": "杭州", "country": "CN"}
    out = pf.add_fact("p1", "location", value_json=json.dumps(payload))
    assert out["status"] == "ok"
    cur = _current("p1", "location")
    assert pf.decode_value(cur) == payload


def test_repeated_write_is_noop(isolated_duckdb):
    pf.add_fact("p1", "role", "founder")
    out = pf.add_fact("p1", "role", "founder")
    assert out["status"] == "noop"
    rows = pf.list_facts("p1", include_history=True, key="role")
    assert len(rows) == 1  # still only one physical row


def test_new_value_closes_old_fact(isolated_duckdb):
    first = pf.add_fact("p1", "role", "contractor")
    second = pf.add_fact("p1", "role", "founder")
    assert second["closed_id"] == first["inserted_id"]
    history = pf.list_facts("p1", include_history=True, key="role")
    assert len(history) == 2
    # Exactly one current fact
    current = [r for r in history if r["valid_to"] is None]
    assert len(current) == 1
    assert pf.decode_value(current[0]) == "founder"


def test_point_in_time_query(isolated_duckdb):
    t_first = datetime(2026, 1, 1, 12, 0, 0)
    t_switch = datetime(2026, 3, 1, 12, 0, 0)
    pf.add_fact("p1", "city", "Beijing", valid_from=t_first)
    # Small sleep-free manipulation: directly close first by adding new.
    pf.add_fact("p1", "city", "Hangzhou", valid_from=t_switch)

    # At t_first (before switch): Beijing
    at_q1 = datetime(2026, 2, 1, 0, 0, 0)
    rows = pf.list_facts("p1", at=at_q1)
    assert len(rows) == 1
    assert pf.decode_value(rows[0]) == "Beijing"

    # At now (after switch): Hangzhou
    rows_now = pf.list_facts("p1")
    assert len(rows_now) == 1
    assert pf.decode_value(rows_now[0]) == "Hangzhou"


def test_invalidate_fact(isolated_duckdb):
    res = pf.add_fact("p1", "residence", "Shanghai")
    fid = res["inserted_id"]
    closed = pf.invalidate_fact(fid)
    assert closed["status"] == "ok"

    # No more current fact
    assert pf.list_facts("p1", key="residence") == []

    # Second invalidate is noop
    again = pf.invalidate_fact(fid)
    assert again["status"] == "noop"

    # Unknown fact is error
    err = pf.invalidate_fact(999_999)
    assert err["status"] == "error"


def test_confidence_and_source_persisted(isolated_duckdb):
    pf.add_fact(
        "p1",
        "employer",
        "Acme",
        confidence=0.75,
        source_kind="capsd",
        source_interaction_id=42,
    )
    cur = _current("p1", "employer")
    assert float(cur["confidence"]) == pytest.approx(0.75)
    assert cur["source_kind"] == "capsd"
    assert int(cur["source_interaction_id"]) == 42


def test_force_writes_even_when_identical(isolated_duckdb):
    first = pf.add_fact("p1", "role", "founder")
    forced = pf.add_fact("p1", "role", "founder", force=True)
    assert forced["status"] == "ok"
    assert forced["closed_id"] == first["inserted_id"]
    assert len(pf.list_facts("p1", include_history=True, key="role")) == 2


def test_missing_inputs_raise(isolated_duckdb):
    with pytest.raises(ValueError):
        pf.add_fact("", "k", "v")
    with pytest.raises(ValueError):
        pf.add_fact("p1", "", "v")
    with pytest.raises(ValueError):
        pf.add_fact("p1", "k", value_json="   ")
    with pytest.raises(ValueError):
        pf.add_fact("p1", "k", value_json="not json {")


def test_include_history_returns_closed_rows(isolated_duckdb):
    pf.add_fact("p1", "role", "v1")
    pf.add_fact("p1", "role", "v2")
    pf.add_fact("p1", "role", "v3")
    hist = pf.list_facts("p1", include_history=True, key="role")
    assert len(hist) == 3
    current = [r for r in hist if r["valid_to"] is None]
    assert len(current) == 1
    assert pf.decode_value(current[0]) == "v3"


def test_get_fact_returns_none_when_absent(isolated_duckdb):
    assert pf.get_fact("nobody", "anything") is None


def test_cli_facts_add_accepts_valid_from(isolated_duckdb):
    """CLI exposes --valid-from so users can backfill historical facts."""
    from brain_cli.main import app
    from typer.testing import CliRunner

    runner = CliRunner()

    # Backfill: "she lived in Hangzhou from 2024-01-15 onwards"
    r1 = runner.invoke(
        app,
        ["facts", "add", "p_demo", "residence", "Hangzhou", "--valid-from", "2024-01-15T00:00:00"],
    )
    assert r1.exit_code == 0, r1.stdout
    out1 = json.loads(r1.stdout)
    assert out1["status"] == "ok"
    assert out1["valid_from"].startswith("2024-01-15")

    # Then she moved to Shanghai on 2025-06-01 — this closes the Hangzhou row at 2025-06-01.
    r2 = runner.invoke(
        app,
        ["facts", "add", "p_demo", "residence", "Shanghai", "--valid-from", "2025-06-01T00:00:00"],
    )
    assert r2.exit_code == 0, r2.stdout

    # Point-in-time query in the middle of 2024 should return Hangzhou.
    mid_2024 = datetime(2024, 7, 1, 0, 0, 0)
    rows = pf.list_facts("p_demo", at=mid_2024, key="residence")
    assert len(rows) == 1
    assert pf.decode_value(rows[0]) == "Hangzhou"

    # Point-in-time after the move should return Shanghai.
    late_2025 = datetime(2025, 10, 1, 0, 0, 0)
    rows2 = pf.list_facts("p_demo", at=late_2025, key="residence")
    assert len(rows2) == 1
    assert pf.decode_value(rows2[0]) == "Shanghai"


def test_cli_facts_add_rejects_bad_valid_from(isolated_duckdb):
    from brain_cli.main import app
    from typer.testing import CliRunner

    r = CliRunner().invoke(
        app,
        ["facts", "add", "p_demo", "residence", "X", "--valid-from", "not-a-date"],
    )
    assert r.exit_code != 0
    assert "bad --valid-from" in r.stdout
