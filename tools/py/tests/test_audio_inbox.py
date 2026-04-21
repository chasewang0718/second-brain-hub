"""Smoke tests for brain_agents.audio_inbox.

Covers (without requiring faster-whisper to be installed):
- unsupported extension skipped
- missing file skipped
- happy path writes a pointer card even when ASR is pending
- ingest_audio_paths copies external files by default; --no-copy keeps
  originals in place
- inbox directory limit is respected
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain_agents import audio_inbox


# Minimal RIFF/WAVE header (44 bytes) so stat()/sha256 work on a plausible file.
_WAV_HEADER = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox-audio"
    content = tmp_path / "content"
    queue = tmp_path / "queue"
    inbox.mkdir()
    content.mkdir()
    queue.mkdir()
    fake = {
        "audio_inbox_dir": str(inbox),
        "pdf_inbox_dir": str(inbox),
        "content_root": str(content),
        "cursor_queue_dir": str(queue),
    }
    monkeypatch.setattr(audio_inbox, "_paths", lambda: fake)
    return {"inbox": inbox, "content": content, "queue": queue}


def _write_wav(path: Path) -> None:
    path.write_bytes(_WAV_HEADER)


def test_unsupported_ext_skipped(sandbox, tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("nope", encoding="utf-8")
    r = audio_inbox.ingest_audio(p)
    assert r["status"] == "skipped"
    assert r["reason"].startswith("unsupported_ext")


def test_missing_file_skipped(sandbox, tmp_path):
    r = audio_inbox.ingest_audio(tmp_path / "ghost.mp3")
    assert r["status"] == "skipped"
    assert r["reason"] == "missing"


def test_pointer_card_written_even_without_faster_whisper(sandbox):
    f = sandbox["inbox"] / "voice-memo.wav"
    _write_wav(f)
    r = audio_inbox.ingest_audio(f)
    assert r["status"] == "ok"
    assert r["asr_status"] in {"ok", "pending"}
    pointer = Path(r["pointer_path"])
    assert pointer.exists()
    text = pointer.read_text(encoding="utf-8")
    assert "asset_type: audio" in text
    assert "asr_status:" in text
    if r["asr_status"] != "ok":
        assert "cursor_queue_task" in r
        assert Path(r["cursor_queue_task"]).exists()


def test_ingest_audio_paths_copies_external(sandbox, tmp_path):
    src = tmp_path / "external.wav"
    _write_wav(src)
    results = audio_inbox.ingest_audio_paths([src])
    assert len(results) == 1
    r = results[0]
    assert r["status"] == "ok"
    assert r["source_path"] == str(src)
    inbox_path = Path(r["inbox_path"])
    assert inbox_path.parent == sandbox["inbox"]
    assert inbox_path.exists()


def test_ingest_audio_paths_no_copy(sandbox, tmp_path):
    src = tmp_path / "stay_here.wav"
    _write_wav(src)
    results = audio_inbox.ingest_audio_paths([src], copy_into_inbox=False)
    assert results[0]["status"] == "ok"
    assert Path(results[0]["inbox_path"]) == src
    assert not (sandbox["inbox"] / "stay_here.wav").exists()


def test_ingest_audio_inbox_limit(sandbox):
    for i in range(3):
        _write_wav(sandbox["inbox"] / f"mem-{i}.wav")
    results = audio_inbox.ingest_audio_inbox(limit=2)
    assert len(results) == 2
    assert all(r["status"] == "ok" for r in results)
