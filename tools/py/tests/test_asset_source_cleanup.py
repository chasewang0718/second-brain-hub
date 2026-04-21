"""B4 · asset_source_cleanup: execute.log parsing, safety gates,
dry-run vs apply, manifest fallback, empty-dir sweep."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from brain_agents import asset_source_cleanup as asc
from brain_agents import asset_migrate as am


def _mk(path: Path, content: bytes = b"x", mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(am.MANIFEST_COLUMNS), dialect="excel-tab")
        w.writeheader()
        for r in rows:
            row = {k: "" for k in am.MANIFEST_COLUMNS}
            row.update(r)
            w.writerow(row)


def _write_execute_log(path: Path, pairs: list[tuple[str, str]], *, extras: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["=== Execute start 2026-04-21 10:00:00 ==="]
    for src, dst in pairs:
        lines.append(f"OK\t{src}\t->\t{dst}")
    if extras:
        lines.extend(extras)
    lines.append("=== Execute done 2026-04-21 10:01:00 ===")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# parse_execute_log
# ---------------------------------------------------------------------------

def test_parse_execute_log_ok_lines_only(tmp_path: Path):
    log = tmp_path / "j-execute.log"
    _write_execute_log(
        log,
        [("A\\a.jpg", "B\\a.jpg"), ("A\\b.jpg", "B\\b.jpg")],
        extras=[
            "SOURCE-MISSING\tA\\gone.jpg",
            "FAIL\tA\\bad.jpg\tsomething",
            "TRASH-CANDIDATE\tA\\thumb.db",
        ],
    )
    m = asc.parse_execute_log(log)
    assert m == {"A\\a.jpg": "B\\a.jpg", "A\\b.jpg": "B\\b.jpg"}


def test_parse_execute_log_missing_file(tmp_path: Path):
    assert asc.parse_execute_log(tmp_path / "nope.log") == {}


def test_parse_execute_log_rejects_malformed_lines(tmp_path: Path):
    log = tmp_path / "bad.log"
    log.write_text(
        "\n".join(
            [
                "OK\tonly-two-fields",
                "OK\tsrc\tNOT-ARROW\tdst",
                "OK\tgood\t->\tgood-dst",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    m = asc.parse_execute_log(log)
    assert m == {"good": "good-dst"}


# ---------------------------------------------------------------------------
# derive_ok_map_from_manifest
# ---------------------------------------------------------------------------

def test_derive_ok_map_from_manifest_filters_by_action(tmp_path: Path):
    mani = tmp_path / "j-manifest.tsv"
    assets = tmp_path / "assets"
    _write_manifest(
        mani,
        [
            {"source_path": "A\\1.jpg", "action": "copy", "target_dir": "10-photos/2024-01", "new_name": "1.jpg"},
            {"source_path": "A\\2.pdf", "action": "copy-to-assets-inbox", "target_dir": "99-inbox", "new_name": "2.pdf"},
            {"source_path": "A\\3.md", "action": "copy-to-brain-inbox", "target_dir": am.BRAIN_INBOX_SENTINEL, "new_name": "3.md"},
            {"source_path": "A\\junk.tmp", "action": "trash-candidate", "target_dir": "-", "new_name": "-"},
        ],
    )
    m = asc.derive_ok_map_from_manifest(mani, assets_root=assets, brain_root=tmp_path / "brain")
    # Only copy + copy-to-assets-inbox included. Text/trash skipped.
    assert set(m.keys()) == {"A\\1.jpg", "A\\2.pdf"}
    assert m["A\\1.jpg"] == str(assets / "10-photos" / "2024-01" / "1.jpg")
    assert m["A\\2.pdf"] == str(assets / "99-inbox" / "2.pdf")


# ---------------------------------------------------------------------------
# check_pair
# ---------------------------------------------------------------------------

def test_check_pair_ok(tmp_path: Path):
    s = _mk(tmp_path / "a.jpg", b"hello")
    d = _mk(tmp_path / "b.jpg", b"hello")
    assert asc.check_pair(s, d) == ("ok", "")


def test_check_pair_src_missing(tmp_path: Path):
    d = _mk(tmp_path / "b.jpg")
    st, _ = asc.check_pair(tmp_path / "nope.jpg", d)
    assert st == "src_missing"


def test_check_pair_dst_missing(tmp_path: Path):
    s = _mk(tmp_path / "a.jpg")
    st, detail = asc.check_pair(s, tmp_path / "nope.jpg")
    assert st == "dst_missing"
    assert "nope.jpg" in detail


def test_check_pair_size_mismatch(tmp_path: Path):
    s = _mk(tmp_path / "a.jpg", b"short")
    d = _mk(tmp_path / "b.jpg", b"way-way-longer")
    st, detail = asc.check_pair(s, d)
    assert st == "size_mismatch"
    assert "!=" in detail


# ---------------------------------------------------------------------------
# cleanup: dry-run vs apply
# ---------------------------------------------------------------------------

def _setup_happy_path(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Build a source file, a matching dest, a manifest and an
    execute.log. Returns (src, dst, manifest_path, assets_root).
    """
    assets = tmp_path / "assets"
    src = _mk(tmp_path / "src" / "photo.jpg", content=b"abc" * 100, mtime=1700000000.0)
    dst = _mk(assets / "10-photos" / "2023-11" / "photo.jpg", content=b"abc" * 100, mtime=1700000000.0)
    mani = assets / "_migration" / "job-manifest.tsv"
    _write_manifest(
        mani,
        [{"source_path": str(src), "action": "copy", "target_dir": "10-photos/2023-11", "new_name": "photo.jpg"}],
    )
    log = assets / "_migration" / "job-execute.log"
    _write_execute_log(log, [(str(src), str(dst))])
    return src, dst, mani, assets


def test_cleanup_dry_run_does_not_delete(tmp_path: Path):
    src, dst, mani, assets = _setup_happy_path(tmp_path)
    out = asc.cleanup(
        manifest_path=mani,
        assets_root=assets,
        brain_root=tmp_path / "brain",
        apply=False,
    )
    assert out["status"] == "ok"
    assert out["mode"] == "DRY-RUN"
    assert out["source_of_truth"] == "execute_log"
    assert out["deleted"] == 1           # counts "would-delete" in dry-run
    assert src.exists()                  # NOT actually deleted
    assert dst.exists()                  # untouched
    log_text = Path(out["cleanup_log_path"]).read_text(encoding="utf-8")
    assert "WOULD-DELETE" in log_text
    assert "DELETED\t" not in log_text    # ensure no apply-line sneaked through


def test_cleanup_apply_deletes_source(tmp_path: Path):
    src, dst, mani, assets = _setup_happy_path(tmp_path)
    out = asc.cleanup(
        manifest_path=mani,
        assets_root=assets,
        brain_root=tmp_path / "brain",
        apply=True,
    )
    assert out["mode"] == "APPLY"
    assert out["deleted"] == 1
    assert not src.exists()              # source GONE
    assert dst.exists()                  # dest preserved
    log_text = Path(out["cleanup_log_path"]).read_text(encoding="utf-8")
    assert "DELETED\t" in log_text


def test_cleanup_safety_gate_src_missing(tmp_path: Path):
    assets = tmp_path / "assets"
    dst = _mk(assets / "10-photos" / "2023-11" / "x.jpg", content=b"abc")
    mani = assets / "_migration" / "job-manifest.tsv"
    _write_manifest(mani, [{"source_path": str(tmp_path / "ghost.jpg"), "action": "copy",
                            "target_dir": "10-photos/2023-11", "new_name": "x.jpg"}])
    log = assets / "_migration" / "job-execute.log"
    _write_execute_log(log, [(str(tmp_path / "ghost.jpg"), str(dst))])

    out = asc.cleanup(manifest_path=mani, assets_root=assets, apply=True)
    assert out["src_missing"] == 1
    assert out["deleted"] == 0
    assert dst.exists()                  # never touched
    log_text = Path(out["cleanup_log_path"]).read_text(encoding="utf-8")
    assert "SKIP-SRC-GONE" in log_text


def test_cleanup_safety_gate_dst_missing(tmp_path: Path):
    src = _mk(tmp_path / "src" / "a.jpg", content=b"abc")
    assets = tmp_path / "assets"
    mani = assets / "_migration" / "job-manifest.tsv"
    _write_manifest(mani, [{"source_path": str(src), "action": "copy",
                            "target_dir": "10-photos/2023-11", "new_name": "a.jpg"}])
    log = assets / "_migration" / "job-execute.log"
    _write_execute_log(log, [(str(src), str(assets / "10-photos" / "2023-11" / "a.jpg"))])

    out = asc.cleanup(manifest_path=mani, assets_root=assets, apply=True)
    assert out["dst_missing"] == 1
    assert out["deleted"] == 0
    assert src.exists()                  # NOT deleted — dst absent
    log_text = Path(out["cleanup_log_path"]).read_text(encoding="utf-8")
    assert "SKIP-DST-MISSING" in log_text


def test_cleanup_safety_gate_size_mismatch(tmp_path: Path):
    src = _mk(tmp_path / "src" / "a.jpg", content=b"short")
    assets = tmp_path / "assets"
    dst = _mk(assets / "10-photos" / "2023-11" / "a.jpg", content=b"way-way-longer")
    mani = assets / "_migration" / "job-manifest.tsv"
    _write_manifest(mani, [{"source_path": str(src), "action": "copy",
                            "target_dir": "10-photos/2023-11", "new_name": "a.jpg"}])
    log = assets / "_migration" / "job-execute.log"
    _write_execute_log(log, [(str(src), str(dst))])

    out = asc.cleanup(manifest_path=mani, assets_root=assets, apply=True)
    assert out["size_mismatch"] == 1
    assert out["deleted"] == 0
    assert src.exists()                  # NOT deleted — size differs
    log_text = Path(out["cleanup_log_path"]).read_text(encoding="utf-8")
    assert "SKIP-SIZE-MISMATCH" in log_text


# ---------------------------------------------------------------------------
# Manifest fallback (execute.log missing)
# ---------------------------------------------------------------------------

def test_cleanup_falls_back_to_manifest_when_log_absent(tmp_path: Path):
    src, dst, mani, assets = _setup_happy_path(tmp_path)
    # Remove the execute.log so we exercise the fallback path
    (assets / "_migration" / "job-execute.log").unlink()
    out = asc.cleanup(manifest_path=mani, assets_root=assets, apply=False)
    assert out["source_of_truth"] == "manifest_fallback"
    assert out["deleted"] == 1
    # Still a dry-run — source intact
    assert src.exists()


# ---------------------------------------------------------------------------
# Missing manifest
# ---------------------------------------------------------------------------

def test_cleanup_missing_manifest(tmp_path: Path):
    out = asc.cleanup(manifest_path=tmp_path / "nope.tsv", assets_root=tmp_path, apply=False)
    assert out["status"] == "missing_manifest"


def test_cleanup_picks_latest_manifest(tmp_path: Path):
    assets = tmp_path / "assets"
    md = assets / "_migration"
    md.mkdir(parents=True, exist_ok=True)
    old = md / "old-manifest.tsv"
    _write_manifest(old, [])
    os.utime(old, (1000, 1000))
    new = md / "new-manifest.tsv"
    _write_manifest(new, [])
    os.utime(new, (2000, 2000))

    out = asc.cleanup(manifest_path=None, assets_root=assets, apply=False)
    assert out["status"] == "ok"
    assert out["manifest_path"].endswith("new-manifest.tsv")


# ---------------------------------------------------------------------------
# Empty-dir sweep
# ---------------------------------------------------------------------------

def test_empty_dir_sweep_skipped_when_source_root_missing(tmp_path: Path):
    src, dst, mani, assets = _setup_happy_path(tmp_path)
    out = asc.cleanup(manifest_path=mani, assets_root=assets, apply=True, source_root=None)
    assert out["empty_dir_sweep"] == "skipped_no_source_root"
    assert out["empty_dirs_deleted"] == 0


def test_empty_dir_sweep_skipped_on_dry_run(tmp_path: Path):
    src, dst, mani, assets = _setup_happy_path(tmp_path)
    out = asc.cleanup(
        manifest_path=mani,
        assets_root=assets,
        apply=False,
        source_root=src.parent.parent,  # would have been valid
    )
    # Dry-run never sweeps (no files actually removed to make dirs empty)
    assert out["empty_dir_sweep"] == "skipped"
    assert out["empty_dirs_deleted"] == 0


def test_empty_dir_sweep_removes_nested_empties(tmp_path: Path):
    # Build: source_root/dir1/dir2/only.jpg (and matching dst)
    source_root = tmp_path / "baidu"
    src = _mk(source_root / "dir1" / "dir2" / "only.jpg", content=b"abc")
    assets = tmp_path / "assets"
    dst = _mk(assets / "10-photos" / "2023-11" / "only.jpg", content=b"abc")
    mani = assets / "_migration" / "job-manifest.tsv"
    _write_manifest(mani, [{"source_path": str(src), "action": "copy",
                            "target_dir": "10-photos/2023-11", "new_name": "only.jpg"}])
    log = assets / "_migration" / "job-execute.log"
    _write_execute_log(log, [(str(src), str(dst))])

    out = asc.cleanup(
        manifest_path=mani,
        assets_root=assets,
        apply=True,
        source_root=source_root,
        delete_empty_dirs=True,
    )
    assert out["deleted"] == 1
    assert out["empty_dir_sweep"] == "ok"
    # Both nested empty dirs should be collapsed
    assert not (source_root / "dir1" / "dir2").exists()
    assert not (source_root / "dir1").exists()
    assert source_root.exists()          # root itself preserved
    assert out["empty_dirs_deleted"] >= 2


def test_empty_dir_sweep_disabled_via_flag(tmp_path: Path):
    source_root = tmp_path / "baidu"
    src = _mk(source_root / "dir1" / "only.jpg", content=b"abc")
    assets = tmp_path / "assets"
    dst = _mk(assets / "10-photos" / "2023-11" / "only.jpg", content=b"abc")
    mani = assets / "_migration" / "job-manifest.tsv"
    _write_manifest(mani, [{"source_path": str(src), "action": "copy",
                            "target_dir": "10-photos/2023-11", "new_name": "only.jpg"}])
    log = assets / "_migration" / "job-execute.log"
    _write_execute_log(log, [(str(src), str(dst))])

    out = asc.cleanup(
        manifest_path=mani,
        assets_root=assets,
        apply=True,
        source_root=source_root,
        delete_empty_dirs=False,
    )
    assert out["deleted"] == 1
    assert out["empty_dir_sweep"] == "skipped"
    assert (source_root / "dir1").exists()   # NOT swept


# ---------------------------------------------------------------------------
# Log file content
# ---------------------------------------------------------------------------

def test_cleanup_log_contains_headers_and_mode(tmp_path: Path):
    src, dst, mani, assets = _setup_happy_path(tmp_path)
    out = asc.cleanup(manifest_path=mani, assets_root=assets, apply=False)
    log_text = Path(out["cleanup_log_path"]).read_text(encoding="utf-8")
    assert "=== cleanup start" in log_text
    assert "=== cleanup done" in log_text
    assert "# 模式: DRY-RUN" in log_text
    assert "# source_of_truth: execute_log" in log_text
