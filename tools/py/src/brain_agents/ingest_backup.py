"""B-ING-0 · Snapshot ``brain-telemetry.duckdb`` before a real ingest.

Usage (CLI):

    brain ingest-backup-now --label ios-addressbook

Produces::

    D:\\second-brain-assets\\_backup\\telemetry\\
        20260421-215430-ios-addressbook.duckdb
        20260421-215430-ios-addressbook.sha256.txt
        pointer-log.jsonl          # append-only index of every snapshot

The ``_backup`` root is read from ``paths.brain_assets_root`` (when
present) or falls back to ``<telemetry_logs_dir>/_backup`` so the test
suite can run without D:\\ being present.

Philosophy: snapshots are **copies**, not exports. Restoring is a
``copy-overwrite`` of the .duckdb file back into place — the user
should be able to roll back without running any Python.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config


LABEL_WHITELIST = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"


def _safe_label(label: str | None) -> str:
    if not label:
        return "manual"
    cleaned = "".join(c if c in LABEL_WHITELIST else "-" for c in label).strip("-_.")
    return cleaned or "manual"


def _duckdb_path() -> Path:
    logs_dir = Path(load_paths_config()["paths"]["telemetry_logs_dir"])
    return logs_dir / "brain-telemetry.duckdb"


def backup_root() -> Path:
    """Directory that holds ``telemetry/`` subdir and ``pointer-log.jsonl``.

    Prefers ``paths.brain_assets_root`` (production); falls back to
    ``telemetry_logs_dir/_backup`` so tests without D:\\ still work.
    """
    paths = load_paths_config()["paths"]
    assets = paths.get("brain_assets_root") or ""
    if assets:
        root = Path(assets) / "_backup"
    else:
        root = Path(paths["telemetry_logs_dir"]) / "_backup"
    return root


def _sha256_file(path: Path, *, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            buf = fh.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def snapshot_duckdb(
    *,
    label: str | None = None,
    source: Path | None = None,
    dest_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Copy the DuckDB file to ``<dest_root>/telemetry/<ts>-<label>.duckdb``
    and return a descriptor dict.

    The descriptor is also appended (one JSON per line) to
    ``<dest_root>/telemetry/pointer-log.jsonl`` for future audit.

    Returns::

        {
          "status": "ok" | "source_missing",
          "source": ...,
          "snapshot": ...,
          "sha256": ...,
          "bytes": ...,
          "elapsed_ms": ...,
          "label": ...,
          "ts_utc": ...,
        }
    """
    src = source or _duckdb_path()
    if not src.exists():
        return {"status": "source_missing", "source": str(src)}

    root = (dest_root or backup_root()) / "telemetry"
    root.mkdir(parents=True, exist_ok=True)

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    lbl = _safe_label(label)
    snap = root / f"{stamp}-{lbl}.duckdb"
    sha_file = root / f"{stamp}-{lbl}.sha256.txt"

    t0 = datetime.now(timezone.utc)
    shutil.copy2(src, snap)
    sha = _sha256_file(snap)
    sha_file.write_text(f"{sha}  {snap.name}\n", encoding="utf-8")
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()

    descriptor = {
        "status": "ok",
        "source": str(src),
        "snapshot": str(snap),
        "sha256": sha,
        "bytes": snap.stat().st_size,
        "elapsed_ms": round(elapsed * 1000, 1),
        "label": lbl,
        "ts_utc": stamp,
    }

    pointer_log = root / "pointer-log.jsonl"
    with pointer_log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(descriptor, ensure_ascii=False) + "\n")

    return descriptor


def list_snapshots(dest_root: Path | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` snapshot descriptors (newest first)."""
    root = (dest_root or backup_root()) / "telemetry"
    pointer_log = root / "pointer-log.jsonl"
    if not pointer_log.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in pointer_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.sort(key=lambda r: r.get("ts_utc", ""), reverse=True)
    return out[: max(1, int(limit))]
