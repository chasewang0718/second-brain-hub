"""people-render: DuckDB → Markdown under 06-people/by-person/."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain_agents.people_render import run_people_render
from brain_memory.structured import ensure_schema, execute


@pytest.fixture
def isolated_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_DB_PATH", str(tmp_path / "brain.duckdb"))
    vault = tmp_path / "vault"
    (vault / "06-people").mkdir(parents=True)
    ensure_schema()
    execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES (?, ?, '[]', '[]', CURRENT_TIMESTAMP)
        """,
        ["p_test_render", "Render Test Person"],
    )
    execute(
        """
        INSERT INTO interactions (id, person_id, ts_utc, channel, summary, source_path, detail_json, source_kind)
        VALUES (nextval('interactions_id_seq'), ?, CURRENT_TIMESTAMP, 'wechat', 'hello summary', 'src', '{}', 'wechat')
        """,
        ["p_test_render"],
    )
    return vault


def test_people_render_writes_markdown(isolated_brain, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = run_people_render(
        person_id="p_test_render",
        dry_run=False,
        content_root=isolated_brain,
        graph_hints=False,
    )
    assert out["status"] == "ok"
    assert out["count"] == 1
    path = Path(out["written"][0])
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "AUTO-GENERATED" in text
    assert "Render Test Person" in text
    assert "hello summary" in text
    assert "p_test_render" in text


def test_people_render_all_writes_index(isolated_brain, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = run_people_render(
        all_people=True,
        since_days=0,
        limit=50,
        dry_run=False,
        content_root=isolated_brain,
    )
    assert out["status"] == "ok"
    assert out["count"] >= 1
    idx = Path(out["out_dir"]) / "_index.md"
    assert idx.exists()
    assert "People cards index" in idx.read_text(encoding="utf-8")


def test_people_render_requires_single_selector(tmp_path):
    r = run_people_render(who="x", person_id="y", dry_run=True, content_root=tmp_path / "v")
    assert r["status"] == "error"


def test_people_render_emits_facts_and_metrics(isolated_brain, tmp_path, monkeypatch):
    """Phase A6 S1: Facts + Metrics sections appear when data exists."""
    monkeypatch.chdir(tmp_path)
    from brain_agents.person_facts import add_fact
    from brain_agents.person_metrics import recompute_all

    add_fact("p_test_render", "residence", "Hangzhou")
    add_fact("p_test_render", "role", "founder", confidence=0.9)
    recompute_all()

    out = run_people_render(
        person_id="p_test_render",
        dry_run=False,
        content_root=isolated_brain,
    )
    assert out["status"] == "ok"
    text = Path(out["written"][0]).read_text(encoding="utf-8")
    assert "## Facts" in text
    assert "Hangzhou" in text
    assert "founder" in text
    assert "## Metrics" in text
    assert "interactions" in text


def test_people_render_no_facts_section_when_empty(isolated_brain, tmp_path, monkeypatch):
    """Graceful degradation: no Facts header when person has no facts."""
    monkeypatch.chdir(tmp_path)
    out = run_people_render(
        person_id="p_test_render",
        dry_run=False,
        content_root=isolated_brain,
    )
    text = Path(out["written"][0]).read_text(encoding="utf-8")
    assert "## Facts" not in text


def test_people_render_facts_history_flag(isolated_brain, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from brain_agents.person_facts import add_fact

    add_fact("p_test_render", "role", "contractor")
    add_fact("p_test_render", "role", "founder")

    out = run_people_render(
        person_id="p_test_render",
        facts_history=True,
        dry_run=False,
        content_root=isolated_brain,
    )
    text = Path(out["written"][0]).read_text(encoding="utf-8")
    assert "### Facts history" in text
    assert "contractor" in text
    assert "founder" in text


def test_people_render_open_threads_table_with_due(isolated_brain, tmp_path, monkeypatch):
    """Phase A6 Sprint 2: Open threads renders as a table with due/status chips."""
    monkeypatch.chdir(tmp_path)
    from datetime import UTC, datetime, timedelta

    from brain_agents.open_threads import add_thread

    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    add_thread(
        "p_test_render",
        "send the book",
        due_utc=now + timedelta(days=2),
        promised_by="self",
    )
    add_thread(
        "p_test_render",
        "review draft",
        due_utc=now - timedelta(days=1),
        promised_by="other",
    )
    add_thread("p_test_render", "loose follow-up")  # no due

    out = run_people_render(
        person_id="p_test_render",
        dry_run=False,
        content_root=isolated_brain,
    )
    text = Path(out["written"][0]).read_text(encoding="utf-8")
    assert "## Open threads" in text
    # Table headers present
    assert "| status | due | who owes | body | last seen | source |" in text
    # At least one overdue chip and one soon chip
    assert "overdue" in text
    assert "soon" in text
    # All three bodies rendered
    assert "send the book" in text
    assert "review draft" in text
    assert "loose follow-up" in text


def test_people_render_open_threads_none_when_empty(isolated_brain, tmp_path, monkeypatch):
    """No open threads → keeps legacy '(none)' placeholder."""
    monkeypatch.chdir(tmp_path)
    out = run_people_render(
        person_id="p_test_render",
        dry_run=False,
        content_root=isolated_brain,
    )
    text = Path(out["written"][0]).read_text(encoding="utf-8")
    assert "## Open threads" in text
    # Table header must NOT appear when no threads exist
    assert "| status | due | who owes" not in text


def test_people_render_topics_and_weekly_sections(isolated_brain, tmp_path, monkeypatch):
    """Phase A6 Sprint 3: Topics (30d) + Weekly Digest render when present."""
    monkeypatch.chdir(tmp_path)
    import json as _json

    from brain_agents.person_digest import (
        INSIGHT_TOPICS,
        INSIGHT_WEEKLY,
        rebuild_one,
    )
    from brain_memory.structured import execute

    # Seed a handful of interactions so rebuild doesn't skip. Use an
    # explicit UTC-naive timestamp because ``CURRENT_TIMESTAMP`` in DuckDB
    # stores local wall-clock time and would fall outside the rebuild
    # window on non-UTC dev machines.
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    base = _dt.now(_UTC).replace(tzinfo=None) - _td(days=1)
    for i, summary in enumerate([
        "聊周末徒步",
        "讨论餐厅预订",
        "发张照片",
    ]):
        execute(
            """
            INSERT INTO interactions (id, person_id, ts_utc, channel, summary, source_path, detail_json, source_kind)
            VALUES (nextval('interactions_id_seq'), ?, ?, 'wechat', ?, 'src', '{}', 'test')
            """,
            ["p_test_render", base + _td(minutes=i), f"第{i}条: {summary}"],
        )

    def _llm(prompt: str, model: str) -> str:  # noqa: ARG001
        if "narrative" in prompt:
            return _json.dumps(
                {"topics": ["徒步", "餐厅", "照片"], "narrative": "最近聊徒步、订餐厅、拍照片。"},
                ensure_ascii=False,
            )
        return "本周互动较少，主要围绕周末安排。"

    rebuild_one(
        "p_test_render",
        insight_types=[INSIGHT_TOPICS, INSIGHT_WEEKLY],
        llm_fn=_llm,
    )

    out = run_people_render(
        person_id="p_test_render",
        dry_run=False,
        content_root=isolated_brain,
    )
    text = Path(out["written"][0]).read_text(encoding="utf-8")
    assert "## Topics (30d)" in text
    assert "`徒步`" in text
    assert "最近聊徒步" in text
    assert "## Weekly Digest" in text
    assert "本周互动" in text


def test_people_render_skips_topics_section_when_absent(isolated_brain, tmp_path, monkeypatch):
    """Without person-digest output, Topics/Weekly sections are silently omitted."""
    monkeypatch.chdir(tmp_path)
    out = run_people_render(
        person_id="p_test_render",
        dry_run=False,
        content_root=isolated_brain,
    )
    text = Path(out["written"][0]).read_text(encoding="utf-8")
    assert "## Topics (30d)" not in text
    assert "## Weekly Digest" not in text


def test_people_render_relationship_tier_section(isolated_brain, tmp_path, monkeypatch):
    """Phase A6 Sprint 4: tier set → frontmatter + section shows status chip."""
    monkeypatch.chdir(tmp_path)
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from brain_agents.relationship_tier import set_tier
    from brain_memory.structured import execute

    # Seed metrics so dormancy > cadence triggers the overdue chip
    last = _dt.now(_UTC).replace(tzinfo=None) - _td(days=30)
    execute(
        """
        INSERT INTO person_metrics
          (person_id, first_seen_utc, last_seen_utc,
           interactions_all, interactions_30d, interactions_90d,
           distinct_channels_30d, dormancy_days)
        VALUES (?, ?, ?, 50, 0, 5, 1, 30)
        """,
        ["p_test_render", last - _td(days=60), last],
    )
    set_tier("p_test_render", "inner")

    out = run_people_render(
        person_id="p_test_render",
        dry_run=False,
        content_root=isolated_brain,
    )
    text = Path(out["written"][0]).read_text(encoding="utf-8")
    assert "relationship_tier: inner" in text
    assert "cadence_target_days: 14" in text
    assert "## Relationship Tier" in text
    assert "`inner`" in text
    assert "16d overdue" in text  # 30 - 14


def test_people_render_tier_within_cadence_shows_check(isolated_brain, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from brain_agents.relationship_tier import set_tier
    from brain_memory.structured import execute

    last = _dt.now(_UTC).replace(tzinfo=None) - _td(days=3)
    execute(
        """
        INSERT INTO person_metrics
          (person_id, first_seen_utc, last_seen_utc,
           interactions_all, interactions_30d, interactions_90d,
           distinct_channels_30d, dormancy_days)
        VALUES (?, ?, ?, 100, 20, 60, 1, 3)
        """,
        ["p_test_render", last - _td(days=60), last],
    )
    set_tier("p_test_render", "close")

    out = run_people_render(person_id="p_test_render", dry_run=False, content_root=isolated_brain)
    text = Path(out["written"][0]).read_text(encoding="utf-8")
    assert "## Relationship Tier" in text
    assert "within cadence" in text


def test_people_render_no_tier_section_when_absent(isolated_brain, tmp_path, monkeypatch):
    """No tier fact + no suggestion → section silently omitted."""
    monkeypatch.chdir(tmp_path)
    out = run_people_render(person_id="p_test_render", dry_run=False, content_root=isolated_brain)
    text = Path(out["written"][0]).read_text(encoding="utf-8")
    assert "## Relationship Tier" not in text
    assert "relationship_tier:" not in text
