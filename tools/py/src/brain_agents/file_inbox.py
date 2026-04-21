"""A3 MVP file inbox pipeline (PDF only)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config


def _paths() -> dict[str, str]:
    return load_paths_config()["paths"]


def _pdf_inbox_dir() -> Path:
    return Path(_paths()["pdf_inbox_dir"])


def _content_root() -> Path:
    return Path(_paths()["content_root"])


def _cursor_queue_dir() -> Path:
    return Path(_paths()["cursor_queue_dir"])


def _slug(raw: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw.strip())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "asset"


def _sha256_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _human_size(size_bytes: int) -> str:
    size = float(size_bytes)
    units = ["B", "KB", "MB", "GB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.2f} {units[idx]}"


@dataclass
class PdfIngestResult:
    source_path: str
    pointer_path: str
    status: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "pointer_path": self.pointer_path,
            "status": self.status,
            "reason": self.reason,
        }


def _write_cursor_queue_task(pdf_path: Path, reason: str) -> Path:
    queue_dir = _cursor_queue_dir()
    queue_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    task_path = queue_dir / f"pdf-ingest-{stamp}-{_slug(pdf_path.stem)}.md"
    task_path.write_text(
        "\n".join(
            [
                "---",
                "task: pdf_ingest_fallback",
                f"created_utc: {datetime.now(UTC).isoformat()}",
                f"source_path: {pdf_path}",
                f"reason: {reason}",
                "---",
                "",
                "# PDF Ingest Fallback",
                "",
                f"- Source: `{pdf_path}`",
                f"- Reason: `{reason}`",
                "- Requested action: generate Tier A pointer card manually in `D:\\second-brain-content`.",
            ]
        ),
        encoding="utf-8",
    )
    return task_path


def _pointer_card_path(pdf_path: Path) -> Path:
    root = _content_root() / "03-projects" / "inbox-auto-pdf"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"asset-{_slug(pdf_path.stem)}.md"


def _build_pointer_card(pdf_path: Path) -> str:
    stat = pdf_path.stat()
    return "\n".join(
        [
            "---",
            f"title: {pdf_path.stem}",
            "asset_type: pdf",
            f"asset_path: {pdf_path}",
            f"asset_size: {_human_size(stat.st_size)}",
            f"asset_sha256: {_sha256_prefix(pdf_path)}",
            "source_original_path: unknown",
            f"created: {datetime.now(UTC).date().isoformat()}",
            "tags: [asset, pdf, pointer-card, auto-ingest]",
            "---",
            "",
            f"# {pdf_path.stem}",
            "",
            "## AI 摘要",
            "- [TODO] A3 MVP 暂未解析 PDF 正文，仅完成指针卡生成。",
            "",
            "## 关键词",
            "- pdf",
            "- inbox",
            "",
            "## 我的备注",
            "",
        ]
    )


def ingest_pdf(pdf_path: Path) -> dict[str, Any]:
    try:
        if not pdf_path.exists():
            return PdfIngestResult(str(pdf_path), "", "skipped", "missing").to_dict()
        if pdf_path.suffix.lower() != ".pdf":
            return PdfIngestResult(str(pdf_path), "", "skipped", "not_pdf").to_dict()
        pointer = _pointer_card_path(pdf_path)
        pointer.write_text(_build_pointer_card(pdf_path), encoding="utf-8")
        return PdfIngestResult(str(pdf_path), str(pointer), "ok").to_dict()
    except Exception as exc:
        task_path = _write_cursor_queue_task(pdf_path, str(exc))
        return PdfIngestResult(str(pdf_path), str(task_path), "queued", str(exc)).to_dict()


def ingest_pdf_inbox(limit: int = 1) -> list[dict[str, Any]]:
    pdfs = sorted(_pdf_inbox_dir().glob("*.pdf"))
    if limit > 0:
        pdfs = pdfs[:limit]
    return [ingest_pdf(path) for path in pdfs]

