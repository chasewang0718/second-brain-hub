"""Phase A6 Sprint 2: daily-digest commitment sections; Sprint 4: tier alerts."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from pathlib import Path

import pytest

from brain_memory import structured


def _append_tier_alert_tests():
    """Marker for grep. Real tests live below the Sprint 2 block."""
    return None


@pytest.fixture
def isolated_brain(tmp_path: Path, monkeypatch):
    """Isolated DuckDB + fake content_root for digest output."""
    db = tmp_path / "digest.duckdb"
    monkeypatch.setattr(structured, "_db_path", lambda: db)
    structured.ensure_schema()

    vault = tmp_path / "vault"
    (vault / "08-indexes" / "digests").mkdir(parents=True)

    # Patch the content_root lookup that digest uses.
    from brain_agents import digest as dg

    monkeypatch.setattr(dg, "_content_root", lambda: vault)
    # Prevent the real recompute from scanning the real FS
    monkeypatch.setattr(dg, "_recent_markdown", lambda limit=20: [])
    # Ensure v6 gate snapshot is absent
    monkeypatch.setattr(dg, "_v6_gate_snapshot", lambda: None)

    return vault


def test_daily_digest_includes_today_and_overdue_commitment_sections(isolated_brain):
    from brain_agents import digest as dg
    from brain_agents.open_threads import add_thread

    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    add_thread(
        "p_today",
        "review draft today",
        due_utc=now.replace(hour=15, minute=0, second=0),
        promised_by="self",
    )
    add_thread(
        "p_overdue",
        "ship old package",
        due_utc=now - timedelta(days=3),
        promised_by="self",
    )
    add_thread("p_later", "far future thing", due_utc=now + timedelta(days=30))

    out = dg.generate_daily_digest()
    assert out["type"] == "daily"
    assert out["due_today_count"] == 1
    assert out["overdue_commitments_count"] == 1

    text = Path(out["path"]).read_text(encoding="utf-8")
    assert "## Today's Commitments" in text
    assert "review draft today" in text
    assert "## Overdue Commitments" in text
    assert "ship old package" in text
    # "far future thing" should NOT appear in either commitment section
    assert "far future thing" not in text


def test_daily_digest_with_no_commitments_shows_none_placeholders(isolated_brain):
    from brain_agents import digest as dg

    out = dg.generate_daily_digest()
    assert out["due_today_count"] == 0
    assert out["overdue_commitments_count"] == 0

    text = Path(out["path"]).read_text(encoding="utf-8")
    # Both sections present with "- none"
    assert text.count("- none") >= 3  # Overdue Contacts + Today + Overdue
    assert "## Today's Commitments" in text
    assert "## Overdue Commitments" in text


def test_daily_digest_excludes_closed_threads(isolated_brain):
    from brain_agents import digest as dg
    from brain_agents.open_threads import add_thread, close_thread

    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    r = add_thread(
        "p_done",
        "already done",
        due_utc=now - timedelta(days=1),
    )
    close_thread(r["id"], status="done")

    out = dg.generate_daily_digest()
    assert out["overdue_commitments_count"] == 0
    text = Path(out["path"]).read_text(encoding="utf-8")
    assert "already done" not in text


# --- Phase A6 Sprint 4: tier-aware relationship alerts ----------------------


def _seed_tier_scenario(inner_dormancy: int, inner_name: str = "田果"):
    """Seed a person → metrics → tier fact trio for alert-section tests."""
    structured.execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES (?, ?, '[]', '[]', ?)
        """,
        ["p_inner", inner_name, datetime.now(UTC).replace(tzinfo=None, microsecond=0)],
    )
    structured.execute(
        """
        INSERT INTO person_metrics
          (person_id, first_seen_utc, last_seen_utc,
           interactions_all, interactions_30d, interactions_90d,
           distinct_channels_30d, dormancy_days)
        VALUES (?, ?, ?, 120, 5, 30, 1, ?)
        """,
        [
            "p_inner",
            datetime.now(UTC).replace(tzinfo=None, microsecond=0) - timedelta(days=120),
            datetime.now(UTC).replace(tzinfo=None, microsecond=0) - timedelta(days=inner_dormancy),
            inner_dormancy,
        ],
    )
    from brain_agents.relationship_tier import set_tier

    set_tier("p_inner", "inner")


def test_relationship_alerts_tiered_section_flags_inner_overdue(isolated_brain):
    from brain_agents import digest as dg

    _seed_tier_scenario(inner_dormancy=20, inner_name="田果")
    out = dg.generate_relationship_alerts(days=45)
    assert out["type"] == "relationship-alerts"
    assert out["tiered_overdue"] == 1
    assert out["tiered_by_tier"]["inner"] == 1

    text = Path(out["path"]).read_text(encoding="utf-8")
    assert "## Tiered Cadence Alarm" in text
    assert "`inner (cadence 14d)`" in text
    assert "田果" in text
    assert "20d" in text  # dormancy
    assert "+6d" in text  # days overdue
    assert "## Overdue Contacts (>=45d, flat baseline)" in text


def test_relationship_alerts_tiered_empty_when_nobody_exceeds(isolated_brain):
    from brain_agents import digest as dg

    _seed_tier_scenario(inner_dormancy=3, inner_name="Safe Person")
    out = dg.generate_relationship_alerts(days=45)
    assert out["tiered_overdue"] == 0
    text = Path(out["path"]).read_text(encoding="utf-8")
    assert "## Tiered Cadence Alarm" in text
    assert "none (nobody with a `relationship_tier`" in text


def test_relationship_alerts_backcompat_when_no_tier_data(isolated_brain):
    """Untiered universe: new section must not crash and shows 'none'."""
    from brain_agents import digest as dg

    out = dg.generate_relationship_alerts(days=45)
    assert out["tiered_overdue"] == 0
    text = Path(out["path"]).read_text(encoding="utf-8")
    assert "## Tiered Cadence Alarm" in text
    # Flat baseline section also present
    assert "## Overdue Contacts (>=45d" in text
