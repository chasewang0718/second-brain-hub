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


def _seed_snapshots(tmp_path: Path) -> Path:
    """Drop 4 snapshots spread over 4 hours with different labels."""
    src = _fake_duckdb(tmp_path)
    dest = tmp_path / "backup"
    base = datetime(2026, 4, 22, 10, 0, 0, tzinfo=timezone.utc)
    labels = [
        ("manual-pre-migrate", 0),
        ("ios-addressbook-apply", 60),
        ("whatsapp-apply", 120),
        ("ios-addressbook-redo", 180),
    ]
    for lbl, offset_min in labels:
        ingest_backup.snapshot_duckdb(
            label=lbl,
            source=src,
            dest_root=dest,
            now=base.replace(minute=0) + _minutes(offset_min),
        )
    return dest


def _minutes(n: int):
    from datetime import timedelta

    return timedelta(minutes=n)


def test_latest_snapshot_prefers_label_prefix(tmp_path):
    dest = _seed_snapshots(tmp_path)
    # Pretend "now" is 10 minutes after the newest (ios-addressbook-redo @ 13:00).
    now = datetime(2026, 4, 22, 13, 10, 0, tzinfo=timezone.utc)
    out = ingest_backup.latest_snapshot(
        label_prefix="ios-addressbook",
        max_age_minutes=240,
        now=now,
        dest_root=dest,
    )
    assert out is not None
    assert out["label"] == "ios-addressbook-redo"


def test_latest_snapshot_respects_age_cap(tmp_path):
    dest = _seed_snapshots(tmp_path)
    # "now" is 3 hours after the latest ios-addressbook run (13:00 + 3h = 16:00).
    now = datetime(2026, 4, 22, 16, 0, 0, tzinfo=timezone.utc)
    # Cap 120 min → newest ios-addressbook is 180 min old, out of window.
    out = ingest_backup.latest_snapshot(
        label_prefix="ios-addressbook",
        max_age_minutes=120,
        now=now,
        dest_root=dest,
    )
    assert out is None
    # Raise the cap → same run is returned.
    out2 = ingest_backup.latest_snapshot(
        label_prefix="ios-addressbook",
        max_age_minutes=240,
        now=now,
        dest_root=dest,
    )
    assert out2 is not None and out2["label"] == "ios-addressbook-redo"


def test_latest_snapshot_prefix_miss_returns_none(tmp_path):
    dest = _seed_snapshots(tmp_path)
    now = datetime(2026, 4, 22, 13, 10, 0, tzinfo=timezone.utc)
    out = ingest_backup.latest_snapshot(
        label_prefix="wechat",
        max_age_minutes=0,  # no cap
        now=now,
        dest_root=dest,
    )
    assert out is None


def test_latest_snapshot_falls_back_to_newest_when_no_prefix(tmp_path):
    dest = _seed_snapshots(tmp_path)
    now = datetime(2026, 4, 22, 13, 10, 0, tzinfo=timezone.utc)
    out = ingest_backup.latest_snapshot(
        label_prefix=None,
        max_age_minutes=240,
        now=now,
        dest_root=dest,
    )
    assert out is not None
    assert out["label"] == "ios-addressbook-redo"  # newest absolute


def test_latest_snapshot_empty_returns_none(tmp_path):
    out = ingest_backup.latest_snapshot(
        label_prefix=None,
        max_age_minutes=0,
        dest_root=tmp_path / "empty-backup",
    )
    assert out is None


def test_short_descriptor_keeps_audit_fields():
    desc = {
        "status": "ok",
        "source": "D:/…/brain-telemetry.duckdb",
        "snapshot": "D:/…/backup/telemetry/20260422-104530-ios.duckdb",
        "sha256": "abc123",
        "bytes": 123456,
        "elapsed_ms": 12.3,
        "label": "ios-addressbook",
        "ts_utc": "20260422-104530",
    }
    short = ingest_backup._short_descriptor(desc)
    assert short == {
        "snapshot": desc["snapshot"],
        "sha256": "abc123",
        "ts_utc": "20260422-104530",
        "label": "ios-addressbook",
        "bytes": 123456,
    }


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
