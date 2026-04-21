"""F3: staleness detection + rebuild_if_stale behaviour.

We exercise the pure mtime-based logic with fake files so most cases
run even without kuzu. The "rebuild actually runs" cases are guarded
by ``importorskip("kuzu")``.
"""

from __future__ import annotations

import os
import time

import pytest

from brain_agents import graph_build


def _touch(path, *, mtime: float | None = None, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_staleness_missing_kuzu(tmp_path, monkeypatch):
    kuzu_dir = tmp_path / "kuzu-graph"
    duckdb_file = tmp_path / "brain-telemetry.duckdb"
    _touch(duckdb_file)

    monkeypatch.setattr(graph_build, "_duckdb_path", lambda: duckdb_file)

    out = graph_build.graph_staleness(kuzu_dir=kuzu_dir)
    assert out["stale"] is True
    assert out["reason"] == "missing"
    assert out["kuzu_mtime"] is None


def test_staleness_no_duckdb(tmp_path, monkeypatch):
    kuzu_dir = tmp_path / "kuzu-graph"
    _touch(kuzu_dir / graph_build.DB_FILENAME)
    monkeypatch.setattr(graph_build, "_duckdb_path", lambda: tmp_path / "missing.duckdb")

    out = graph_build.graph_staleness(kuzu_dir=kuzu_dir)
    assert out["stale"] is False
    assert out["reason"] == "no_duckdb"


def test_staleness_duckdb_newer(tmp_path, monkeypatch):
    kuzu_file = tmp_path / "kuzu-graph" / graph_build.DB_FILENAME
    duckdb_file = tmp_path / "brain-telemetry.duckdb"
    _touch(kuzu_file, mtime=time.time() - 3600)  # 1h old
    _touch(duckdb_file, mtime=time.time())  # just now

    monkeypatch.setattr(graph_build, "_duckdb_path", lambda: duckdb_file)

    out = graph_build.graph_staleness(kuzu_dir=kuzu_file.parent)
    assert out["stale"] is True
    assert out["reason"] == "duckdb_newer"
    assert out["lag_seconds"] >= 3000


def test_staleness_fresh(tmp_path, monkeypatch):
    kuzu_file = tmp_path / "kuzu-graph" / graph_build.DB_FILENAME
    duckdb_file = tmp_path / "brain-telemetry.duckdb"
    t = time.time()
    _touch(duckdb_file, mtime=t - 100)
    _touch(kuzu_file, mtime=t)  # newer than DuckDB

    monkeypatch.setattr(graph_build, "_duckdb_path", lambda: duckdb_file)

    out = graph_build.graph_staleness(kuzu_dir=kuzu_file.parent)
    assert out["stale"] is False
    assert out["reason"] == "fresh"


def test_staleness_older_than_max(tmp_path, monkeypatch):
    """Max-age check only triggers when DuckDB isn't already newer."""
    kuzu_file = tmp_path / "kuzu-graph" / graph_build.DB_FILENAME
    duckdb_file = tmp_path / "brain-telemetry.duckdb"
    t = time.time()
    _touch(duckdb_file, mtime=t - 8 * 3600)  # 8h old (older than kuzu)
    _touch(kuzu_file, mtime=t - 4 * 3600)  # 4h old; fresher than DuckDB

    monkeypatch.setattr(graph_build, "_duckdb_path", lambda: duckdb_file)

    # With no max-age: fresh
    out = graph_build.graph_staleness(kuzu_dir=kuzu_file.parent)
    assert out["reason"] == "fresh"

    # With a 1h max-age: stale by wall clock
    out = graph_build.graph_staleness(kuzu_dir=kuzu_file.parent, max_age_seconds=3600)
    assert out["stale"] is True
    assert out["reason"] == "older_than_max"
    assert out["age_seconds"] >= 3600


def test_rebuild_if_stale_no_rebuild_when_fresh(tmp_path, monkeypatch):
    kuzu_file = tmp_path / "kuzu-graph" / graph_build.DB_FILENAME
    duckdb_file = tmp_path / "brain-telemetry.duckdb"
    t = time.time()
    _touch(duckdb_file, mtime=t - 100)
    _touch(kuzu_file, mtime=t)

    monkeypatch.setattr(graph_build, "_duckdb_path", lambda: duckdb_file)

    called = {"n": 0}

    def fake_build(kuzu_dir=None):
        called["n"] += 1
        return {"persons": 0}

    monkeypatch.setattr(graph_build, "build_graph", fake_build)

    out = graph_build.rebuild_if_stale(kuzu_dir=kuzu_file.parent)
    assert out["status"] == "ok"
    assert out["rebuilt"] is False
    assert called["n"] == 0


def test_rebuild_if_stale_rebuilds_when_duckdb_newer(tmp_path, monkeypatch):
    kuzu_file = tmp_path / "kuzu-graph" / graph_build.DB_FILENAME
    duckdb_file = tmp_path / "brain-telemetry.duckdb"
    _touch(kuzu_file, mtime=time.time() - 3600)
    _touch(duckdb_file, mtime=time.time())

    monkeypatch.setattr(graph_build, "_duckdb_path", lambda: duckdb_file)

    called = {"n": 0}

    def fake_build(kuzu_dir=None):
        called["n"] += 1
        return {"persons": 42, "interacted_edges": 10}

    monkeypatch.setattr(graph_build, "build_graph", fake_build)

    out = graph_build.rebuild_if_stale(kuzu_dir=kuzu_file.parent)
    assert out["status"] == "ok"
    assert out["rebuilt"] is True
    assert out["reason"] == "duckdb_newer"
    assert out["stats"]["persons"] == 42
    assert called["n"] == 1


def test_rebuild_if_stale_force_even_when_fresh(tmp_path, monkeypatch):
    kuzu_file = tmp_path / "kuzu-graph" / graph_build.DB_FILENAME
    duckdb_file = tmp_path / "brain-telemetry.duckdb"
    t = time.time()
    _touch(duckdb_file, mtime=t - 100)
    _touch(kuzu_file, mtime=t)

    monkeypatch.setattr(graph_build, "_duckdb_path", lambda: duckdb_file)

    called = {"n": 0}

    def fake_build(kuzu_dir=None):
        called["n"] += 1
        return {"persons": 1}

    monkeypatch.setattr(graph_build, "build_graph", fake_build)

    out = graph_build.rebuild_if_stale(kuzu_dir=kuzu_file.parent, force=True)
    assert out["rebuilt"] is True
    assert out["reason"] == "forced"
    assert called["n"] == 1


def test_rebuild_if_stale_skipped_when_build_raises(tmp_path, monkeypatch):
    kuzu_dir = tmp_path / "kuzu-graph"
    duckdb_file = tmp_path / "brain-telemetry.duckdb"
    _touch(duckdb_file)

    monkeypatch.setattr(graph_build, "_duckdb_path", lambda: duckdb_file)

    def raise_missing(kuzu_dir=None):
        raise RuntimeError("kuzu_missing:ImportError")

    monkeypatch.setattr(graph_build, "build_graph", raise_missing)

    out = graph_build.rebuild_if_stale(kuzu_dir=kuzu_dir)
    assert out["status"] == "skipped"
    assert "kuzu_missing" in out["reason"]
