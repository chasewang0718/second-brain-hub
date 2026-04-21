"""B1 · asset_dedup: two-pass SHA256 scan + TSV/MD render."""

from __future__ import annotations

from pathlib import Path

from brain_agents import asset_dedup


def _mk(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_no_duplicates_returns_empty_groups(tmp_path: Path):
    root = tmp_path / "assets"
    _mk(root / "a.bin", b"X" * 20480)  # 20 KB, unique
    _mk(root / "b.bin", b"Y" * 20480)  # same size, different content
    scan = asset_dedup.scan_duplicates(root)
    assert scan["status"] == "ok"
    assert scan["scanned"] == 2
    assert scan["same_size_candidates"] == 2  # same size, so both hashed
    assert scan["groups"] == []
    assert scan["redundant_files"] == 0


def test_duplicates_grouped_and_sorted_by_waste(tmp_path: Path):
    root = tmp_path / "assets"
    # Two big dup group (30 KB × 3 → waste 60 KB)
    big_content = b"B" * 30720
    _mk(root / "10-photos" / "dup1.jpg", big_content)
    _mk(root / "10-photos" / "dup2.jpg", big_content)
    _mk(root / "12-video" / "dup3.jpg", big_content)
    # Small dup (20 KB × 2 → waste 20 KB)
    small = b"S" * 20480
    _mk(root / "a.bin", small)
    _mk(root / "sub" / "a.bin", small)
    # Unique file
    _mk(root / "uniq.bin", b"U" * 15000)

    scan = asset_dedup.scan_duplicates(root)
    assert scan["status"] == "ok"
    assert scan["scanned"] == 6
    assert len(scan["groups"]) == 2
    # Biggest-waste group first
    assert scan["groups"][0]["size"] == 30720
    assert len(scan["groups"][0]["paths"]) == 3
    assert scan["groups"][1]["size"] == 20480
    # Redundant accounting
    assert scan["redundant_files"] == 3  # (3-1) + (2-1)
    assert scan["redundant_bytes"] == 30720 * 2 + 20480 * 1


def test_small_files_filtered(tmp_path: Path):
    root = tmp_path / "assets"
    _mk(root / "tiny1.txt", b"x")  # 1 byte
    _mk(root / "tiny2.txt", b"x")  # duplicate but < 10 KB
    scan = asset_dedup.scan_duplicates(root)  # default min_bytes = 10 KB
    assert scan["scanned"] == 0
    assert scan["groups"] == []


def test_inbox_skipped_by_default(tmp_path: Path):
    root = tmp_path / "assets"
    content = b"I" * 20480
    _mk(root / "99-inbox" / "a.pdf", content)
    _mk(root / "a.pdf", content)  # the duplicate outside inbox

    scan = asset_dedup.scan_duplicates(root)
    assert scan["scanned"] == 1  # inbox file excluded entirely
    assert scan["groups"] == []

    scan2 = asset_dedup.scan_duplicates(root, include_inbox=True)
    assert scan2["scanned"] == 2
    assert len(scan2["groups"]) == 1


def test_migration_dir_always_excluded(tmp_path: Path):
    root = tmp_path / "assets"
    content = b"M" * 20480
    _mk(root / "_migration" / "old.bin", content)
    _mk(root / "new.bin", content)
    scan = asset_dedup.scan_duplicates(root, include_inbox=True)
    assert scan["scanned"] == 1
    assert scan["groups"] == []


def test_keep_suggestion_prefers_shorter_path(tmp_path: Path):
    root = tmp_path / "assets"
    content = b"K" * 20480
    _mk(root / "a.bin", content)  # short
    _mk(root / "deeply" / "nested" / "path" / "a.bin", content)  # long

    scan = asset_dedup.scan_duplicates(root)
    assert len(scan["groups"]) == 1
    sorted_paths = asset_dedup._suggest_keep(list(scan["groups"][0]["paths"]))
    # Shortest path wins
    assert sorted_paths[0].name == "a.bin"
    assert sorted_paths[0].parent == root


def test_render_tsv_has_header_and_rows(tmp_path: Path):
    root = tmp_path / "assets"
    content = b"T" * 20480
    _mk(root / "a.bin", content)
    _mk(root / "b.bin", content)
    scan = asset_dedup.scan_duplicates(root)
    tsv = asset_dedup.render_tsv(scan)
    lines = [ln for ln in tsv.splitlines() if ln.strip()]
    assert lines[0].startswith("hash\tsize_kb\t")
    # Two entries — one KEEP, one DUP
    marks = {ln.rsplit("\t", 1)[-1] for ln in lines[1:]}
    assert marks == {"KEEP", "DUP"}


def test_render_markdown_no_dups_shows_none_message(tmp_path: Path):
    scan = {"status": "ok", "scanned": 5, "min_bytes": 10240, "groups": [], "redundant_files": 0, "redundant_bytes": 0, "include_inbox": False}
    md = asset_dedup.render_markdown(scan, today="2026-04-21")
    assert "没找到任何重复文件" in md
    assert "### 组" not in md


def test_run_writes_both_reports(tmp_path: Path):
    root = tmp_path / "assets"
    content = b"R" * 20480
    _mk(root / "a.bin", content)
    _mk(root / "b.bin", content)

    out = asset_dedup.run(assets_root=root, today="2026-04-21")
    assert out["status"] == "ok"
    assert out["groups"] == 1
    assert Path(out["report_md"]).exists()
    assert Path(out["report_tsv"]).exists()
    tsv = Path(out["report_tsv"]).read_text(encoding="utf-8")
    assert tsv.startswith("hash\tsize_kb\t")


def test_run_no_write(tmp_path: Path):
    root = tmp_path / "assets"
    content = b"R" * 20480
    _mk(root / "a.bin", content)
    _mk(root / "b.bin", content)

    out = asset_dedup.run(assets_root=root, write_reports=False)
    assert out["status"] == "ok"
    assert "report_md" not in out
    assert not (root / "_migration").exists()


def test_missing_root(tmp_path: Path):
    out = asset_dedup.scan_duplicates(tmp_path / "nope")
    assert out["status"] == "missing"
