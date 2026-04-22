"""Phase A6 Sprint 3 · person_digest (topics_30d + weekly_digest)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain_agents import person_digest as pd
from brain_memory import structured


@pytest.fixture
def isolated_duckdb(tmp_path: Path, monkeypatch):
    db = tmp_path / "digest.duckdb"
    monkeypatch.setattr(structured, "_db_path", lambda: db)
    structured.ensure_schema()
    return db


def _seed_interactions(pid: str, summaries: list[str], *, base_ts: datetime | None = None) -> None:
    base = base_ts or (datetime.now(UTC).replace(tzinfo=None, microsecond=0) - timedelta(days=1))
    with structured.transaction() as conn:
        for i, s in enumerate(summaries):
            conn.execute(
                """
                INSERT INTO interactions (id, person_id, ts_utc, channel, summary, source_kind)
                VALUES (nextval('interactions_id_seq'), ?, ?, 'wechat', ?, 'test')
                """,
                [pid, base + timedelta(minutes=i), s],
            )


def _mk_topics_llm(topics: list[str], narrative: str):
    payload = json.dumps({"topics": topics, "narrative": narrative}, ensure_ascii=False)

    def _fake(prompt: str, model: str) -> str:  # noqa: ARG001
        if "narrative" in prompt or "topics" in prompt:
            return payload
        # Weekly prompt fallback in same mock
        return "这周聊得不多，待办：帮她改简历。"

    return _fake


def test_rebuild_one_writes_both_insights(isolated_duckdb):
    _seed_interactions("p1", ["聊了周末的徒步", "下周预定餐厅", "发她一张照片"])
    out = pd.rebuild_one(
        "p1",
        llm_fn=_mk_topics_llm(["徒步", "餐厅", "照片"], "最近聊徒步、订餐厅、拍照片。"),
    )
    assert out["status"] == "ok"
    results = {r["insight_type"]: r for r in out["results"]}
    assert results[pd.INSIGHT_TOPICS]["status"] == "ok"
    assert results[pd.INSIGHT_WEEKLY]["status"] == "ok"
    assert results[pd.INSIGHT_TOPICS]["mode"] == "llm"

    current = pd.get_current_insights("p1")
    assert current["topics"] is not None
    assert "徒步" in (current["topics"]["detail"].get("topics") or [])
    assert current["weekly"] is not None
    assert "简历" in current["weekly"]["body"]


def test_rebuild_is_idempotent_and_chains_superseded_by(isolated_duckdb):
    _seed_interactions("p1", ["吃饭", "看电影", "开会"])
    llm = _mk_topics_llm(["吃饭", "电影"], "聊了吃饭和电影。")

    r1 = pd.rebuild_one("p1", insight_types=[pd.INSIGHT_TOPICS], llm_fn=llm)
    r2 = pd.rebuild_one("p1", insight_types=[pd.INSIGHT_TOPICS], llm_fn=llm)

    first_id = r1["results"][0]["id"]
    second_id = r2["results"][0]["id"]
    assert second_id != first_id
    assert r2["results"][0]["prior_id"] == first_id

    rows = structured.query(
        "SELECT id, superseded_by FROM person_insights WHERE person_id = ? AND insight_type = ? ORDER BY id",
        ["p1", pd.INSIGHT_TOPICS],
    )
    assert len(rows) == 2
    # Older row points to newer via superseded_by; newer has NULL
    assert rows[0]["superseded_by"] == second_id
    assert rows[1]["superseded_by"] is None

    # get_current_insights returns only the latest
    current = pd.get_current_insights("p1")
    assert current["topics"]["id"] == second_id


def test_rebuild_empty_interactions_skips_cleanly(isolated_duckdb):
    # No summaries for p_empty
    out = pd.rebuild_one("p_empty", llm_fn=lambda p, m: "should not be called")
    statuses = [r["status"] for r in out["results"]]
    assert statuses == ["skipped", "skipped"]
    # Nothing written
    assert structured.query("SELECT COUNT(*) as n FROM person_insights")[0]["n"] == 0


def test_rebuild_llm_crash_falls_back_to_heuristic(isolated_duckdb):
    _seed_interactions("p1", ["吃饭吃饭", "打球打球", "约饭约饭"])

    def _boom(prompt: str, model: str) -> str:  # noqa: ARG001
        raise RuntimeError("ollama down")

    out = pd.rebuild_one("p1", llm_fn=_boom)
    results = {r["insight_type"]: r for r in out["results"]}
    assert results[pd.INSIGHT_TOPICS]["status"] == "ok"
    assert results[pd.INSIGHT_TOPICS]["mode"] == "heuristic"
    assert results[pd.INSIGHT_WEEKLY]["mode"] == "heuristic"

    current = pd.get_current_insights("p1")
    assert current["topics"]["source_kind"] == "heuristic"
    topics = current["topics"]["detail"].get("topics") or []
    assert any("吃饭" in t for t in topics)


def test_rebuild_llm_returns_garbage_falls_back(isolated_duckdb):
    _seed_interactions("p1", ["内容甲", "内容乙", "内容丙"])
    out = pd.rebuild_one(
        "p1",
        insight_types=[pd.INSIGHT_TOPICS],
        llm_fn=lambda p, m: "I don't know how to do that, sorry",
    )
    assert out["results"][0]["mode"] == "heuristic"


def test_rebuild_respects_window(isolated_duckdb):
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    # One interaction 60 days ago, one 3 days ago
    with structured.transaction() as conn:
        conn.execute(
            "INSERT INTO interactions (id, person_id, ts_utc, channel, summary, source_kind) VALUES (nextval('interactions_id_seq'), ?, ?, 'wechat', ?, 'test')",
            ["p1", now - timedelta(days=60), "旧对话（不应进窗口）"],
        )
        conn.execute(
            "INSERT INTO interactions (id, person_id, ts_utc, channel, summary, source_kind) VALUES (nextval('interactions_id_seq'), ?, ?, 'wechat', ?, 'test')",
            ["p1", now - timedelta(days=3), "最近对话（应该进窗口）"],
        )

    captured_prompts: list[str] = []

    def _capture(prompt: str, model: str) -> str:  # noqa: ARG001
        captured_prompts.append(prompt)
        return json.dumps({"topics": ["近况"], "narrative": "最近的一段总结。"})

    out = pd.rebuild_one(
        "p1",
        insight_types=[pd.INSIGHT_TOPICS],
        topics_days=30,
        llm_fn=_capture,
        window_end=now,
    )
    assert out["results"][0]["status"] == "ok"
    assert out["results"][0]["sample_count"] == 1
    assert "最近对话" in captured_prompts[0]
    assert "旧对话" not in captured_prompts[0]


def test_rebuild_respects_explicit_insight_types(isolated_duckdb):
    _seed_interactions("p1", ["a", "b", "c"])
    out = pd.rebuild_one(
        "p1",
        insight_types=[pd.INSIGHT_WEEKLY],
        llm_fn=lambda p, m: "一段周报。",
    )
    assert len(out["results"]) == 1
    assert out["results"][0]["insight_type"] == pd.INSIGHT_WEEKLY


def test_rebuild_rejects_unknown_insight_type(isolated_duckdb):
    with pytest.raises(ValueError):
        pd.rebuild_one("p1", insight_types=["not_a_type"], llm_fn=lambda p, m: "")


def test_rebuild_rejects_empty_person_id(isolated_duckdb):
    with pytest.raises(ValueError):
        pd.rebuild_one("", llm_fn=lambda p, m: "")


def test_parse_topics_payload_handles_fenced_json():
    out = pd._parse_topics_payload('```json\n{"topics":["A","B"],"narrative":"ok"}\n```')
    assert out["topics"] == ["A", "B"]
    assert out["narrative"] == "ok"


def test_parse_topics_payload_recovers_from_prose():
    out = pd._parse_topics_payload('Sure: {"topics":["X"],"narrative":"y"} thanks!')
    assert out["topics"] == ["X"]


def test_parse_topics_payload_empty_on_garbage():
    assert pd._parse_topics_payload("definitely not json")["topics"] == []
    assert pd._parse_topics_payload("")["topics"] == []


def test_rebuild_all_scans_persons_with_recent_interactions(isolated_duckdb):
    _seed_interactions("p_active", ["活跃", "对话", "很多"] * 2)
    # p_cold has no interactions → not scanned
    llm = _mk_topics_llm(["活跃"], "很活跃的一个人。")

    out = pd.rebuild_all(llm_fn=llm)
    assert out["status"] == "ok"
    assert "p_active" in out["persons"]
    assert "p_cold" not in out["persons"]
    assert out["rebuilt"] == 1


def test_rebuild_all_survives_per_person_errors(isolated_duckdb):
    _seed_interactions("p1", ["内容"])
    _seed_interactions("p2", ["内容"])

    calls = {"n": 0}

    def _flaky(prompt: str, model: str) -> str:  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            # First prompt crashes — heuristic fallback will kick in for that insight
            raise RuntimeError("first call down")
        return json.dumps({"topics": ["ok"], "narrative": "ok"})

    out = pd.rebuild_all(llm_fn=_flaky)
    # Both persons processed; LLM crash is absorbed by the heuristic fallback,
    # so rebuild_all sees 2 ok rebuilds and 0 top-level errors.
    assert out["rebuilt"] == 2
    assert out["errors"] == []


def test_get_current_insights_returns_none_when_absent(isolated_duckdb):
    current = pd.get_current_insights("p_nobody")
    assert current == {"topics": None, "weekly": None}
