"""E2 · asset_migrate_parity: diff two manifest TSVs."""

from __future__ import annotations

import csv
from pathlib import Path

from brain_agents import asset_migrate_parity as amp
from brain_agents import asset_migrate as am


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(am.MANIFEST_COLUMNS), dialect="excel-tab")
        w.writeheader()
        for r in rows:
            row = {k: "" for k in am.MANIFEST_COLUMNS}
            row.update(r)
            w.writerow(row)


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------

def test_load_manifest_reads_expected_columns(tmp_path: Path):
    p = tmp_path / "m.tsv"
    _write_manifest(p, [
        {"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy",
         "target_dir": "10-photos\\2024-01", "new_name": "a.jpg"},
    ])
    rows = amp.load_manifest(p)
    assert len(rows) == 1
    assert rows[0]["source_path"] == "D:\\src\\a.jpg"
    assert rows[0]["rule"] == "photo"


def test_load_manifest_missing_file_returns_empty(tmp_path: Path):
    assert amp.load_manifest(tmp_path / "nope.tsv") == []


# ---------------------------------------------------------------------------
# diff_manifests: identical
# ---------------------------------------------------------------------------

def test_diff_identical_manifests_reports_match(tmp_path: Path):
    rows = [
        {"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy",
         "target_dir": "10-photos\\2024-01", "new_name": "a.jpg"},
        {"source_path": "D:\\src\\clip.mp4", "rule": "video", "action": "copy",
         "target_dir": "12-video\\2024-05", "new_name": "clip.mp4"},
    ]
    diff = amp.diff_manifests(rows, list(rows))
    assert diff["match"] is True
    assert diff["a_count"] == 2
    assert diff["b_count"] == 2
    assert diff["common_count"] == 2
    assert diff["identical_count"] == 2
    assert diff["only_in_a"] == []
    assert diff["only_in_b"] == []
    assert diff["mismatches"] == []


# ---------------------------------------------------------------------------
# diff_manifests: disjoint / partial overlap
# ---------------------------------------------------------------------------

def test_diff_only_in_one_side(tmp_path: Path):
    a_rows = [
        {"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy", "target_dir": "10-photos\\2024-01"},
        {"source_path": "D:\\src\\b.jpg", "rule": "photo", "action": "copy", "target_dir": "10-photos\\2024-02"},
    ]
    b_rows = [
        {"source_path": "D:\\src\\b.jpg", "rule": "photo", "action": "copy", "target_dir": "10-photos\\2024-02"},
        {"source_path": "D:\\src\\c.jpg", "rule": "photo", "action": "copy", "target_dir": "10-photos\\2024-03"},
    ]
    diff = amp.diff_manifests(a_rows, b_rows)
    assert diff["match"] is False
    assert diff["common_count"] == 1
    assert diff["identical_count"] == 1
    assert [r["source_path"] for r in diff["only_in_a"]] == ["D:\\src\\a.jpg"]
    assert [r["source_path"] for r in diff["only_in_b"]] == ["D:\\src\\c.jpg"]


# ---------------------------------------------------------------------------
# diff_manifests: shared key, mismatching classification
# ---------------------------------------------------------------------------

def test_diff_mismatch_target_dir_when_exif_vs_mtime(tmp_path: Path):
    # PS got exif=2024-01; Python fell back to mtime=2024-02
    a_rows = [{"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy",
               "target_dir": "10-photos\\2024-01"}]
    b_rows = [{"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy",
               "target_dir": "10-photos\\2024-02"}]
    diff = amp.diff_manifests(a_rows, b_rows)
    assert diff["match"] is False
    assert diff["common_count"] == 1
    assert len(diff["mismatches"]) == 1
    m = diff["mismatches"][0]
    assert m["source_path"] == "D:\\src\\a.jpg"
    assert m["target_dir"] == ["10-photos\\2024-01", "10-photos\\2024-02"]
    assert "rule" not in m
    assert "action" not in m


def test_diff_target_dir_slash_vs_backslash_is_not_a_diff(tmp_path: Path):
    a_rows = [{"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy",
               "target_dir": "10-photos/2024-01"}]
    b_rows = [{"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy",
               "target_dir": "10-photos\\2024-01"}]
    diff = amp.diff_manifests(a_rows, b_rows)
    assert diff["match"] is True
    assert diff["mismatches"] == []


def test_diff_mismatch_rule(tmp_path: Path):
    a_rows = [{"source_path": "D:\\src\\x.tiff", "rule": "other", "action": "copy",
               "target_dir": "98-staging"}]
    b_rows = [{"source_path": "D:\\src\\x.tiff", "rule": "photo", "action": "copy",
               "target_dir": "10-photos\\2024-01"}]
    diff = amp.diff_manifests(a_rows, b_rows)
    assert diff["match"] is False
    m = diff["mismatches"][0]
    assert m["rule"] == ["other", "photo"]
    assert "target_dir" in m


def test_diff_source_path_match_is_case_insensitive(tmp_path: Path):
    a_rows = [{"source_path": "D:\\Src\\A.jpg", "rule": "photo", "action": "copy",
               "target_dir": "10-photos\\2024-01"}]
    b_rows = [{"source_path": "d:/src/a.JPG", "rule": "photo", "action": "copy",
               "target_dir": "10-photos\\2024-01"}]
    diff = amp.diff_manifests(a_rows, b_rows)
    assert diff["common_count"] == 1
    assert diff["match"] is True


# ---------------------------------------------------------------------------
# stats_by_rule
# ---------------------------------------------------------------------------

def test_diff_stats_per_rule_ordered_by_count(tmp_path: Path):
    a_rows = [
        {"source_path": f"D:\\src\\a{i}.jpg", "rule": "photo", "action": "copy", "target_dir": "10-photos\\2024-01"}
        for i in range(3)
    ] + [
        {"source_path": "D:\\src\\clip.mp4", "rule": "video", "action": "copy", "target_dir": "12-video\\2024-05"},
    ]
    b_rows = list(a_rows) + [
        {"source_path": "D:\\src\\font.ttf", "rule": "font", "action": "copy", "target_dir": "11-fonts"},
    ]
    diff = amp.diff_manifests(a_rows, b_rows)
    assert diff["stats_a_by_rule"] == {"photo": 3, "video": 1}
    assert diff["stats_b_by_rule"] == {"photo": 3, "video": 1, "font": 1}


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------

def test_render_markdown_identical_shows_pass(tmp_path: Path):
    rows = [{"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy",
             "target_dir": "10-photos\\2024-01"}]
    diff = amp.diff_manifests(rows, list(rows))
    md = amp.render_markdown(diff, a_path="A.tsv", b_path="B.tsv", today="2026-04-21")
    assert "# asset-migrate parity 2026-04-21" in md
    assert "对拍通过" in md
    assert "## 整体汇总" in md
    assert "## 每类计数" in md
    assert "## 差异明细" in md


def test_render_markdown_differences_shows_fail(tmp_path: Path):
    a_rows = [{"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy",
               "target_dir": "10-photos\\2024-01"}]
    b_rows = [{"source_path": "D:\\src\\b.jpg", "rule": "photo", "action": "copy",
               "target_dir": "10-photos\\2024-02"}]
    diff = amp.diff_manifests(a_rows, b_rows)
    md = amp.render_markdown(diff, a_path="A.tsv", b_path="B.tsv")
    assert "有差异" in md
    # Both sides show up in the "only in X" section
    assert "D:\\src\\a.jpg" in md
    assert "D:\\src\\b.jpg" in md


def test_render_markdown_handles_pipe_in_paths(tmp_path: Path):
    a_rows = [{"source_path": "D:\\src\\weird|name.jpg", "rule": "photo", "action": "copy",
               "target_dir": "10-photos\\2024-01"}]
    b_rows: list[dict[str, str]] = []
    diff = amp.diff_manifests(a_rows, b_rows)
    md = amp.render_markdown(diff, a_path="A.tsv", b_path="B.tsv")
    # Pipe must be escaped so the markdown table survives
    assert "weird\\|name.jpg" in md


# ---------------------------------------------------------------------------
# run (top-level entrypoint)
# ---------------------------------------------------------------------------

def test_run_missing_a(tmp_path: Path):
    b = tmp_path / "b.tsv"
    _write_manifest(b, [])
    out = amp.run(a_path=tmp_path / "nope-a.tsv", b_path=b)
    assert out["status"] == "missing_a"


def test_run_missing_b(tmp_path: Path):
    a = tmp_path / "a.tsv"
    _write_manifest(a, [])
    out = amp.run(a_path=a, b_path=tmp_path / "nope-b.tsv")
    assert out["status"] == "missing_b"


def test_run_writes_report(tmp_path: Path):
    a = tmp_path / "a.tsv"
    b = tmp_path / "b.tsv"
    rows = [{"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy",
             "target_dir": "10-photos\\2024-01"}]
    _write_manifest(a, rows)
    _write_manifest(b, rows)

    out_path = tmp_path / "reports" / "parity.md"
    out = amp.run(a_path=a, b_path=b, output_path=out_path, today="2026-04-21")
    assert out["status"] == "ok"
    assert out["match"] is True
    assert out["report_path"] == str(out_path)
    assert out_path.exists()
    md = out_path.read_text(encoding="utf-8")
    assert "对拍通过" in md


def test_run_omits_report_when_output_path_none(tmp_path: Path):
    a = tmp_path / "a.tsv"
    b = tmp_path / "b.tsv"
    _write_manifest(a, [])
    _write_manifest(b, [])
    out = amp.run(a_path=a, b_path=b)
    assert "report_path" not in out
    assert out["match"] is True


def test_run_reports_counts_in_summary_dict(tmp_path: Path):
    a = tmp_path / "a.tsv"
    b = tmp_path / "b.tsv"
    _write_manifest(a, [
        {"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy", "target_dir": "10-photos\\2024-01"},
        {"source_path": "D:\\src\\b.jpg", "rule": "photo", "action": "copy", "target_dir": "10-photos\\2024-02"},
    ])
    _write_manifest(b, [
        {"source_path": "D:\\src\\a.jpg", "rule": "photo", "action": "copy", "target_dir": "10-photos\\2024-01"},
        {"source_path": "D:\\src\\c.jpg", "rule": "photo", "action": "copy", "target_dir": "10-photos\\2024-03"},
    ])
    out = amp.run(a_path=a, b_path=b)
    assert out["a_count"] == 2
    assert out["b_count"] == 2
    assert out["common_count"] == 1
    assert out["identical_count"] == 1
    assert out["only_in_a_count"] == 1
    assert out["only_in_b_count"] == 1
    assert out["mismatches_count"] == 0
    assert out["match"] is False
