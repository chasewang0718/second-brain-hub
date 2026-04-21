"""B3 · asset_migrate: classify + scan + execute."""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

import pytest

from brain_agents import asset_migrate as am


def _mk(path: Path, content: bytes = b"x", mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# ---------------------------------------------------------------------------
# classify_file
# ---------------------------------------------------------------------------

def test_classify_photo_with_exif(tmp_path: Path):
    f = _mk(tmp_path / "a.jpg", mtime=1700000000.0)

    def fake_photo(_p: Path) -> tuple[datetime, str]:
        return datetime(2024, 3, 15, 10, 30, 0), "exif"

    c = am.classify_file(f, photo_date_fn=fake_photo)
    assert c.rule == "photo"
    assert c.target_dir == "10-photos\\2024-03"
    assert c.date_source == "exif"
    assert c.action == "copy"
    assert c.new_name == "a.jpg"


def test_classify_photo_fallback_to_mtime(tmp_path: Path):
    # mtime = 2024-01-15 00:00:00 UTC-ish (doesn't matter for YM)
    f = _mk(tmp_path / "b.png", mtime=datetime(2024, 1, 15).timestamp())

    def raising_photo(_p: Path) -> tuple[datetime, str]:
        raise RuntimeError("no EXIF here")

    c = am.classify_file(f, photo_date_fn=raising_photo)
    assert c.rule == "photo"
    assert c.date_source == "mtime"
    assert c.target_dir == "10-photos\\2024-01"


def test_classify_video_uses_mtime(tmp_path: Path):
    f = _mk(tmp_path / "clip.mov", mtime=datetime(2025, 7, 4).timestamp())
    c = am.classify_file(f)
    assert c.rule == "video"
    assert c.target_dir == "12-video\\2025-07"
    assert c.date_source == "mtime"


@pytest.mark.parametrize(
    "name,expected_rule,expected_dir,expected_action",
    [
        ("track.mp3", "audio", "13-audio", "copy"),
        ("face.ttf", "font", "11-fonts", "copy"),
        ("blob.zip", "archive", "14-archives", "copy"),
        ("notes.md", "text", am.BRAIN_INBOX_SENTINEL, "copy-to-brain-inbox"),
        ("paper.pdf", "pdf", "99-inbox", "copy-to-assets-inbox"),
        ("deck.pptx", "document", "99-inbox", "copy-to-assets-inbox"),
        ("random.xyz", "other", "98-staging", "copy"),
    ],
)
def test_classify_simple_rules(tmp_path: Path, name, expected_rule, expected_dir, expected_action):
    f = _mk(tmp_path / name)
    c = am.classify_file(f)
    assert c.rule == expected_rule
    assert c.target_dir == expected_dir
    assert c.action == expected_action


@pytest.mark.parametrize(
    "name",
    ["IMG.AAE", "foo.tmp", "bar.bak", "Thumbs.db", "desktop.ini", ".DS_Store"],
)
def test_classify_trash_candidates(tmp_path: Path, name):
    f = _mk(tmp_path / name)
    c = am.classify_file(f)
    assert c.rule == "trash"
    assert c.action == "trash-candidate"
    assert c.target_dir == "-"


# ---------------------------------------------------------------------------
# is_excluded
# ---------------------------------------------------------------------------

def test_is_excluded_startswith_and_substring():
    patterns = ["D:\\junk", "temp_stuff"]
    assert am.is_excluded("D:\\junk\\a\\b.txt", patterns)
    assert am.is_excluded("D:/junk/a/b.txt", patterns)   # slash-normalized
    assert am.is_excluded("C:\\work\\temp_stuff\\x.pdf", patterns)  # substring
    assert not am.is_excluded("D:\\docs\\a.txt", patterns)


def test_is_excluded_empty_rule_ignored():
    assert not am.is_excluded("anything", ["", "  "])


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

def _photo_exif_at(ym: str):
    """Helper: stub a photo_date_fn that returns a fixed YYYY-MM."""
    def _fn(_p: Path) -> tuple[datetime, str]:
        y, m = ym.split("-")
        return datetime(int(y), int(m), 1), "exif"
    return _fn


def test_scan_writes_manifest_and_counts(tmp_path: Path):
    src = tmp_path / "src"
    assets = tmp_path / "assets"
    _mk(src / "a.jpg")
    _mk(src / "sub" / "clip.mp4", mtime=datetime(2024, 5, 1).timestamp())
    _mk(src / "ignore.tmp")
    _mk(src / "readme.md")

    result = am.scan(
        src,
        job_name="unit",
        assets_root=assets,
        exclude_patterns=[],
        photo_date_fn=_photo_exif_at("2024-03"),
    )
    assert result["status"] == "ok"
    assert result["total"] == 4
    assert result["excluded"] == 0
    assert result["counts"] == {"photo": 1, "video": 1, "trash": 1, "text": 1}

    manifest = Path(result["manifest_path"])
    assert manifest.exists()
    with manifest.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, dialect="excel-tab"))
    assert len(rows) == 4
    # column order preserved
    assert list(rows[0].keys()) == list(am.MANIFEST_COLUMNS)
    rules = {r["rule"] for r in rows}
    assert rules == {"photo", "video", "trash", "text"}


def test_scan_honors_exclude_patterns(tmp_path: Path):
    src = tmp_path / "src"
    assets = tmp_path / "assets"
    _mk(src / "keep.pdf")
    _mk(src / "skip_me" / "nope.pdf")
    _mk(src / "also_out.pdf")

    result = am.scan(
        src,
        job_name="exc",
        assets_root=assets,
        exclude_patterns=["skip_me", "also_out.pdf"],
    )
    assert result["total"] == 3
    assert result["excluded"] == 2
    assert [r["source_path"] for r in result["rows"]] == [str(src / "keep.pdf")]


def test_scan_handles_missing_source(tmp_path: Path):
    out = am.scan(tmp_path / "does-not-exist", job_name="x", assets_root=tmp_path)
    assert out["status"] == "missing_source"
    assert out["rows"] == []


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(am.MANIFEST_COLUMNS), dialect="excel-tab")
        w.writeheader()
        for r in rows:
            row = {k: "" for k in am.MANIFEST_COLUMNS}
            row.update(r)
            w.writerow(row)


def test_execute_copies_files_and_preserves_mtime(tmp_path: Path):
    src = _mk(tmp_path / "src" / "photo.jpg", content=b"abc" * 100, mtime=1700000000.0)
    assets = tmp_path / "assets"
    brain = tmp_path / "brain"
    manifest = assets / "_migration" / "j-manifest.tsv"
    _write_manifest(
        manifest,
        [
            {
                "source_path": str(src),
                "rule": "photo",
                "action": "copy",
                "target_dir": "10-photos\\2023-11",
                "new_name": "photo.jpg",
            }
        ],
    )

    out = am.execute(manifest, assets_root=assets, brain_root=brain)
    assert out["status"] == "ok"
    assert out["copied"] == 1
    dest = assets / "10-photos" / "2023-11" / "photo.jpg"
    assert dest.exists()
    # mtime preserved (allow tiny FS quantum drift)
    assert abs(dest.stat().st_mtime - 1700000000.0) < 2.0
    # source still exists (never deleted)
    assert src.exists()
    # log file written next to manifest
    assert Path(out["log_path"]).exists()


def test_execute_name_collision_adds_mtime_suffix(tmp_path: Path):
    src = _mk(tmp_path / "src" / "a.jpg", mtime=datetime(2024, 2, 3, 4, 5, 6).timestamp())
    assets = tmp_path / "assets"
    # pre-create destination collision
    dest_dir = assets / "10-photos" / "2024-02"
    _mk(dest_dir / "a.jpg", content=b"existing", mtime=1.0)

    manifest = assets / "_migration" / "c-manifest.tsv"
    _write_manifest(
        manifest,
        [
            {
                "source_path": str(src),
                "rule": "photo",
                "action": "copy",
                "target_dir": "10-photos/2024-02",
                "new_name": "a.jpg",
            }
        ],
    )
    out = am.execute(manifest, assets_root=assets, brain_root=tmp_path / "brain")
    assert out["copied"] == 1
    # original collision target untouched
    assert (dest_dir / "a.jpg").read_bytes() == b"existing"
    # renamed sibling exists (mtime stamped into filename)
    expected = dest_dir / "a-20240203-040506.jpg"
    assert expected.exists()


def test_execute_trash_candidate_logs_only(tmp_path: Path):
    src = _mk(tmp_path / "src" / "thumb.db", content=b"junk")
    assets = tmp_path / "assets"
    manifest = assets / "_migration" / "t-manifest.tsv"
    _write_manifest(
        manifest,
        [
            {
                "source_path": str(src),
                "rule": "trash",
                "action": "trash-candidate",
                "target_dir": "-",
                "new_name": "-",
            }
        ],
    )
    out = am.execute(manifest, assets_root=assets, brain_root=tmp_path / "brain")
    assert out["trash_marked"] == 1
    assert out["copied"] == 0
    # source still exists (never deleted)
    assert src.exists()
    log = Path(out["log_path"]).read_text(encoding="utf-8")
    assert "TRASH-CANDIDATE" in log
    assert str(src) in log


def test_execute_missing_source_counted_and_logged(tmp_path: Path):
    assets = tmp_path / "assets"
    manifest = assets / "_migration" / "m-manifest.tsv"
    _write_manifest(
        manifest,
        [
            {
                "source_path": str(tmp_path / "src" / "ghost.pdf"),
                "rule": "pdf",
                "action": "copy-to-assets-inbox",
                "target_dir": "99-inbox",
                "new_name": "ghost.pdf",
            }
        ],
    )
    out = am.execute(manifest, assets_root=assets, brain_root=tmp_path / "brain")
    assert out["skipped"] == 1
    assert out["copied"] == 0
    log = Path(out["log_path"]).read_text(encoding="utf-8")
    assert "SOURCE-MISSING" in log


def test_execute_text_goes_to_brain_99_inbox(tmp_path: Path):
    src = _mk(tmp_path / "src" / "notes.md", content=b"# hi")
    assets = tmp_path / "assets"
    brain = tmp_path / "brain"
    manifest = assets / "_migration" / "tx-manifest.tsv"
    _write_manifest(
        manifest,
        [
            {
                "source_path": str(src),
                "rule": "text",
                "action": "copy-to-brain-inbox",
                "target_dir": am.BRAIN_INBOX_SENTINEL,
                "new_name": "notes.md",
            }
        ],
    )
    out = am.execute(manifest, assets_root=assets, brain_root=brain)
    assert out["copied"] == 1
    assert out["to_brain_inbox"] == 1
    dest = brain / "99-inbox" / "notes.md"
    assert dest.exists()
    # assets root should not contain it
    assert not (assets / "99-inbox" / "notes.md").exists()


def test_execute_picks_latest_manifest(tmp_path: Path):
    assets = tmp_path / "assets"
    (assets / "_migration").mkdir(parents=True, exist_ok=True)
    # older
    m_old = assets / "_migration" / "old-manifest.tsv"
    _write_manifest(m_old, [])
    os.utime(m_old, (1000, 1000))
    # newer
    m_new = assets / "_migration" / "new-manifest.tsv"
    _write_manifest(m_new, [])
    os.utime(m_new, (2000, 2000))

    out = am.execute(None, assets_root=assets, brain_root=tmp_path / "brain")
    assert out["status"] == "ok"
    assert out["manifest_path"].endswith("new-manifest.tsv")


def test_execute_missing_manifest_returns_error(tmp_path: Path):
    out = am.execute(None, assets_root=tmp_path / "nope", brain_root=tmp_path / "brain")
    assert out["status"] == "missing_manifest"


# ---------------------------------------------------------------------------
# migration_dir / run_scan
# ---------------------------------------------------------------------------

def test_migration_dir_uses_assets_root(tmp_path: Path):
    assert am.migration_dir(tmp_path) == tmp_path / "_migration"


def test_run_scan_generates_default_job_name(tmp_path: Path, monkeypatch):
    src = tmp_path / "src"
    assets = tmp_path / "assets"
    _mk(src / "x.md")
    # no job_name → auto-generated
    out = am.run_scan(source=src, assets_root=assets, exclude_patterns=[])
    assert out["status"] == "ok"
    assert out["job_name"].startswith("job-")
    assert Path(out["manifest_path"]).name.startswith("job-")
    assert Path(out["manifest_path"]).name.endswith("-manifest.tsv")
