"""B-ING-0 · ingest_backup snapshot + pointer-log."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brain_agents import ingest_backup


def _fake_duckdb(tmp_path: Path, content: bytes = b"duckdb-contents") -> Path:
    f = tmp_path / "src" / "brain-telemetry.duckdb"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(content)
    return f


def test_snapshot_writes_copy_sha256_pointer(tmp_path):
    src = _fake_duckdb(tmp_path)
    dest = tmp_path / "backup"
    now = datetime(2026, 4, 21, 21, 54, 30, tzinfo=timezone.utc)

    out = ingest_backup.snapshot_duckdb(
        label="ios-addressbook",
        source=src,
        dest_root=dest,
        now=now,
    )
    assert out["status"] == "ok"
    snap = Path(out["snapshot"])
    assert snap.exists()
    assert snap.read_bytes() == src.read_bytes()
    # sha256 sidecar
    sha_file = snap.with_name(snap.stem + ".sha256.txt")
    assert sha_file.exists()
    assert out["sha256"] in sha_file.read_text(encoding="utf-8")
    # pointer-log.jsonl
    log = snap.parent / "pointer-log.jsonl"
    assert log.exists()
    line = log.read_text(encoding="utf-8").strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["label"] == "ios-addressbook"
    assert parsed["ts_utc"] == "20260421-215430"
    # filename carries stamp + label
    assert snap.name == "20260421-215430-ios-addressbook.duckdb"


def test_snapshot_missing_source(tmp_path):
    out = ingest_backup.snapshot_duckdb(
        label="x",
        source=tmp_path / "does-not-exist.duckdb",
        dest_root=tmp_path / "backup",
    )
    assert out["status"] == "source_missing"


def test_label_sanitized(tmp_path):
    src = _fake_duckdb(tmp_path)
    out = ingest_backup.snapshot_duckdb(
        label="bad/label with spaces!",
        source=src,
        dest_root=tmp_path / "backup",
    )
    # slashes and spaces become dashes; leading/trailing dashes stripped
    assert "/" not in out["label"]
    assert " " not in out["label"]
    assert out["label"]  # non-empty


def test_list_snapshots_newest_first(tmp_path):
    src = _fake_duckdb(tmp_path)
    dest = tmp_path / "backup"
    for i in range(3):
        ingest_backup.snapshot_duckdb(
            label=f"run-{i}",
            source=src,
            dest_root=dest,
            now=datetime(2026, 4, 21, 10, i, 0, tzinfo=timezone.utc),
        )
    out = ingest_backup.list_snapshots(dest_root=dest, limit=10)
    assert len(out) == 3
    assert out[0]["label"] == "run-2"
    assert out[-1]["label"] == "run-0"
