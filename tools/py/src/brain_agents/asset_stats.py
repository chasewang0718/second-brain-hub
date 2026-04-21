"""B1 · Python port of ``tools/asset/brain-asset-stats.ps1``.

Pure-metadata scan of ``brain_assets_root`` (default
``D:\\second-brain-assets``). Produces a Markdown report at
``<brain_content_root>/04-journal/brain-assets-stats-YYYY-MM-DD.md``
with:

  * total file count + GB
  * top-level directory distribution
  * top-20 extensions by bytes
  * month-over-month distribution by mtime
  * top-10 largest single files

Zero LLM tokens. Safe to run on any machine (paths come from
``paths.yaml``).
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config


EXCLUDE_DIR_TOKENS = ("_migration",)  # skip sub-trees matching any token


def _mb(n: int) -> float:
    return round(n / (1024 * 1024), 1)


def _gb(n: int) -> float:
    return round(n / (1024 * 1024 * 1024), 2)


def _should_skip(relative_parts: tuple[str, ...]) -> bool:
    return any(tok in relative_parts for tok in EXCLUDE_DIR_TOKENS)


def scan_assets(
    assets_root: Path,
    *,
    exclude_tokens: tuple[str, ...] = EXCLUDE_DIR_TOKENS,
) -> dict[str, Any]:
    """Walk ``assets_root`` and collect stats. Symlinks are NOT followed."""
    if not assets_root.exists():
        return {"status": "missing", "assets_root": str(assets_root)}

    total_count = 0
    total_size = 0
    top_dirs: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "size": 0})
    ext_map: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "size": 0})
    month_map: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "size": 0})
    top_large: list[tuple[int, Path]] = []

    for root, dirs, files in os.walk(assets_root, followlinks=False):
        rel = Path(root).relative_to(assets_root)
        parts = rel.parts
        if _should_skip(parts):
            dirs[:] = []
            continue
        # Prune any child dir that matches an exclude token.
        dirs[:] = [d for d in dirs if d not in exclude_tokens]

        top_dir = parts[0] if parts else "(root)"
        for fname in files:
            fpath = Path(root) / fname
            try:
                st = fpath.stat()
            except OSError:
                continue

            total_count += 1
            total_size += st.st_size

            top_dirs[top_dir]["count"] += 1
            top_dirs[top_dir]["size"] += st.st_size

            ext = fpath.suffix.lower() or "(no-ext)"
            ext_map[ext]["count"] += 1
            ext_map[ext]["size"] += st.st_size

            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
            ym = mtime.strftime("%Y-%m")
            month_map[ym]["count"] += 1
            month_map[ym]["size"] += st.st_size

            if len(top_large) < 10:
                top_large.append((st.st_size, fpath))
                top_large.sort(key=lambda t: -t[0])
            elif st.st_size > top_large[-1][0]:
                top_large[-1] = (st.st_size, fpath)
                top_large.sort(key=lambda t: -t[0])

    return {
        "status": "ok",
        "assets_root": str(assets_root),
        "total_count": total_count,
        "total_size": total_size,
        "top_dirs": dict(top_dirs),
        "ext_map": dict(ext_map),
        "month_map": dict(month_map),
        "top_large": [(sz, str(p)) for sz, p in top_large],
    }


def render_markdown(stats: dict[str, Any], *, today: str | None = None) -> str:
    """Render the Markdown report. Mirrors the PS original's columns
    so existing journal consumers don't break.
    """
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_count = int(stats.get("total_count", 0))
    total_size = int(stats.get("total_size", 0))
    total_gb = _gb(total_size)

    lines: list[str] = []
    lines.append("---")
    lines.append(f"title: brain-assets 统计报告 {today}")
    lines.append(f"date: {today}")
    lines.append("tags: [stats, housekeeping, auto-generated]")
    lines.append("---")
    lines.append("")
    lines.append(f"# brain-assets 统计 {today}")
    lines.append("")
    lines.append(f"**总文件数**: {total_count} · **总大小**: {total_gb} GB")
    lines.append("")

    lines.append("## 一级目录分布")
    lines.append("")
    lines.append("| 目录 | 文件数 | 大小 (MB) | 占比 |")
    lines.append("|------|--------|-----------|------|")
    for key, v in sorted(stats.get("top_dirs", {}).items(), key=lambda kv: -kv[1]["size"]):
        pct = round(100 * v["size"] / total_size, 1) if total_size else 0
        lines.append(f"| `{key}/` | {v['count']} | {_mb(v['size'])} | {pct}% |")
    lines.append("")

    lines.append("## 扩展名 Top 20 (按占用大小)")
    lines.append("")
    lines.append("| 扩展 | 文件数 | 大小 (MB) | 占比 |")
    lines.append("|------|--------|-----------|------|")
    sorted_ext = sorted(stats.get("ext_map", {}).items(), key=lambda kv: -kv[1]["size"])[:20]
    for ext, v in sorted_ext:
        pct = round(100 * v["size"] / total_size, 1) if total_size else 0
        lines.append(f"| `{ext}` | {v['count']} | {_mb(v['size'])} | {pct}% |")
    lines.append("")

    lines.append("## 按月分布 (mtime)")
    lines.append("")
    lines.append("| 月份 | 文件数 | 大小 (MB) |")
    lines.append("|------|--------|-----------|")
    for ym in sorted(stats.get("month_map", {})):
        v = stats["month_map"][ym]
        lines.append(f"| {ym} | {v['count']} | {_mb(v['size'])} |")
    lines.append("")

    lines.append("## Top 10 单文件")
    lines.append("")
    lines.append("| 大小 (MB) | 路径 |")
    lines.append("|-----------|------|")
    for sz, path in stats.get("top_large", []):
        lines.append(f"| {_mb(sz)} | `{path}` |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*auto-generated by `brain asset-stats` (Python; 纯元数据, 0 token)*")
    return "\n".join(lines)


def run(
    *,
    assets_root: Path | None = None,
    content_root: Path | None = None,
    write_report: bool = True,
    today: str | None = None,
) -> dict[str, Any]:
    """Scan + render. When ``write_report=True`` also writes the MD to
    ``<content_root>/04-journal/brain-assets-stats-<today>.md`` and
    returns ``report_path`` in the result.
    """
    paths = load_paths_config()["paths"]
    ar = assets_root or Path(paths.get("assets_root") or paths.get("brain_assets_root") or "D:\\second-brain-assets")
    cr = content_root or Path(paths.get("content_root") or paths.get("brain_root") or "D:\\second-brain-content")
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    stats = scan_assets(ar)
    if stats.get("status") != "ok":
        return stats

    out: dict[str, Any] = {
        "status": "ok",
        "assets_root": str(ar),
        "total_count": stats["total_count"],
        "total_size_gb": _gb(stats["total_size"]),
        "top_dirs_count": len(stats["top_dirs"]),
        "months_seen": len(stats["month_map"]),
    }

    if write_report:
        md = render_markdown(stats, today=today)
        report_dir = cr / "04-journal"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"brain-assets-stats-{today}.md"
        report_path.write_text(md, encoding="utf-8")
        out["report_path"] = str(report_path)

    return out
