"""Phase A6 Sprint 1 路 derived person_metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain_agents import person_metrics as pm
from brain_memory import structured


@pytest.fixture
def isolated_duckdb(tmp_path: Path, monkeypatch):
    db = tmp_path / "metrics.duckdb"
    monkeypatch.setattr(structured, "_db_path", lambda: db)
    structured.ensure_schema()
    return db


def _seed_interaction(person_id: str, ts: datetime, channel: str = "wechat", summary: str = "hi") -> None:
    structured.execute(
        """
        INSERT INTO interactions (id, person_id, ts_utc, channel, summary, source_path, detail_json, source_kind, source_id)
        VALUES (nextval('interactions_id_seq'), ?, ?, ?, ?, '', '{}', 'test', '')
        """,
        [person_id, ts, channel, summary],
    )


def _seed_person(person_id: str, name: str = "x") -> None:
    structured.execute(
        "INSERT OR REPLACE INTO persons (person_id, primary_name) VALUES (?, ?)",
        [person_id, name],
    )


def test_recompute_one_with_no_interactions_returns_cleared(isolated_duckdb):
    _seed_person("pX")
    out = pm.recompute_one("pX")
    assert out["status"] == "ok"
    assert out["updated"] == 0
    assert out["cleared"] == 1


def test_recompute_single_person_basic_counts(isolated_duckdb):
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    _seed_person("p1")
    # 3 interactions: 5 days ago (wechat), 20 days ago (whatsapp), 60 days ago (wechat)
    _seed_interaction("p1", now - timedelta(days=5), "wechat")
    _seed_interaction("p1", now - timedelta(days=20), "whatsapp")
    _seed_interaction("p1", now - timedelta(days=60), "wechat")

    out = pm.recompute_one("p1")
    assert out["status"] == "ok"
    m = out["metrics"]
    assert int(m["interactions_all"]) == 3
    assert int(m["interactions_30d"]) == 2
    assert int(m["interactions_90d"]) == 3
    assert int(m["distinct_channels_30d"]) == 2
    assert str(m["last_interaction_channel"]).lower() == "wechat"
    assert m["dormancy_days"] is not None and int(m["dormancy_days"]) <= 6


def test_recompute_all_rebuilds_multiple_people(isolated_duckdb):
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    for pid in ("a", "b", "c"):
        _seed_person(pid)
    _seed_interaction("a", now - timedelta(days=1))
    _seed_interaction("a", now - timedelta(days=2))
    _seed_interaction("b", now - timedelta(days=100))  # outside 90d
    _seed_interaction("c", now - timedelta(days=10))

    out = pm.recompute_all()
    assert out["status"] == "ok"
    assert out["updated"] == 3
    assert int(out["total_rows"]) == 3

    ma = pm.get_metrics("a")
    assert int(ma["interactions_30d"]) == 2
    mb = pm.get_metrics("b")
    assert int(mb["interactions_30d"]) == 0
    assert int(mb["interactions_90d"]) == 0
    assert int(mb["interactions_all"]) == 1
    mc = pm.get_metrics("c")
    assert int(mc["interactions_30d"]) == 1


def test_dormancy_calculation_bounds(isolated_duckdb):
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    _seed_person("p1")
    _seed_interaction("p1", now - timedelta(days=7))
    pm.recompute_all()
    m = pm.get_metrics("p1")
    # 7 days 卤 1 because of the tick between _utc_now and test clock.
    assert abs(int(m["dormancy_days"]) - 7) <= 1


def test_orphan_removal(isolated_duckdb):
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    _seed_person("orphan")
    # Seed metrics row by hand (simulates absorbed person left behind).
    structured.execute(
        """
        INSERT INTO person_metrics
          (person_id, first_seen_utc, last_seen_utc, last_interaction_channel,
           interactions_all, interactions_30d, interactions_90d,
           distinct_channels_30d, dormancy_days, computed_at)
        VALUES ('orphan', ?, ?, '', 0, 0, 0, 0, NULL, ?)
        """,
        [now, now, now],
    )
    # Seed a real interaction for another person.
    _seed_person("alive")
    _seed_interaction("alive", now - timedelta(days=1))

    out = pm.recompute_all(remove_orphans=True)
    assert out["status"] == "ok"
    assert pm.get_metrics("orphan") is None  # orphan purged
    assert pm.get_metrics("alive") is not None


def test_empty_person_id_returns_error(isolated_duckdb):
    assert pm.recompute_one("  ")["status"] == "error"


def test_ignores_rows_with_blank_person_id(isolated_duckdb):
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    structured.execute(
        """
        INSERT INTO interactions (id, person_id, ts_utc, channel, summary, detail_json)
        VALUES (nextval('interactions_id_seq'), '', ?, 'wechat', 'stray', '{}')
        """,
        [now],
    )
    out = pm.recompute_all()
    assert out["status"] == "ok"
    # No rows in person_metrics because all interactions were blank-id.
    total = structured.fetch_one("SELECT count(*) AS n FROM person_metrics")
    assert int(total["n"]) == 0

