"""E2 · Parity checker for the asset-migrate manifest.

Compares two ``*-manifest.tsv`` files (typically one from the
PowerShell ``brain-asset-migrate.ps1 -DryRun`` and one from
``brain asset-scan``) and reports differences. Used during the
3-week parity window after B3/B4 before deleting the PS versions
(see ``architecture/asset-migration-plan.md``).

Pure read-only on both inputs. Never touches the actual asset
files; just re-reads the two TSVs.

The two manifests share the same column set by construction
(see ``asset_migrate.MANIFEST_COLUMNS``):

    source_path, size_kb, mtime, ext, rule, action,
    target_dir, new_name, date_source, note

Join key is ``source_path`` (case-insensitive, slash-normalized).
Mismatch dimensions reported: ``rule``, ``action``, ``target_dir``.

Usage (as expected during parity window):

    # 1. run the PS version
    pwsh tools/asset/brain-asset-migrate.ps1 -Source X -JobName ps-X

    # 2. run the Python version on the same source
    brain asset-scan --source X --job py-X

    # 3. diff the two manifests
    brain asset-parity-diff \\
        --a D:\\second-brain-assets\\_migration\\ps-X-manifest.tsv \\
        --b D:\\second-brain-assets\\_migration\\py-X-manifest.tsv \\
        --output D:\\second-brain-assets\\_migration\\parity-X.md
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


# Join key is source_path normalized; everything downstream is on the
# normalized key. We keep the original casing in the rows for display.
def _normalize_src(path: str) -> str:
    return path.replace("/", "\\").lower().rstrip("\\")


def load_manifest(path: Path) -> list[dict[str, str]]:
    """Read a tab-separated manifest. Tolerant to missing columns
    (they show up as empty strings), so a hand-edited or older
    format still loads.

    Uses ``utf-8-sig`` to eat the BOM that PowerShell 5.1's
    ``Export-Csv -Encoding UTF8`` writes. Without this, the first
    header would be read as ``\\ufeffsource_path`` and the whole
    join-by-source_path would silently miss every row.
    """
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, dialect="excel-tab")
        # Belt-and-braces: also strip any leftover BOM or whitespace
        # from column names, so a weirdly-encoded hand edit still
        # parses cleanly.
        return [
            {(k or "").lstrip("\ufeff").strip(): (v or "") for k, v in row.items()}
            for row in reader
        ]


def _index_by_src(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        src = row.get("source_path", "")
        if not src:
            continue
        out[_normalize_src(src)] = row
    return out


def _count_by_rule(rows: Iterable[dict[str, str]]) -> dict[str, int]:
    c: dict[str, int] = {}
    for row in rows:
        r = row.get("rule", "") or "(empty)"
        c[r] = c.get(r, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def diff_manifests(
    a_rows: list[dict[str, str]],
    b_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Compute a diff between two manifest row lists.

    Returns a dict with:

    - ``a_count`` / ``b_count``: total rows per side
    - ``only_in_a`` / ``only_in_b``: rows whose normalized
      source_path is present on exactly one side
    - ``common_count``: number of shared source_paths
    - ``mismatches``: list of dicts ``{source_path, rule: [a, b],
      action: [a, b], target_dir: [a, b]}`` for shared source_paths
      where any of those three fields disagree
    - ``identical_count``: shared rows where rule + action +
      target_dir all agree (``common_count - len(mismatches)``)
    - ``stats_a_by_rule`` / ``stats_b_by_rule``: ``{rule: count}``
      for quick visual sanity check
    - ``match``: True iff both sides have the same source_paths
      AND every shared row agrees on rule/action/target_dir
    """
    a_idx = _index_by_src(a_rows)
    b_idx = _index_by_src(b_rows)
    a_keys = set(a_idx)
    b_keys = set(b_idx)

    only_a_keys = a_keys - b_keys
    only_b_keys = b_keys - a_keys
    common_keys = a_keys & b_keys

    only_in_a = [a_idx[k] for k in sorted(only_a_keys)]
    only_in_b = [b_idx[k] for k in sorted(only_b_keys)]

    mismatches: list[dict[str, Any]] = []
    for k in sorted(common_keys):
        ra, rb = a_idx[k], b_idx[k]
        diffs: dict[str, list[str]] = {}
        for col in ("rule", "action", "target_dir"):
            va = (ra.get(col) or "").strip()
            vb = (rb.get(col) or "").strip()
            # target_dir differences can be just slash-vs-backslash
            # noise between PS and Python; normalize before comparing.
            if col == "target_dir":
                va_cmp = va.replace("/", "\\").lower()
                vb_cmp = vb.replace("/", "\\").lower()
            else:
                va_cmp = va
                vb_cmp = vb
            if va_cmp != vb_cmp:
                diffs[col] = [va, vb]
        if diffs:
            entry: dict[str, Any] = {"source_path": ra.get("source_path", "")}
            entry.update(diffs)
            mismatches.append(entry)

    identical_count = len(common_keys) - len(mismatches)
    match = (not only_a_keys) and (not only_b_keys) and (not mismatches)

    return {
        "a_count": len(a_rows),
        "b_count": len(b_rows),
        "common_count": len(common_keys),
        "identical_count": identical_count,
        "only_in_a": only_in_a,
        "only_in_b": only_in_b,
        "mismatches": mismatches,
        "stats_a_by_rule": _count_by_rule(a_rows),
        "stats_b_by_rule": _count_by_rule(b_rows),
        "match": match,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

_SAMPLE_ROWS = 20


def _row_table(rows: list[dict[str, str]], *, label: str) -> list[str]:
    out: list[str] = [f"### {label} (前 {_SAMPLE_ROWS} 条)", ""]
    if not rows:
        out.append("_无_")
        out.append("")
        return out
    out.append("| source_path | rule | action | target_dir |")
    out.append("|---|---|---|---|")
    for row in rows[:_SAMPLE_ROWS]:
        src = row.get("source_path", "")
        rule = row.get("rule", "")
        action = row.get("action", "")
        tgt = row.get("target_dir", "")
        # Markdown-escape the pipe so long Windows paths don't
        # break the table.
        src_md = src.replace("|", "\\|")
        tgt_md = tgt.replace("|", "\\|")
        out.append(f"| `{src_md}` | `{rule}` | `{action}` | `{tgt_md}` |")
    if len(rows) > _SAMPLE_ROWS:
        out.append("")
        out.append(f"_...还有 {len(rows) - _SAMPLE_ROWS} 行，见 JSON 输出。_")
    out.append("")
    return out


def _mismatch_table(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = [f"### 共同 source_path 但分类不同 (前 {_SAMPLE_ROWS} 条)", ""]
    if not rows:
        out.append("_无_")
        out.append("")
        return out
    out.append("| source_path | col | A | B |")
    out.append("|---|---|---|---|")
    shown = 0
    for entry in rows:
        src = entry.get("source_path", "")
        src_md = src.replace("|", "\\|")
        for col in ("rule", "action", "target_dir"):
            if col in entry:
                a, b = entry[col]
                a_md = str(a).replace("|", "\\|")
                b_md = str(b).replace("|", "\\|")
                out.append(f"| `{src_md}` | {col} | `{a_md}` | `{b_md}` |")
        shown += 1
        if shown >= _SAMPLE_ROWS:
            break
    if len(rows) > _SAMPLE_ROWS:
        out.append("")
        out.append(f"_...还有 {len(rows) - _SAMPLE_ROWS} 条不一致，见 JSON 输出。_")
    out.append("")
    return out


def _rule_stats_table(a: dict[str, int], b: dict[str, int]) -> list[str]:
    out: list[str] = ["### 每类计数对比", ""]
    out.append("| rule | A | B | diff |")
    out.append("|---|---:|---:|---:|")
    for rule in sorted(set(a) | set(b)):
        av = a.get(rule, 0)
        bv = b.get(rule, 0)
        d = bv - av
        sign = "+" if d > 0 else ""
        out.append(f"| `{rule}` | {av} | {bv} | {sign}{d} |")
    out.append("")
    return out


def render_markdown(
    diff: dict[str, Any],
    *,
    a_path: str,
    b_path: str,
    today: str | None = None,
) -> str:
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = []
    lines.append("---")
    lines.append(f"title: asset-migrate parity {today}")
    lines.append(f"date: {today}")
    lines.append("tags: [parity, asset-migrate, auto-generated]")
    lines.append("---")
    lines.append("")
    lines.append(f"# asset-migrate parity {today}")
    lines.append("")
    lines.append(f"- **A** (PS): `{a_path}`")
    lines.append(f"- **B** (Python): `{b_path}`")
    lines.append("")

    verdict = "✅ 对拍通过" if diff["match"] else "⚠️ 有差异"
    lines.append(f"**结论**: {verdict}")
    lines.append("")

    lines.append("## 整体汇总")
    lines.append("")
    lines.append(f"- A 总行数: `{diff['a_count']}`")
    lines.append(f"- B 总行数: `{diff['b_count']}`")
    lines.append(f"- 共同 source_path: `{diff['common_count']}`")
    lines.append(f"- 完全一致（共同行 rule/action/target_dir 全对齐）: `{diff['identical_count']}`")
    lines.append(f"- 仅在 A 中: `{len(diff['only_in_a'])}`")
    lines.append(f"- 仅在 B 中: `{len(diff['only_in_b'])}`")
    lines.append(f"- 共同但分类不同: `{len(diff['mismatches'])}`")
    lines.append("")

    lines.append("## 每类计数")
    lines.append("")
    lines.extend(_rule_stats_table(diff["stats_a_by_rule"], diff["stats_b_by_rule"]))

    lines.append("## 差异明细")
    lines.append("")
    lines.extend(_row_table(diff["only_in_a"], label="仅在 A 中的文件"))
    lines.extend(_row_table(diff["only_in_b"], label="仅在 B 中的文件"))
    lines.extend(_mismatch_table(diff["mismatches"]))

    lines.append("---")
    lines.append("")
    lines.append("*auto-generated by `brain asset-parity-diff` (Python; 对拍期间 3 周用)*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public run helper (used by CLI)
# ---------------------------------------------------------------------------

def run(
    *,
    a_path: str | Path,
    b_path: str | Path,
    output_path: str | Path | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    a = Path(a_path)
    b = Path(b_path)
    if not a.exists():
        return {"status": "missing_a", "a_path": str(a)}
    if not b.exists():
        return {"status": "missing_b", "b_path": str(b)}

    a_rows = load_manifest(a)
    b_rows = load_manifest(b)
    diff = diff_manifests(a_rows, b_rows)

    out: dict[str, Any] = {
        "status": "ok",
        "a_path": str(a),
        "b_path": str(b),
        "match": diff["match"],
        "a_count": diff["a_count"],
        "b_count": diff["b_count"],
        "common_count": diff["common_count"],
        "identical_count": diff["identical_count"],
        "only_in_a_count": len(diff["only_in_a"]),
        "only_in_b_count": len(diff["only_in_b"]),
        "mismatches_count": len(diff["mismatches"]),
        "stats_a_by_rule": diff["stats_a_by_rule"],
        "stats_b_by_rule": diff["stats_b_by_rule"],
    }

    if output_path is not None:
        op = Path(output_path)
        op.parent.mkdir(parents=True, exist_ok=True)
        md = render_markdown(diff, a_path=str(a), b_path=str(b), today=today)
        op.write_text(md, encoding="utf-8")
        out["report_path"] = str(op)

    return out
