"""B4 · Python port of ``tools/asset/brain-asset-source-cleanup.ps1``.

**This module DELETES source files.** Use with care.

Flow (Stage 4 of the asset pipeline):

1. Locate the manifest (explicit path or latest ``*-manifest.tsv``
   in ``<assets_root>/_migration/``).
2. Load the "OK" src→dst mapping from the sibling
   ``<job>-execute.log`` (written by ``asset_migrate.execute``).
   If that log is missing, fall back to deriving src→dst from the
   manifest's ``action in (copy, copy-to-assets-inbox)`` rows.
   The fallback path is noisier and marked in the result.
3. For each (src, dst) run three safety gates:
     - src still exists
     - dst exists
     - ``stat().st_size`` matches
   **All three must pass** before deleting the source.
4. ``apply=False`` (default — *safer than the PS original which
   defaulted to real delete*) logs ``WOULD-DELETE`` only.
   ``apply=True`` performs ``unlink()``.
5. Optional empty-directory sweep under ``source_root`` after
   successful deletions (up to 5 passes to collapse nested empties).

Returns counts for all buckets (deleted, src_missing, dst_missing,
size_mismatch, failed, empty_dirs_deleted) and the log path.

Behavioural notes vs. PS:

- PS defaulted ``-DryRun`` off (real delete). Python defaults
  ``apply=False`` (dry-run). Explicit opt-in for irreversible
  operations is the brain CLI convention (see ``merge-candidates
  sync-from-graph``).
- PS hardcoded ``D:\\BaiduSyncdisk`` as the empty-dir sweep root.
  Python requires ``source_root`` to be passed explicitly (or
  skips the sweep). Safer for mixed-source workflows.
- Log file format preserved line-for-line so existing eyeballing
  habits / tooling continue to work.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from brain_core.config import load_paths_config


# ---------------------------------------------------------------------------
# Config helpers (mirror asset_migrate)
# ---------------------------------------------------------------------------

def _paths() -> dict[str, str]:
    return load_paths_config()["paths"]


def _default_assets_root() -> Path:
    p = _paths()
    return Path(p.get("assets_root") or p.get("brain_assets_root") or "D:\\second-brain-assets")


def _default_brain_root() -> Path:
    p = _paths()
    return Path(p.get("content_root") or p.get("brain_root") or "D:\\second-brain-content")


def _migration_dir(assets_root: Path) -> Path:
    return assets_root / "_migration"


def _latest_manifest(assets_root: Path) -> Path | None:
    md = _migration_dir(assets_root)
    if not md.exists():
        return None
    cands = sorted(md.glob("*-manifest.tsv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


# ---------------------------------------------------------------------------
# execute.log / manifest → OK map
# ---------------------------------------------------------------------------

def parse_execute_log(log_path: Path) -> dict[str, str]:
    """Parse ``OK\\t<src>\\t->\\t<dst>`` lines into ``{src: dst}``.

    Any other line (including ``FAIL``, ``SOURCE-MISSING``,
    ``TRASH-CANDIDATE``, or header/trailer markers) is ignored.
    """
    out: dict[str, str] = {}
    if not log_path.exists():
        return out
    for raw in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not raw.startswith("OK\t"):
            continue
        parts = raw.split("\t")
        # Expected: ["OK", src, "->", dst]
        if len(parts) < 4:
            continue
        src, arrow, dst = parts[1], parts[2], parts[3]
        if arrow != "->":
            continue
        out[src] = dst
    return out


def derive_ok_map_from_manifest(
    manifest_path: Path,
    *,
    assets_root: Path,
    brain_root: Path,
) -> dict[str, str]:
    """Less-safe fallback: infer src→dst by applying the same target
    rules as ``asset_migrate.execute`` without verifying the copy
    actually happened.

    Only rows whose ``action`` is ``copy`` or ``copy-to-assets-inbox``
    are included; ``copy-to-brain-inbox`` (text → brain content
    repo) is *excluded* on purpose — deleting a source that was
    merely queued for Tier A inbox is a human decision, not a
    cleanup-script one.
    """
    out: dict[str, str] = {}
    with manifest_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, dialect="excel-tab")
        for row in reader:
            action = (row.get("action") or "").strip()
            if action not in ("copy", "copy-to-assets-inbox"):
                continue
            target_dir = (row.get("target_dir") or "").strip()
            new_name = (row.get("new_name") or "").strip()
            src = (row.get("source_path") or "").strip()
            if not (target_dir and new_name and src):
                continue
            parts = target_dir.replace("\\", "/").split("/")
            dst = assets_root.joinpath(*parts, new_name)
            out[src] = str(dst)
    return out


# ---------------------------------------------------------------------------
# Per-file safety gate
# ---------------------------------------------------------------------------

def check_pair(src: Path, dst: Path) -> tuple[str, str]:
    """Return ``(status, detail)`` where status is one of:

    - ``ok``                — all three gates passed
    - ``src_missing``
    - ``dst_missing``
    - ``size_mismatch``
    - ``stat_failed``
    """
    if not src.exists():
        return "src_missing", ""
    if not dst.exists():
        return "dst_missing", str(dst)
    try:
        ssz = src.stat().st_size
        dsz = dst.stat().st_size
    except OSError as exc:
        return "stat_failed", str(exc)
    if ssz != dsz:
        return "size_mismatch", f"{ssz}!={dsz}"
    return "ok", ""


# ---------------------------------------------------------------------------
# Empty directory sweep
# ---------------------------------------------------------------------------

def _sweep_empty_dirs(root: Path, max_passes: int = 5) -> list[Path]:
    """Delete empty directories under ``root`` (non-recursive of
    ``root`` itself). Run multiple passes to collapse nested
    empties. Returns the list of removed dir paths in deletion
    order. Swallows per-dir OSError but records nothing for it.
    """
    deleted: list[Path] = []
    if not root.exists():
        return deleted
    for _ in range(max_passes):
        found = False
        # Walk bottom-up so deeper dirs drain first.
        for dir_path in sorted(
            (p for p in root.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            try:
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    deleted.append(dir_path)
                    found = True
            except OSError:
                continue
        if not found:
            break
    return deleted


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def cleanup(
    *,
    manifest_path: Path | None = None,
    execute_log_path: Path | None = None,
    assets_root: Path | None = None,
    brain_root: Path | None = None,
    apply: bool = False,
    source_root: Path | None = None,
    delete_empty_dirs: bool = True,
    now_fn: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    assets_root = assets_root or _default_assets_root()
    brain_root = brain_root or _default_brain_root()
    now_fn = now_fn or datetime.now

    # 1. Locate manifest
    if manifest_path is None:
        picked = _latest_manifest(assets_root)
        if picked is None:
            return {"status": "missing_manifest", "manifest_path": None}
        manifest_path = picked
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return {"status": "missing_manifest", "manifest_path": str(manifest_path)}

    # 2. Locate execute.log
    job_base = manifest_path.name.replace("-manifest.tsv", "")
    if execute_log_path is None:
        execute_log_path = manifest_path.with_name(f"{job_base}-execute.log")
    execute_log_path = Path(execute_log_path)
    cleanup_log_path = manifest_path.with_name(f"{job_base}-cleanup.log")

    ok_map: dict[str, str]
    source_of_truth: str
    if execute_log_path.exists():
        ok_map = parse_execute_log(execute_log_path)
        source_of_truth = "execute_log"
    else:
        ok_map = derive_ok_map_from_manifest(
            manifest_path, assets_root=assets_root, brain_root=brain_root
        )
        source_of_truth = "manifest_fallback"

    # 3. Iterate + gate + delete
    stats = {
        "deleted": 0,
        "src_missing": 0,
        "dst_missing": 0,
        "size_mismatch": 0,
        "failed": 0,
    }
    log_lines: list[str] = []
    mode = "APPLY" if apply else "DRY-RUN"
    log_lines.append(f"=== cleanup start {now_fn().strftime('%Y-%m-%d %H:%M:%S')} ===")
    log_lines.append(f"# 模式: {mode}")
    log_lines.append(f"# source_of_truth: {source_of_truth}")

    src_parents: set[Path] = set()

    for src_str, dst_str in ok_map.items():
        src = Path(src_str)
        dst = Path(dst_str)
        status, detail = check_pair(src, dst)
        if status == "src_missing":
            stats["src_missing"] += 1
            log_lines.append(f"SKIP-SRC-GONE\t{src}")
            continue
        if status == "dst_missing":
            stats["dst_missing"] += 1
            log_lines.append(f"SKIP-DST-MISSING\t{src}\t{detail}")
            continue
        if status == "size_mismatch":
            stats["size_mismatch"] += 1
            log_lines.append(f"SKIP-SIZE-MISMATCH\t{src}\t{detail}")
            continue
        if status == "stat_failed":
            stats["failed"] += 1
            log_lines.append(f"FAIL-STAT\t{src}\t{detail}")
            continue

        src_parents.add(src.parent)

        if not apply:
            stats["deleted"] += 1
            log_lines.append(f"WOULD-DELETE\t{src}")
            continue

        try:
            src.unlink()
            stats["deleted"] += 1
            log_lines.append(f"DELETED\t{src}")
        except OSError as exc:
            stats["failed"] += 1
            log_lines.append(f"FAIL-DELETE\t{src}\t{exc}")

    # 4. Optional empty-dir sweep
    empty_dirs_deleted: list[Path] = []
    empty_dir_sweep_status = "skipped"
    if apply and delete_empty_dirs:
        if source_root is None:
            empty_dir_sweep_status = "skipped_no_source_root"
        else:
            source_root = Path(source_root)
            empty_dirs_deleted = _sweep_empty_dirs(source_root)
            empty_dir_sweep_status = "ok"
            for d in empty_dirs_deleted:
                log_lines.append(f"DELETED-DIR\t{d}")

    log_lines.append(f"=== cleanup done {now_fn().strftime('%Y-%m-%d %H:%M:%S')} ===")

    # Ensure the parent dir exists (tests use tmp paths that may
    # not have _migration yet if fallback from manifest-less tree).
    cleanup_log_path.parent.mkdir(parents=True, exist_ok=True)
    cleanup_log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    return {
        "status": "ok",
        "mode": mode,
        "source_of_truth": source_of_truth,
        "manifest_path": str(manifest_path),
        "execute_log_path": str(execute_log_path) if execute_log_path.exists() else None,
        "cleanup_log_path": str(cleanup_log_path),
        "total_candidates": len(ok_map),
        "empty_dir_sweep": empty_dir_sweep_status,
        "empty_dirs_deleted": len(empty_dirs_deleted),
        **stats,
    }


# ---------------------------------------------------------------------------
# Public run helper (used by CLI)
# ---------------------------------------------------------------------------

def run(
    *,
    manifest_path: str | Path | None = None,
    execute_log_path: str | Path | None = None,
    assets_root: str | Path | None = None,
    brain_root: str | Path | None = None,
    source_root: str | Path | None = None,
    apply: bool = False,
    delete_empty_dirs: bool = True,
) -> dict[str, Any]:
    return cleanup(
        manifest_path=Path(manifest_path) if manifest_path else None,
        execute_log_path=Path(execute_log_path) if execute_log_path else None,
        assets_root=Path(assets_root) if assets_root else None,
        brain_root=Path(brain_root) if brain_root else None,
        source_root=Path(source_root) if source_root else None,
        apply=apply,
        delete_empty_dirs=delete_empty_dirs,
    )
