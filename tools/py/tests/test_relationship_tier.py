"""Phase A6 Sprint 4 · relationship_tier (tier fact + cadence alarm)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain_agents import relationship_tier as rt
from brain_memory import structured


@pytest.fixture
def isolated_duckdb(tmp_path: Path, monkeypatch):
    db = tmp_path / "tier.duckdb"
    monkeypatch.setattr(structured, "_db_path", lambda: db)
    structured.ensure_schema()
    return db


def _seed_person(pid: str, name: str = "") -> None:
    structured.execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES (?, ?, '[]', '[]', ?)
        """,
        [pid, name or pid, datetime.now(UTC).replace(tzinfo=None, microsecond=0)],
    )


def _seed_metrics(
    pid: str,
    *,
    interactions_all: int = 0,
    interactions_30d: int = 0,
    interactions_90d: int = 0,
    dormancy_days: int | None = None,
) -> None:
    last_seen = (
        datetime.now(UTC).replace(tzinfo=None, microsecond=0) - timedelta(days=int(dormancy_days or 0))
        if dormancy_days is not None
        else None
    )
    structured.execute(
        """
        INSERT INTO person_metrics
          (person_id, first_seen_utc, last_seen_utc,
           interactions_all, interactions_30d, interactions_90d,
           distinct_channels_30d, dormancy_days)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        [pid, last_seen, last_seen, interactions_all, interactions_30d, interactions_90d, dormancy_days],
    )


# --- set_tier / get_tier round trip -----------------------------------------


def test_set_and_get_tier_roundtrip(isolated_duckdb):
    _seed_person("p1")
    out = rt.set_tier("p1", "inner", note="核心家庭成员")
    assert out["tier"] == "inner"
    assert rt.get_tier("p1") == "inner"


def test_set_tier_rejects_unknown_value(isolated_duckdb):
    _seed_person("p1")
    with pytest.raises(ValueError):
        rt.set_tier("p1", "VIP")


def test_set_tier_rejects_empty_person_id(isolated_duckdb):
    with pytest.raises(ValueError):
        rt.set_tier("  ", "inner")


def test_get_tier_returns_none_when_unset(isolated_duckdb):
    _seed_person("p_fresh")
    assert rt.get_tier("p_fresh") is None


def test_set_tier_closes_prior_fact_bi_temporal(isolated_duckdb):
    """Re-setting closes old fact; include_history=True shows both rows."""
    _seed_person("p1")
    rt.set_tier("p1", "close")
    rt.set_tier("p1", "inner")
    hist = rt.list_tiers(include_history=True)
    p1_rows = [r for r in hist if r["person_id"] == "p1"]
    assert len(p1_rows) == 2
    # The current row has valid_to IS NULL; the previous row has been closed.
    current = [r for r in p1_rows if r["valid_to"] is None]
    closed = [r for r in p1_rows if r["valid_to"] is not None]
    assert len(current) == 1
    assert current[0]["tier"] == "inner"
    assert len(closed) == 1
    assert closed[0]["tier"] == "close"


def test_list_tiers_filters_by_tier(isolated_duckdb):
    _seed_person("p1")
    _seed_person("p2")
    _seed_person("p3")
    rt.set_tier("p1", "inner")
    rt.set_tier("p2", "close")
    rt.set_tier("p3", "inner")
    inner_only = rt.list_tiers(tier="inner")
    ids = {r["person_id"] for r in inner_only}
    assert ids == {"p1", "p3"}


# --- config reader ----------------------------------------------------------


def test_load_cadence_config_returns_defaults_when_section_missing(monkeypatch, tmp_path):
    """When thresholds.yaml has no ``people_cadence:``, defaults win."""
    monkeypatch.setattr(
        "brain_core.config.load_thresholds_config",
        lambda: {"unrelated": 1},
    )
    cfg = rt.load_cadence_config()
    assert cfg["inner"] == 14
    assert cfg["close"] == 30
    assert cfg["dormant"] is None


def test_load_cadence_config_respects_yaml_overrides(monkeypatch):
    monkeypatch.setattr(
        "brain_core.config.load_thresholds_config",
        lambda: {"people_cadence": {"inner": 7, "close": 21, "dormant": None}},
    )
    cfg = rt.load_cadence_config()
    assert cfg["inner"] == 7
    assert cfg["close"] == 21
    assert cfg["working"] == 60  # untouched → default
    assert cfg["dormant"] is None


def test_load_cadence_config_rejects_garbage_values(monkeypatch):
    """Typos / bad types must not crash; they fall back to defaults for that tier."""
    monkeypatch.setattr(
        "brain_core.config.load_thresholds_config",
        lambda: {"people_cadence": {"inner": "abc", "close": -5, "working": 0}},
    )
    cfg = rt.load_cadence_config()
    assert cfg["inner"] == 14  # unparseable → kept default
    assert cfg["close"] is None  # negative → treated as "no alarm"
    assert cfg["working"] is None  # 0 → treated as "no alarm"


# --- suggester --------------------------------------------------------------


def test_suggest_tier_heuristic_buckets(isolated_duckdb):
    """Deterministic ladder: very active → inner; long dormant → dormant."""
    _seed_person("p_active")
    _seed_metrics("p_active", interactions_all=400, interactions_30d=50, interactions_90d=150, dormancy_days=1)
    r1 = rt.suggest_tier("p_active")
    assert r1["suggested_tier"] == "inner"

    _seed_person("p_close")
    _seed_metrics("p_close", interactions_all=80, interactions_30d=7, interactions_90d=25, dormancy_days=5)
    r2 = rt.suggest_tier("p_close")
    assert r2["suggested_tier"] == "close"

    _seed_person("p_dormant")
    _seed_metrics("p_dormant", interactions_all=3, interactions_30d=0, interactions_90d=0, dormancy_days=500)
    r3 = rt.suggest_tier("p_dormant")
    assert r3["suggested_tier"] == "dormant"


def test_suggest_tier_chains_superseded_by(isolated_duckdb):
    _seed_person("p1")
    _seed_metrics("p1", interactions_all=400, interactions_30d=50, interactions_90d=150, dormancy_days=1)
    first = rt.suggest_tier("p1")
    second = rt.suggest_tier("p1")
    assert second["prior_insight_id"] == first["insight_id"]
    assert second["insight_id"] != first["insight_id"]

    rows = structured.query(
        "SELECT id, superseded_by FROM person_insights WHERE person_id = ? AND insight_type = ? ORDER BY id",
        ["p1", rt.INSIGHT_TIER_SUGGEST],
    )
    assert len(rows) == 2
    assert rows[0]["superseded_by"] == second["insight_id"]
    assert rows[1]["superseded_by"] is None


def test_suggest_tier_does_not_overwrite_human_fact(isolated_duckdb):
    """The single hard rule: AI never overwrites a human-set tier."""
    _seed_person("p1")
    _seed_metrics("p1", interactions_all=400, interactions_30d=50, interactions_90d=150, dormancy_days=1)
    rt.set_tier("p1", "acquaintance", note="人工刻意")
    # Heuristic would suggest inner, but apply_as_fact must not overwrite.
    res = rt.suggest_tier("p1", apply_as_fact=True)
    assert res["suggested_tier"] == "inner"
    assert res["applied_as_fact"] is False
    assert rt.get_tier("p1") == "acquaintance"


def test_suggest_tier_applies_when_no_human_fact(isolated_duckdb):
    _seed_person("p1")
    _seed_metrics("p1", interactions_all=400, interactions_30d=50, interactions_90d=150, dormancy_days=1)
    res = rt.suggest_tier("p1", apply_as_fact=True)
    assert res["applied_as_fact"] is True
    assert rt.get_tier("p1") == "inner"


def test_suggest_tier_all_skips_people_without_metrics(isolated_duckdb):
    _seed_person("p_with")
    _seed_metrics("p_with", interactions_all=1, interactions_30d=0, interactions_90d=5, dormancy_days=30)
    _seed_person("p_without")  # NO metrics row
    out = rt.suggest_tier_all()
    assert out["status"] == "ok"
    assert out["scanned"] == 1
    ids = {s["person_id"] for s in out["samples"]}
    assert "p_with" in ids
    assert "p_without" not in ids


# --- overdue / cadence ------------------------------------------------------


def test_overdue_inner_flags_when_dormant_more_than_14d(isolated_duckdb):
    _seed_person("p1", "Test Inner")
    _seed_metrics("p1", interactions_all=50, interactions_30d=0, interactions_90d=10, dormancy_days=20)
    rt.set_tier("p1", "inner")
    out = rt.list_overdue_by_tier(cadence={"inner": 14, "close": 30, "working": 60})
    assert len(out["inner"]) == 1
    assert out["inner"][0]["person_id"] == "p1"
    assert out["inner"][0]["days_overdue"] == 6


def test_overdue_excludes_within_threshold(isolated_duckdb):
    _seed_person("p1")
    _seed_metrics("p1", interactions_all=50, interactions_30d=5, interactions_90d=15, dormancy_days=5)
    rt.set_tier("p1", "inner")
    out = rt.list_overdue_by_tier(cadence={"inner": 14})
    assert out["inner"] == []


def test_overdue_excludes_people_without_tier_fact(isolated_duckdb):
    """Legacy-flat-threshold path handles untiered people; we skip them."""
    _seed_person("p1")
    _seed_metrics("p1", interactions_all=50, interactions_30d=0, interactions_90d=10, dormancy_days=400)
    # No set_tier call.
    out = rt.list_overdue_by_tier()
    for rows in out.values():
        assert all(r["person_id"] != "p1" for r in rows)


def test_overdue_ignores_dormant_tier_with_null_cadence(isolated_duckdb):
    _seed_person("p1")
    _seed_metrics("p1", interactions_all=5, interactions_30d=0, interactions_90d=0, dormancy_days=500)
    rt.set_tier("p1", "dormant")
    out = rt.list_overdue_by_tier()
    assert out["dormant"] == []


def test_overdue_sorts_by_days_overdue_desc(isolated_duckdb):
    _seed_person("p_10")
    _seed_metrics("p_10", interactions_all=30, interactions_30d=0, interactions_90d=5, dormancy_days=40)
    _seed_person("p_30")
    _seed_metrics("p_30", interactions_all=30, interactions_30d=0, interactions_90d=5, dormancy_days=100)
    rt.set_tier("p_10", "close")
    rt.set_tier("p_30", "close")
    out = rt.list_overdue_by_tier(cadence={"close": 30})
    assert [r["person_id"] for r in out["close"]] == ["p_30", "p_10"]


def test_overdue_filtered_by_tiers_argument(isolated_duckdb):
    _seed_person("p1")
    _seed_metrics("p1", interactions_all=50, interactions_30d=0, interactions_90d=10, dormancy_days=20)
    rt.set_tier("p1", "inner")
    out = rt.list_overdue_by_tier(tiers=["close"])
    assert "close" in out
    assert "inner" not in out


# --- suggestion getter ------------------------------------------------------


def test_get_tier_suggestion_roundtrip(isolated_duckdb):
    _seed_person("p1")
    _seed_metrics("p1", interactions_all=400, interactions_30d=50, interactions_90d=150, dormancy_days=1)
    rt.suggest_tier("p1")
    got = rt.get_tier_suggestion("p1")
    assert got is not None
    assert got["suggested_tier"] == "inner"
    assert got["detail"]["confidence"] > 0


def test_get_tier_suggestion_returns_none_when_absent(isolated_duckdb):
    assert rt.get_tier_suggestion("p_nobody") is None
