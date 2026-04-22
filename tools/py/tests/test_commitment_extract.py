"""Phase A6 Sprint 2 · LLM commitment extraction (mocked Ollama)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain_agents import commitment_extract as ce
from brain_agents import open_threads as ot
from brain_memory import structured


@pytest.fixture
def isolated_duckdb(tmp_path: Path, monkeypatch):
    db = tmp_path / "ce.duckdb"
    monkeypatch.setattr(structured, "_db_path", lambda: db)
    structured.ensure_schema()
    return db


def _seed_interactions(pid: str, *summaries: str, days_ago: int = 2) -> None:
    ts = datetime.now(UTC).replace(tzinfo=None, microsecond=0) - timedelta(days=days_ago)
    with structured.transaction() as conn:
        for i, s in enumerate(summaries):
            conn.execute(
                """
                INSERT INTO interactions (id, person_id, ts_utc, channel, summary, source_kind)
                VALUES (nextval('interactions_id_seq'), ?, ?, 'wechat', ?, 'test')
                """,
                [pid, ts + timedelta(minutes=i), s],
            )


def _mk_llm(response: str):
    def _fake(prompt: str, model: str) -> str:  # noqa: ARG001
        return response

    return _fake


def test_parse_candidates_plain_json():
    raw = json.dumps(
        [
            {"body": "send book", "due_utc": "2026-05-01", "promised_by": "self", "confidence": 0.9},
            {"body": "review draft", "due_utc": None, "promised_by": "other", "confidence": 0.7},
        ]
    )
    out = ce._parse_candidates(raw)
    assert len(out) == 2
    assert out[0]["body"] == "send book"
    assert out[0]["due_utc"] == "2026-05-01"
    assert out[1]["due_utc"] is None


def test_parse_candidates_strips_code_fence():
    raw = "```json\n" + json.dumps([{"body": "ping her", "confidence": 0.8}]) + "\n```"
    out = ce._parse_candidates(raw)
    assert len(out) == 1
    assert out[0]["body"] == "ping her"
    assert out[0]["promised_by"] is None  # not supplied


def test_parse_candidates_recovers_from_surrounding_prose():
    raw = 'Sure, here you go: [{"body":"ship box","confidence":0.6}] hope this helps!'
    out = ce._parse_candidates(raw)
    assert len(out) == 1
    assert out[0]["body"] == "ship box"


def test_parse_candidates_empty_on_garbage():
    assert ce._parse_candidates("definitely not JSON") == []
    assert ce._parse_candidates("") == []
    assert ce._parse_candidates("{}") == []  # object, not list


def test_parse_candidates_drops_bad_entries():
    raw = json.dumps(
        [
            {"body": "  ", "confidence": 0.9},  # empty body
            "not-a-dict",
            {"body": "keep me", "confidence": "not a number"},  # malformed conf → 0
            {"body": "also keep", "promised_by": "nonsense", "confidence": 0.5},
        ]
    )
    out = ce._parse_candidates(raw)
    bodies = [c["body"] for c in out]
    assert bodies == ["keep me", "also keep"]
    assert out[0]["confidence"] == 0.0
    assert out[1]["promised_by"] is None  # "nonsense" → None


def test_scan_dry_run_no_writes(isolated_duckdb):
    _seed_interactions("p1", "I will send her the book next Wednesday", "chatted about dinner")
    llm = _mk_llm(
        json.dumps(
            [
                {"body": "send the book", "due_utc": "2026-05-01", "promised_by": "self", "confidence": 0.9},
            ]
        )
    )
    out = ce.scan_commitments(since_days=30, llm_fn=llm)
    assert out["status"] == "ok"
    assert out["mode"] == "dry-run"
    assert out["candidate_count"] == 1
    assert out["applied_count"] == 0
    # Nothing written to open_threads
    assert ot.list_threads(person_id="p1", status=None) == []


def test_scan_apply_writes_open_thread(isolated_duckdb):
    _seed_interactions("p1", "I promised to review her draft by Friday")
    llm = _mk_llm(
        json.dumps(
            [
                {"body": "review her draft", "due_utc": "2026-05-02T17:00:00", "promised_by": "self", "confidence": 0.85},
            ]
        )
    )
    out = ce.scan_commitments(since_days=30, apply=True, llm_fn=llm)
    assert out["applied_count"] == 1

    rows = ot.list_threads(person_id="p1", status=None)
    assert len(rows) == 1
    assert rows[0]["body"] == "review her draft"
    assert rows[0]["source_kind"] == "llm_extracted"
    assert rows[0]["body_hash"] is not None


def test_scan_apply_is_idempotent(isolated_duckdb):
    _seed_interactions("p1", "Will ship the laptop next week")
    llm = _mk_llm(
        json.dumps([{"body": "ship laptop", "confidence": 0.9}])
    )
    r1 = ce.scan_commitments(since_days=30, apply=True, llm_fn=llm)
    r2 = ce.scan_commitments(since_days=30, apply=True, llm_fn=llm)

    assert r1["applied_count"] == 1
    assert r2["applied_count"] == 0
    assert r2["deduped_count"] == 1

    rows = ot.list_threads(person_id="p1", status=None)
    assert len(rows) == 1


def test_scan_respects_min_confidence_on_apply(isolated_duckdb):
    _seed_interactions("p1", "maybe I'll send something, unclear")
    llm = _mk_llm(
        json.dumps(
            [
                {"body": "low confidence promise", "confidence": 0.4},
                {"body": "high confidence promise", "confidence": 0.95},
            ]
        )
    )
    out = ce.scan_commitments(
        since_days=30, apply=True, min_confidence=0.6, llm_fn=llm,
    )
    assert out["applied_count"] == 1
    assert out["skipped_low_confidence"] == 1
    rows = ot.list_threads(person_id="p1", status=None)
    assert [r["body"] for r in rows] == ["high confidence promise"]


def test_scan_survives_llm_failure(isolated_duckdb):
    _seed_interactions("p1", "anything")

    def _boom(prompt: str, model: str) -> str:  # noqa: ARG001
        raise RuntimeError("connection refused")

    out = ce.scan_commitments(since_days=30, llm_fn=_boom)
    assert out["status"] == "ok"
    assert out["candidate_count"] == 0
    assert len(out["errors"]) == 1
    assert "connection refused" in out["errors"][0]["error"]


def test_scan_filters_by_person_id(isolated_duckdb):
    _seed_interactions("p1", "p1 will call")
    _seed_interactions("p2", "p2 will email")

    calls: list[str] = []

    def _llm(prompt: str, model: str) -> str:  # noqa: ARG001
        calls.append(prompt)
        return "[]"

    out = ce.scan_commitments(since_days=30, person_id="p1", llm_fn=_llm)
    assert out["scanned_persons"] == 1
    # Only one prompt sent (for p1)
    assert len(calls) == 1


def test_scan_links_source_interaction_id(isolated_duckdb):
    _seed_interactions("p1", "most recent summary", days_ago=1)
    llm = _mk_llm(json.dumps([{"body": "x", "confidence": 0.9}]))
    out = ce.scan_commitments(since_days=30, llm_fn=llm)
    assert out["candidates"][0]["source_interaction_id"] is not None
