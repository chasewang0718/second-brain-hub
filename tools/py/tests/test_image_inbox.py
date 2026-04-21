"""Smoke tests for brain_agents.image_inbox.

Covers (without requiring paddleocr to be installed):
- unsupported extension is skipped
- missing file is skipped
- happy path writes a pointer card even when OCR is pending (paddleocr
  absent / empty result); a cursor_queue fallback task is recorded.
- ingest_image_paths copies external files into image_inbox_dir by default
  and respects ``--no-copy`` semantics (copy_into_inbox=False).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain_agents import image_inbox


# Minimal valid 1x1 PNG so Path.stat().st_size > 0 and sha256 works.
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "89000000114944415478da636464606060000000400001208145c9d30000000049454e44ae426082"
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox-image"
    content = tmp_path / "content"
    queue = tmp_path / "queue"
    inbox.mkdir()
    content.mkdir()
    queue.mkdir()
    fake = {
        "image_inbox_dir": str(inbox),
        "pdf_inbox_dir": str(inbox),  # fallback key
        "content_root": str(content),
        "cursor_queue_dir": str(queue),
    }
    monkeypatch.setattr(image_inbox, "_paths", lambda: fake)
    return {"inbox": inbox, "content": content, "queue": queue}


def _write_png(path: Path) -> None:
    path.write_bytes(_PNG_1x1)


def test_unsupported_ext_skipped(sandbox, tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("nope", encoding="utf-8")
    r = image_inbox.ingest_image(p)
    assert r["status"] == "skipped"
    assert r["reason"].startswith("unsupported_ext")


def test_missing_file_skipped(sandbox, tmp_path):
    r = image_inbox.ingest_image(tmp_path / "ghost.png")
    assert r["status"] == "skipped"
    assert r["reason"] == "missing"


def test_pointer_card_written_even_without_paddleocr(sandbox, tmp_path):
    img = sandbox["inbox"] / "screen.png"
    _write_png(img)
    r = image_inbox.ingest_image(img)
    assert r["status"] == "ok"
    assert r["ocr_status"] in {"ok", "pending"}
    pointer = Path(r["pointer_path"])
    assert pointer.exists()
    text = pointer.read_text(encoding="utf-8")
    assert "asset_type: image" in text
    assert "ocr_status:" in text
    if r["ocr_status"] != "ok":
        # pending/error path must enqueue a cursor_queue task
        assert "cursor_queue_task" in r
        assert Path(r["cursor_queue_task"]).exists()


def test_ingest_image_paths_copies_external(sandbox, tmp_path):
    src = tmp_path / "external.png"
    _write_png(src)
    results = image_inbox.ingest_image_paths([src])
    assert len(results) == 1
    r = results[0]
    assert r["status"] == "ok"
    assert r["source_path"] == str(src)
    inbox_path = Path(r["inbox_path"])
    assert inbox_path.parent == sandbox["inbox"]
    assert inbox_path.exists()


def test_ingest_image_paths_no_copy(sandbox, tmp_path):
    src = tmp_path / "stay_here.png"
    _write_png(src)
    results = image_inbox.ingest_image_paths([src], copy_into_inbox=False)
    assert results[0]["status"] == "ok"
    assert Path(results[0]["inbox_path"]) == src
    assert not (sandbox["inbox"] / "stay_here.png").exists()


def test_ingest_image_inbox_limit(sandbox):
    for i in range(3):
        _write_png(sandbox["inbox"] / f"img-{i}.png")
    results = image_inbox.ingest_image_inbox(limit=2)
    assert len(results) == 2
    assert all(r["status"] == "ok" for r in results)
