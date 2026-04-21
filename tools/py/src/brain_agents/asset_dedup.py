"""B1 · Python port of ``tools/asset/brain-asset-dedup.ps1``.

Two-pass SHA256 duplicate finder against ``brain_assets_root``.

Pass 1: group by file size (cheap). Only groups with ``count > 1`` need
hashing (if two files differ in size they CANNOT be byte-identical).

Pass 2: compute SHA256 for each same-size candidate, group by hash.
Groups with ``count > 1`` are real duplicates.

Writes two reports to ``<assets_root>/_migration/``:
  * ``dedup-YYYY-MM-DD.tsv`` (machine-readable, one row per file)
  * ``dedup-YYYY-MM-DD.md`` (human-readable, grouped & sorted by size)

**Never deletes anything**. The PS original had a ``-Execute`` switch
but it was never wired up to actually delete; we keep the same
contract — this module is read-only.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config


DEFAULT_MIN_BYTES = 10 * 1024  # 10 KB — matches the PS default


def _kb(n: int) -> float:
    return round(n / 1024, 1)


def _mb(n: int) -> float:
    return round(n / (1024 * 1024), 1)


def _should_skip_path(relative_parts: tuple[str, ...], *, include_inbox: bool) -> bool:
    if "_migration" in relative_parts:
        return True
    if not include_inbox and any(p.startswith("99-inbox") for p in relative_parts):
        return True
    return False


def _sha256_file(path: Path, *, chunk: int = 1024 * 1024) -> str | None:
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while True:
                buf = fh.read(chunk)
                if not buf:
                    break
                h.update(buf)
    except OSError:
        return None
    return h.hexdigest()


def scan_duplicates(
    assets_root: Path,
    *,
    min_bytes: int = DEFAULT_MIN_BYTES,
    include_inbox: bool = False,
) -> dict[str, Any]:
    """Two-pass duplicate scan. Returns a structured dict — render it
    with :func:`render_reports` or consume it programmatically.
    """
    if not assets_root.exists():
        return {"status": "missing", "assets_root": str(assets_root)}

    # Pass 1: bucket by size
    size_buckets: dict[int, list[Path]] = defaultdict(list)
    scanned = 0
    for root, dirs, files in os.walk(assets_root, followlinks=False):
        rel_parts = Path(root).relative_to(assets_root).parts
        if _should_skip_path(rel_parts, include_inbox=include_inbox):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not _should_skip_path(rel_parts + (d,), include_inbox=include_inbox)]
        for fname in files:
            fpath = Path(root) / fname
            try:
                size = fpath.stat().st_size
            except OSError:
                continue
            if size < min_bytes:
                continue
            scanned += 1
            size_buckets[size].append(fpath)

    hash_candidates = [paths for paths in size_buckets.values() if len(paths) > 1]
    candidates_count = sum(len(paths) for paths in hash_candidates)

    # Pass 2: hash only same-size files
    hash_buckets: dict[str, list[Path]] = defaultdict(list)
    hashed = 0
    for paths in hash_candidates:
        for p in paths:
            sha = _sha256_file(p)
            if sha is None:
                continue
            hash_buckets[sha].append(p)
            hashed += 1

    dup_groups = [
        {"hash": h, "paths": paths, "size": paths[0].stat().st_size}
        for h, paths in hash_buckets.items()
        if len(paths) > 1
    ]
    # Sort groups by wasted bytes desc (size * (count - 1))
    dup_groups.sort(key=lambda g: -(g["size"] * (len(g["paths"]) - 1)))

    redundant_bytes = sum(g["size"] * (len(g["paths"]) - 1) for g in dup_groups)
    redundant_files = sum(len(g["paths"]) - 1 for g in dup_groups)

    return {
        "status": "ok",
        "assets_root": str(assets_root),
        "min_bytes": int(min_bytes),
        "include_inbox": bool(include_inbox),
        "scanned": scanned,
        "same_size_candidates": candidates_count,
        "hashed": hashed,
        "groups": dup_groups,
        "redundant_files": redundant_files,
        "redundant_bytes": redundant_bytes,
    }


def _suggest_keep(paths: list[Path]) -> list[Path]:
    """Sort so the first entry is the "keep" suggestion: shortest path,
    tie-break on filename alphabetically.
    """
    return sorted(paths, key=lambda p: (len(str(p)), p.name))


def render_tsv(scan: dict[str, Any]) -> str:
    lines = ["hash\tsize_kb\tcount\tpath\tkeep_suggestion"]
    for g in scan.get("groups", []):
        sorted_paths = _suggest_keep(list(g["paths"]))
        keep = sorted_paths[0]
        for p in sorted_paths:
            mark = "KEEP" if p == keep else "DUP"
            lines.append(
                f"{g['hash'][:12]}\t{_kb(g['size'])}\t{len(g['paths'])}\t{p}\t{mark}"
            )
    return "\n".join(lines) + "\n"


def render_markdown(scan: dict[str, Any], *, today: str | None = None, max_groups: int = 200) -> str:
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    groups = scan.get("groups", [])

    lines: list[str] = []
    lines.append("---")
    lines.append(f"title: brain-assets 去重报告 {today}")
    lines.append(f"date: {today}")
    lines.append("tags: [dedup, housekeeping, auto-generated]")
    lines.append("---")
    lines.append("")
    lines.append(f"# brain-assets 去重候选 {today}")
    lines.append("")

    inbox_note = "" if scan.get("include_inbox") else " 和 `99-inbox/`"
    lines.append(
        f"扫了 **{scan.get('scanned', 0)}** 个文件 "
        f"(过滤掉 <{_kb(scan.get('min_bytes', 0))} KB 的小文件{inbox_note})."
    )
    lines.append("")

    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 重复组数: **{len(groups)}**")
    lines.append(f"- 冗余文件数: **{scan.get('redundant_files', 0)}** (如全删可释放)")
    lines.append(f"- 冗余总大小: **{_mb(scan.get('redundant_bytes', 0))} MB**")
    lines.append("")

    if not groups:
        lines.append("*没找到任何重复文件.*")
        lines.append("")
        return "\n".join(lines)

    lines.append("## 使用说明")
    lines.append("")
    lines.append("- 每组标 `KEEP` 的是建议保留 (路径最短 / 命名最规整的那一个)")
    lines.append("- 标 `dup` 的是冗余, 人工 review 后可考虑删")
    lines.append("- 默认不自动删; 本工具 **只做报告, 不碰文件**")
    lines.append("")

    for i, g in enumerate(groups[:max_groups], start=1):
        sorted_paths = _suggest_keep(list(g["paths"]))
        keep = sorted_paths[0]
        lines.append(f"### 组 {i} · {_kb(g['size'])} KB × {len(g['paths'])} 份")
        lines.append("")
        for p in sorted_paths:
            mark = "**KEEP**" if p == keep else "dup"
            lines.append(f"- {mark} `{p}`")
        lines.append("")

    if len(groups) > max_groups:
        lines.append(f"*(只显示前 {max_groups} 组, 其他见 dedup-*.tsv)*")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*auto-generated by `brain asset-dedup` (Python; dry-run only)*")
    return "\n".join(lines)


def run(
    *,
    assets_root: Path | None = None,
    min_kb: int = 10,
    include_inbox: bool = False,
    write_reports: bool = True,
    today: str | None = None,
) -> dict[str, Any]:
    paths = load_paths_config()["paths"]
    ar = assets_root or Path(paths.get("assets_root") or paths.get("brain_assets_root") or "D:\\second-brain-assets")
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    scan = scan_duplicates(ar, min_bytes=max(0, int(min_kb)) * 1024, include_inbox=include_inbox)
    if scan.get("status") != "ok":
        return scan

    out: dict[str, Any] = {
        "status": "ok",
        "assets_root": str(ar),
        "scanned": scan["scanned"],
        "groups": len(scan["groups"]),
        "redundant_files": scan["redundant_files"],
        "redundant_mb": _mb(scan["redundant_bytes"]),
        "samples": [
            {
                "size_kb": _kb(g["size"]),
                "count": len(g["paths"]),
                "keep": str(_suggest_keep(list(g["paths"]))[0]),
            }
            for g in scan["groups"][:5]
        ],
    }

    if write_reports:
        out_dir = ar / "_migration"
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"dedup-{today}.md"
        tsv_path = out_dir / f"dedup-{today}.tsv"
        md_path.write_text(render_markdown(scan, today=today), encoding="utf-8")
        tsv_path.write_text(render_tsv(scan), encoding="utf-8")
        out["report_md"] = str(md_path)
        out["report_tsv"] = str(tsv_path)

    return out
