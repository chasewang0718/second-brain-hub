"""B-ING-0 · jsonl ingest event log."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from brain_agents import ingest_log


def test_log_apply_writes_jsonl(tmp_path):
    src = tmp_path / "fake.sqlite"
    src.write_bytes(b"hello")
    out = ingest_log.log_ingest_event(
        source="ios_addressbook",
        mode="apply",
        stats={"status": "ok", "persons_created": 3, "identifiers_added": 7},
        source_path=src,
        elapsed_ms=123.4,
        backup={"snapshot": "x.duckdb", "sha256": "abc"},
        now=datetime(2026, 4, 21, 22, 0, 0, tzinfo=timezone.utc),
        log_dir=tmp_path,
    )
    assert out["status"] == "logged"
    log_file = tmp_path / "ingest-2026-04-21.jsonl"
    assert log_file.exists()
    line = log_file.read_text(encoding="utf-8").strip()
    ev = json.loads(line)
    assert ev["source"] == "ios_addressbook"
    assert ev["mode"] == "apply"
    assert ev["persons_added"] == 3
    assert ev["identifiers_added"] == 7
    assert ev["elapsed_ms"] == 123.4
    assert ev["source_sha256"]  # sha was computed for apply
    assert ev["backup"]["sha256"] == "abc"


def test_log_dry_run_skips_sha(tmp_path):
    src = tmp_path / "fake.sqlite"
    src.write_bytes(b"hello")
    out = ingest_log.log_ingest_event(
        source="whatsapp_ios",
        mode="dry_run",
        stats={"status": "dry_run"},
        source_path=src,
        log_dir=tmp_path,
    )
    assert out["status"] == "logged"
    ev = out["event"]
    assert ev["mode"] == "dry_run"
    assert ev["source_sha256"] is None


def test_log_appends_not_overwrites(tmp_path):
    for i in range(3):
        ingest_log.log_ingest_event(
            source="whatsapp_ios",
            mode="apply",
            stats={"status": "ok", "inserted": i},
            log_dir=tmp_path,
            now=datetime(2026, 4, 21, tzinfo=timezone.utc),
        )
    log_file = tmp_path / "ingest-2026-04-21.jsonl"
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


def test_log_skipped_on_oserror(tmp_path, monkeypatch):
    """Log write failures must not raise — ingest itself is the source of truth."""
    def _raise(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", _raise)
    out = ingest_log.log_ingest_event(
        source="x",
        mode="apply",
        stats={"status": "ok"},
        log_dir=tmp_path,
    )
    assert out["status"] == "log_skipped"
    assert "disk full" in out["reason"]
