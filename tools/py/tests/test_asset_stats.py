"""B1 · asset_stats: scan + render."""

from __future__ import annotations

import os
import time
from pathlib import Path

from brain_agents import asset_stats


def _mk(path: Path, content: bytes = b"", mtime: float | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_scan_counts_and_groups(tmp_path: Path):
    root = tmp_path / "assets"
    # photos/YYYY-MM pattern, varied extensions, _migration excluded
    _mk(root / "10-photos" / "2026-04" / "a.jpg", b"x" * 1000, mtime=1776000000.0)
    _mk(root / "10-photos" / "2026-04" / "b.jpg", b"y" * 2000, mtime=1776000000.0)
    _mk(root / "12-video" / "clip.mp4", b"z" * 5000, mtime=1776500000.0)
    _mk(root / "README", b"plain", mtime=1776000000.0)
    _mk(root / "_migration" / "ignore.me", b"should not be counted", mtime=1776000000.0)

    stats = asset_stats.scan_assets(root)
    assert stats["status"] == "ok"
    # 4 counted + 1 skipped (the _migration file)
    assert stats["total_count"] == 4
    # top-level dirs: 10-photos, 12-video, and "(root)" for README
    assert set(stats["top_dirs"].keys()) == {"10-photos", "12-video", "(root)"}
    assert stats["top_dirs"]["10-photos"]["count"] == 2
    assert stats["top_dirs"]["10-photos"]["size"] == 3000
    # ext_map: .jpg (2), .mp4 (1), (no-ext) (1 for README)
    assert stats["ext_map"][".jpg"]["count"] == 2
    assert stats["ext_map"][".mp4"]["count"] == 1
    assert stats["ext_map"]["(no-ext)"]["count"] == 1
    # top_large: sorted by size desc, mp4 (5000) biggest
    assert stats["top_large"][0][0] == 5000


def test_scan_handles_missing_root(tmp_path: Path):
    out = asset_stats.scan_assets(tmp_path / "does-not-exist")
    assert out["status"] == "missing"


def test_render_markdown_has_all_sections(tmp_path: Path):
    root = tmp_path / "assets"
    _mk(root / "10-photos" / "a.jpg", b"x" * 1024, mtime=1776000000.0)
    _mk(root / "big.bin", b"X" * (10 * 1024 * 1024), mtime=1776500000.0)  # 10 MB

    stats = asset_stats.scan_assets(root)
    md = asset_stats.render_markdown(stats, today="2026-04-21")
    assert "# brain-assets 统计 2026-04-21" in md
    assert "## 一级目录分布" in md
    assert "## 扩展名 Top 20" in md
    assert "## 按月分布 (mtime)" in md
    assert "## Top 10 单文件" in md
    assert "big.bin" in md  # top-large entry appears in path cell
    assert "10.0" in md  # 10 MB rounded


def test_run_writes_report(tmp_path: Path):
    assets = tmp_path / "assets"
    content = tmp_path / "content"
    _mk(assets / "a.txt", b"hello", mtime=1776000000.0)

    out = asset_stats.run(
        assets_root=assets,
        content_root=content,
        today="2026-04-21",
    )
    assert out["status"] == "ok"
    assert out["total_count"] == 1
    report = Path(out["report_path"])
    assert report.exists()
    assert "brain-assets" in report.read_text(encoding="utf-8")


def test_run_no_write_skips_file(tmp_path: Path):
    assets = tmp_path / "assets"
    _mk(assets / "a.txt", b"hello")

    out = asset_stats.run(assets_root=assets, content_root=tmp_path / "content", write_report=False, today="2026-04-21")
    assert out["status"] == "ok"
    assert "report_path" not in out
    assert not (tmp_path / "content" / "04-journal" / "brain-assets-stats-2026-04-21.md").exists()


def test_empty_asset_root(tmp_path: Path):
    assets = tmp_path / "assets"
    assets.mkdir()
    stats = asset_stats.scan_assets(assets)
    assert stats["status"] == "ok"
    assert stats["total_count"] == 0
    assert stats["total_size"] == 0
    # render still OK, 0% columns
    md = asset_stats.render_markdown(stats, today="2026-04-21")
    assert "**总文件数**: 0" in md
