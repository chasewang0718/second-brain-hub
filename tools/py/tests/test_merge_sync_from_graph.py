"""Tests for ``brain_agents.merge_candidates.sync_from_graph``.

We stub the Kuzu side (``_enumerate_shared_identifier_pairs``) so these
tests do not require kuzu to be installed or a graph to be built.
"""

from __future__ import annotations

import pytest

from brain_agents import merge_candidates as mc
from brain_memory.structured import execute, fetch_one, query


@pytest.fixture(autouse=True)
def _clean_tables():
    """Keep merge_candidates + merge_log state isolated for each test."""
    execute("DELETE FROM merge_candidates")
    execute("DELETE FROM merge_log")
    yield
    execute("DELETE FROM merge_candidates")
    execute("DELETE FROM merge_log")


def test_sync_skipped_when_kuzu_missing(monkeypatch):
    def raise_missing():
        raise RuntimeError("kuzu_missing:ModuleNotFoundError")

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", raise_missing)
    out = mc.sync_from_graph(dry_run=True)
    assert out["status"] == "skipped"
    assert "kuzu_missing" in out["reason"]
    assert out["dry_run"] is True


def test_sync_dry_run_does_not_write(monkeypatch):
    def fake_pairs():
        return [
            {"person_a": "p_a", "person_b": "p_b", "kind": "phone", "value": "8613800138000"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=True)
    assert out["status"] == "ok"
    assert out["proposed"] == 1
    assert out["inserted"] == 0
    assert out["samples"][0]["score"] == pytest.approx(0.95)
    assert out["samples"][0]["reason"].startswith("graph:shared_identifier:phone")

    # nothing actually inserted
    rows = query("SELECT COUNT(*) AS c FROM merge_candidates")
    assert int(rows[0]["c"]) == 0


def test_sync_apply_inserts_pending_row(monkeypatch):
    def fake_pairs():
        return [
            {"person_a": "p_a", "person_b": "p_b", "kind": "phone", "value": "8613800138000"},
            {"person_a": "p_a", "person_b": "p_b", "kind": "email", "value": "a@example.com"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=False)
    assert out["status"] == "ok"
    assert out["proposed"] == 1  # dedup to one pair
    assert out["inserted"] == 1

    row = fetch_one(
        "SELECT person_a, person_b, status, reason, score, detail_json "
        "FROM merge_candidates ORDER BY id DESC LIMIT 1"
    )
    assert row is not None
    assert row["person_a"] == "p_a"
    assert row["person_b"] == "p_b"
    assert row["status"] == "pending"
    # kinds are sorted alphabetically in reason
    assert "email" in row["reason"] and "phone" in row["reason"]
    # score is the max of phone (0.95) / email (0.92)
    assert float(row["score"]) == pytest.approx(0.95)


def test_sync_skips_pairs_already_in_merge_log(monkeypatch):
    execute(
        "INSERT INTO merge_log (kept_person_id, absorbed_person_id, reason, detail_json) "
        "VALUES ('p_a', 'p_b', 'test', '{}')",
    )

    def fake_pairs():
        return [
            {"person_a": "p_a", "person_b": "p_b", "kind": "phone", "value": "x"},
            {"person_a": "p_c", "person_b": "p_d", "kind": "phone", "value": "y"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=False)
    assert out["proposed"] == 1  # only p_c/p_d remains
    assert out["inserted"] == 1

    row = fetch_one("SELECT person_a, person_b FROM merge_candidates ORDER BY id DESC LIMIT 1")
    assert row["person_a"] == "p_c" and row["person_b"] == "p_d"


def test_sync_skips_pairs_already_in_merge_candidates(monkeypatch):
    execute(
        "INSERT INTO merge_candidates (person_a, person_b, score, reason, status, detail_json) "
        "VALUES ('p_a', 'p_b', 0.9, 'pre-existing', 'rejected', '{}')",
    )

    def fake_pairs():
        return [
            # (a,b) flipped order — _already_handled_pairs must normalize
            {"person_a": "p_b", "person_b": "p_a", "kind": "phone", "value": "z"},
            {"person_a": "p_e", "person_b": "p_f", "kind": "email", "value": "e@x"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    # Note: fake_pairs returns person_a > person_b which wouldn't happen
    # in real Kuzu query, but we normalize in Python anyway.
    out = mc.sync_from_graph(dry_run=False)
    assert out["proposed"] == 1
    assert out["inserted"] == 1

    # exactly two candidates now: the pre-existing rejected + new e/f
    count = int(query("SELECT COUNT(*) AS c FROM merge_candidates")[0]["c"])
    assert count == 2


def test_sync_unknown_kind_gets_default_score(monkeypatch):
    def fake_pairs():
        return [
            {"person_a": "p_a", "person_b": "p_b", "kind": "weird_kind", "value": "v"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)
    out = mc.sync_from_graph(dry_run=True)
    assert out["samples"][0]["score"] == pytest.approx(mc._GRAPH_DEFAULT_SCORE)
