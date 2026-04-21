"""A3 MVP file inbox pipeline (PDF only)."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config


def _brain_exclude_patterns() -> list[str]:
    home = Path.home() / ".brain-exclude.txt"
    if not home.exists():
        return []
    out: list[str] = []
    for line in home.read_text(encoding="utf-8", errors="ignore").splitlines():
        item = line.strip()
        if item and not item.startswith("#"):
            out.append(item.lower())
    return out


def _is_excluded(pdf_path: Path) -> str:
    patterns = _brain_exclude_patterns()
    p = str(pdf_path).lower()
    for pat in patterns:
        if pat in p:
            return pat
    return ""


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


def _copy_into_inbox(pdf_path: Path) -> Path:
    """If pdf_path is outside pdf_inbox_dir, copy it in with a collision-safe name."""
    inbox = _pdf_inbox_dir()
    inbox.mkdir(parents=True, exist_ok=True)
    try:
        resolved_src = pdf_path.resolve()
        resolved_inbox = inbox.resolve()
    except OSError:
        resolved_src = pdf_path
        resolved_inbox = inbox
    try:
        inside = str(resolved_src).lower().startswith(str(resolved_inbox).lower() + os.sep.lower())
    except Exception:
        inside = False
    if inside:
        return resolved_src
    target = inbox / pdf_path.name
    if target.exists():
        stem = pdf_path.stem
        suffix = pdf_path.suffix
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        target = inbox / f"{stem}-{stamp}{suffix}"
    shutil.copy2(pdf_path, target)
    return target


def ingest_pdf(pdf_path: Path) -> dict[str, Any]:
    try:
        if not pdf_path.exists():
            return PdfIngestResult(str(pdf_path), "", "skipped", "missing").to_dict()
        if pdf_path.suffix.lower() != ".pdf":
            return PdfIngestResult(str(pdf_path), "", "skipped", "not_pdf").to_dict()
        pattern = _is_excluded(pdf_path)
        if pattern:
            return PdfIngestResult(
                str(pdf_path), "", "skipped", f"blacklist:{pattern}"
            ).to_dict()
        pointer = _pointer_card_path(pdf_path)
        pointer.write_text(_build_pointer_card(pdf_path), encoding="utf-8")
        return PdfIngestResult(str(pdf_path), str(pointer), "ok").to_dict()
    except Exception as exc:
        task_path = _write_cursor_queue_task(pdf_path, str(exc))
        return PdfIngestResult(str(pdf_path), str(task_path), "queued", str(exc)).to_dict()


def ingest_pdf_paths(paths: list[str | Path], copy_into_inbox: bool = True) -> list[dict[str, Any]]:
    """Ingest an explicit list of PDF paths.

    When copy_into_inbox is True, a file that lives outside pdf_inbox_dir is first
    copied into it so the original tree stays untouched. The pointer card is then
    generated against the in-inbox copy.
    """
    results: list[dict[str, Any]] = []
    for raw in paths:
        try:
            src = Path(raw).expanduser()
        except Exception as exc:
            results.append(
                PdfIngestResult(str(raw), "", "skipped", f"bad_path:{exc}").to_dict()
            )
            continue
        if src.suffix.lower() != ".pdf":
            results.append(
                PdfIngestResult(str(src), "", "skipped", "not_pdf").to_dict()
            )
            continue
        if not src.exists():
            results.append(
                PdfIngestResult(str(src), "", "skipped", "missing").to_dict()
            )
            continue
        pattern = _is_excluded(src)
        if pattern:
            results.append(
                PdfIngestResult(str(src), "", "skipped", f"blacklist:{pattern}").to_dict()
            )
            continue
        try:
            target = _copy_into_inbox(src) if copy_into_inbox else src
        except Exception as exc:
            results.append(
                PdfIngestResult(str(src), "", "skipped", f"copy_failed:{exc}").to_dict()
            )
            continue
        result = ingest_pdf(target)
        result["source_path"] = str(src)
        result["inbox_path"] = str(target)
        results.append(result)
    return results


def ingest_pdf_inbox(limit: int = 1) -> list[dict[str, Any]]:
    pdfs = sorted(_pdf_inbox_dir().glob("*.pdf"))
    if limit > 0:
        pdfs = pdfs[:limit]
    return [ingest_pdf(path) for path in pdfs]

