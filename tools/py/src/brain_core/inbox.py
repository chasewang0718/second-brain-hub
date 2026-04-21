"""Read inbox captures from content_root/99-inbox."""

from __future__ import annotations

from pathlib import Path

from brain_core.config import load_paths_config


def _inbox_dir() -> Path:
    content_root = Path(load_paths_config()["paths"]["content_root"])
    return content_root / "99-inbox"


def _title_from_markdown(text: str) -> str:
    lines = text.lstrip("\ufeff").splitlines()
    in_frontmatter = False
    if lines and lines[0].strip() == "---":
        in_frontmatter = True
        lines = lines[1:]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if in_frontmatter and stripped == "---":
            in_frontmatter = False
            continue
        if in_frontmatter:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:80]
        return stripped[:80]
    return ""


def list_inbox(limit: int = 20) -> list[dict]:
    inbox = _inbox_dir()
    if not inbox.exists():
        return []
    files = sorted(inbox.glob("paste-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows: list[dict] = []
    for p in files[:limit]:
        text = p.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
        rows.append(
            {
                "name": p.name,
                "mtime": p.stat().st_mtime,
                "chars": len(text),
                "title": _title_from_markdown(text),
            }
        )
    return rows

