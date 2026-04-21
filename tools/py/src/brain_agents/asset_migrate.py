"""B3 · Python port of ``tools/asset/brain-asset-migrate.ps1``.

Two-stage pipeline:

1. **scan** (dry-run, default) — walk ``source``, run a pure classification
   rule per file, emit a tab-separated manifest under
   ``<assets_root>/_migration/<job>-manifest.tsv``. Zero token, never
   touches any file except the manifest itself.

2. **execute** — read a manifest (the most-recent one by default),
   copy each row's source to its computed destination (the copy is
   mtime-preserving), recover gracefully from missing sources,
   rename-on-collision using the source's mtime, and emit
   ``<job>-execute.log`` sibling to the manifest. **Source files are
   NEVER deleted** — the 7-day verification window is still a human
   decision, same as the PS original.

Rules mirror the PS version exactly so an existing manifest produced
by the PS script still executes correctly here.

Key behavioural contract preserved from the PS version:

- ``~/.brain-exclude.txt`` is honoured (one pattern per line,
  startswith or substring, case-insensitive, slash-normalized).
- ``trash-candidate`` rows are *logged only* and never deleted.
- ``__BRAIN_INBOX__`` sentinel in ``target_dir`` maps to
  ``<brain_content_root>/99-inbox`` instead of
  ``<assets_root>/...``.
- Name collisions append ``-YYYYMMDD-HHmmss`` (src mtime) to the
  destination.
- mtime is copied onto the destination.

Safe to exercise in tests via the three injection points:
``photo_date_fn`` (skip real EXIF), ``exclude_patterns`` (skip
``~/.brain-exclude.txt`` I/O), and ``now_fn`` (stable timestamps).
"""

from __future__ import annotations

import csv
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from brain_core.config import load_paths_config


MANIFEST_COLUMNS = (
    "source_path",
    "size_kb",
    "mtime",
    "ext",
    "rule",
    "action",
    "target_dir",
    "new_name",
    "date_source",
    "note",
)

BRAIN_INBOX_SENTINEL = "__BRAIN_INBOX__"

_PHOTO_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic"})
_VIDEO_EXTS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v"})
_AUDIO_EXTS = frozenset({".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".wma"})
_FONT_EXTS = frozenset({".ttf", ".otf", ".woff", ".woff2"})
_ARCHIVE_EXTS = frozenset({".zip", ".rar", ".7z", ".tgz", ".tar"})
_TEXT_EXTS = frozenset({".txt", ".md", ".rtf", ".tex"})
_DOCUMENT_EXTS = frozenset({".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"})
_TRASH_EXTS = frozenset({".aae", ".aux", ".log", ".ds_store", ".tmp", ".bak"})
_TRASH_NAMES = frozenset({"thumbs.db", "desktop.ini", ".ds_store"})


# ---------------------------------------------------------------------------
# Exclude list (~/.brain-exclude.txt)
# ---------------------------------------------------------------------------

def _brain_exclude_patterns() -> list[str]:
    home = Path.home() / ".brain-exclude.txt"
    if not home.exists():
        return []
    out: list[str] = []
    for line in home.read_text(encoding="utf-8", errors="ignore").splitlines():
        item = line.strip()
        if item and not item.startswith("#"):
            out.append(item)
    return out


def _norm(p: str) -> str:
    return p.replace("/", "\\").rstrip("\\").lower()


def is_excluded(path: str | Path, patterns: Iterable[str]) -> bool:
    """Return True when ``path`` is matched by any exclude pattern.

    A pattern matches if the (slash-normalized, case-insensitive)
    path either starts with it (directory/prefix match) or contains
    it as a substring. This is a conservative superset of the PS
    script's behaviour to keep parity while staying lenient.
    """
    p_norm = _norm(str(path))
    for rule in patterns:
        r = _norm(rule)
        if not r:
            continue
        if p_norm.startswith(r):
            return True
        if r in p_norm:
            return True
    return False


# ---------------------------------------------------------------------------
# Photo date (EXIF with mtime fallback)
# ---------------------------------------------------------------------------

PhotoDateFn = Callable[[Path], "tuple[datetime, str]"]


def _default_photo_date_fn(path: Path) -> tuple[datetime, str]:
    """Return (datetime, source) where source is ``exif`` or ``mtime``.

    Pillow is imported lazily so test environments without it still
    work (they just fall back to mtime).
    """
    try:
        from PIL import Image  # type: ignore
        from PIL.ExifTags import TAGS  # type: ignore

        with Image.open(path) as img:
            exif = getattr(img, "_getexif", lambda: None)()
            if exif:
                for tag_id, value in exif.items():
                    if TAGS.get(tag_id) == "DateTimeOriginal" and isinstance(value, str):
                        # Format: "YYYY:MM:DD HH:MM:SS"
                        dt = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                        return dt, "exif"
    except Exception:
        pass
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return mtime, "mtime"


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

@dataclass
class Classification:
    rule: str
    target_dir: str
    new_name: str
    date_source: str
    action: str

    def as_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "target_dir": self.target_dir,
            "new_name": self.new_name,
            "date_source": self.date_source,
            "action": self.action,
        }


def classify_file(
    path: Path,
    *,
    photo_date_fn: PhotoDateFn | None = None,
) -> Classification:
    ext = path.suffix.lower()
    name = path.name.lower()

    # Trash / system files first (can win over ext rules if name matches)
    if ext in _TRASH_EXTS or name in _TRASH_NAMES:
        return Classification("trash", "-", "-", "-", "trash-candidate")

    if ext in _PHOTO_EXTS:
        fn = photo_date_fn or _default_photo_date_fn
        try:
            dt, src = fn(path)
        except Exception:
            dt, src = datetime.fromtimestamp(path.stat().st_mtime), "mtime"
        ym = dt.strftime("%Y-%m")
        return Classification("photo", f"10-photos\\{ym}", path.name, src, "copy")

    if ext in _VIDEO_EXTS:
        dt = datetime.fromtimestamp(path.stat().st_mtime)
        ym = dt.strftime("%Y-%m")
        return Classification("video", f"12-video\\{ym}", path.name, "mtime", "copy")

    if ext in _AUDIO_EXTS:
        return Classification("audio", "13-audio", path.name, "-", "copy")

    if ext in _FONT_EXTS:
        return Classification("font", "11-fonts", path.name, "-", "copy")

    if ext in _ARCHIVE_EXTS:
        return Classification("archive", "14-archives", path.name, "-", "copy")

    if ext in _TEXT_EXTS:
        return Classification("text", BRAIN_INBOX_SENTINEL, path.name, "-", "copy-to-brain-inbox")

    if ext == ".pdf":
        return Classification("pdf", "99-inbox", path.name, "-", "copy-to-assets-inbox")

    if ext in _DOCUMENT_EXTS:
        return Classification("document", "99-inbox", path.name, "-", "copy-to-assets-inbox")

    return Classification("other", "98-staging", path.name, "-", "copy")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _paths() -> dict[str, str]:
    return load_paths_config()["paths"]


def _default_assets_root() -> Path:
    p = _paths()
    return Path(p.get("assets_root") or p.get("brain_assets_root") or "D:\\second-brain-assets")


def _default_brain_root() -> Path:
    p = _paths()
    return Path(p.get("content_root") or p.get("brain_root") or "D:\\second-brain-content")


def migration_dir(assets_root: Path | None = None) -> Path:
    return (assets_root or _default_assets_root()) / "_migration"


# ---------------------------------------------------------------------------
# SCAN
# ---------------------------------------------------------------------------

def _format_mtime(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def scan(
    source: Path,
    *,
    job_name: str,
    assets_root: Path | None = None,
    exclude_patterns: Sequence[str] | None = None,
    photo_date_fn: PhotoDateFn | None = None,
    write_manifest: bool = True,
) -> dict[str, Any]:
    """Walk ``source`` and build a manifest.

    Returns a dict with:

    - ``status``: ``ok`` | ``missing_source``
    - ``manifest_path``: where the TSV was written (when
      ``write_manifest=True``)
    - ``rows``: list of row dicts (same columns as the TSV)
    - ``counts``: Counter-like mapping ``{rule: count}``
    - ``sizes``: ``{rule: total_bytes}``
    - ``excluded``: number of files dropped by exclude patterns
    - ``total``: total files visited (including excluded)
    """
    source = Path(source)
    if not source.exists():
        return {
            "status": "missing_source",
            "source": str(source),
            "rows": [],
            "counts": {},
            "sizes": {},
            "excluded": 0,
            "total": 0,
        }

    assets_root = assets_root or _default_assets_root()
    patterns = list(exclude_patterns) if exclude_patterns is not None else _brain_exclude_patterns()

    rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    sizes: dict[str, int] = {}
    excluded = 0
    total = 0

    for root, dirs, files in os.walk(source, followlinks=False):
        for fname in files:
            total += 1
            fpath = Path(root) / fname
            if is_excluded(str(fpath), patterns):
                excluded += 1
                continue
            try:
                st = fpath.stat()
            except OSError:
                continue

            cls = classify_file(fpath, photo_date_fn=photo_date_fn)
            size_kb = round(st.st_size / 1024, 1)
            rows.append(
                {
                    "source_path": str(fpath),
                    "size_kb": f"{size_kb}",
                    "mtime": _format_mtime(st.st_mtime),
                    "ext": fpath.suffix.lower(),
                    "rule": cls.rule,
                    "action": cls.action,
                    "target_dir": cls.target_dir,
                    "new_name": cls.new_name,
                    "date_source": cls.date_source,
                    "note": "",
                }
            )
            counts[cls.rule] = counts.get(cls.rule, 0) + 1
            sizes[cls.rule] = sizes.get(cls.rule, 0) + st.st_size

    out: dict[str, Any] = {
        "status": "ok",
        "source": str(source),
        "job_name": job_name,
        "rows": rows,
        "counts": counts,
        "sizes": sizes,
        "excluded": excluded,
        "total": total,
    }

    if write_manifest:
        md = migration_dir(assets_root)
        md.mkdir(parents=True, exist_ok=True)
        manifest_path = md / f"{job_name}-manifest.tsv"
        with manifest_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(MANIFEST_COLUMNS),
                dialect="excel-tab",
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        out["manifest_path"] = str(manifest_path)

    return out


# ---------------------------------------------------------------------------
# EXECUTE
# ---------------------------------------------------------------------------

def _latest_manifest(assets_root: Path | None = None) -> Path | None:
    md = migration_dir(assets_root)
    if not md.exists():
        return None
    candidates = sorted(
        md.glob("*-manifest.tsv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, dialect="excel-tab")
        return [dict(row) for row in reader]


def _resolve_dest_root(
    target_dir: str,
    *,
    assets_root: Path,
    brain_root: Path,
) -> tuple[Path, bool]:
    """Return (dest_root, is_brain_inbox)."""
    if target_dir == BRAIN_INBOX_SENTINEL:
        return brain_root / "99-inbox", True
    # target_dir may come in as either ``10-photos\2024-01`` or
    # ``10-photos/2024-01``; normalize both.
    parts = target_dir.replace("\\", "/").split("/")
    return assets_root.joinpath(*parts), False


def _resolve_collision(dest: Path, source: Path) -> Path:
    if not dest.exists():
        return dest
    src_mtime = datetime.fromtimestamp(source.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
    return dest.with_name(f"{dest.stem}-{src_mtime}{dest.suffix}")


def execute(
    manifest_path: Path | None = None,
    *,
    assets_root: Path | None = None,
    brain_root: Path | None = None,
    progress_every: int = 200,
    now_fn: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Apply a manifest. ``manifest_path=None`` picks the most
    recent ``*-manifest.tsv`` under ``_migration/``.
    """
    assets_root = assets_root or _default_assets_root()
    brain_root = brain_root or _default_brain_root()
    now_fn = now_fn or datetime.now

    if manifest_path is None:
        picked = _latest_manifest(assets_root)
        if picked is None:
            return {"status": "missing_manifest", "manifest_path": None}
        manifest_path = picked
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return {"status": "missing_manifest", "manifest_path": str(manifest_path)}

    rows = _read_manifest(manifest_path)
    log_path = manifest_path.with_name(
        manifest_path.name.replace("-manifest.tsv", "-execute.log")
    )

    stats = {
        "copied": 0,
        "skipped": 0,
        "failed": 0,
        "trash_marked": 0,
        "to_brain_inbox": 0,
    }

    lines: list[str] = []
    lines.append(f"=== Execute start {now_fn().strftime('%Y-%m-%d %H:%M:%S')} ===")

    for idx, row in enumerate(rows, 1):
        action = row.get("action", "")
        src = row.get("source_path", "")

        if action == "trash-candidate":
            stats["trash_marked"] += 1
            lines.append(f"TRASH-CANDIDATE\t{src}")
            continue

        src_path = Path(src)
        if not src_path.exists():
            stats["skipped"] += 1
            lines.append(f"SOURCE-MISSING\t{src}")
            continue

        target_dir = row.get("target_dir", "")
        new_name = row.get("new_name") or src_path.name
        dest_root, is_brain = _resolve_dest_root(
            target_dir, assets_root=assets_root, brain_root=brain_root
        )
        if is_brain:
            stats["to_brain_inbox"] += 1

        dest_root.mkdir(parents=True, exist_ok=True)
        dest_path = _resolve_collision(dest_root / new_name, src_path)

        try:
            shutil.copy2(src_path, dest_path)
            # shutil.copy2 already preserves mtime, but re-stamp to
            # guarantee parity with the PS script on exotic FS.
            st = src_path.stat()
            os.utime(dest_path, (st.st_atime, st.st_mtime))
            stats["copied"] += 1
            lines.append(f"OK\t{src}\t->\t{dest_path}")
        except Exception as exc:  # noqa: BLE001 — log everything
            stats["failed"] += 1
            lines.append(f"FAIL\t{src}\t{exc}")

    lines.append(f"=== Execute done {now_fn().strftime('%Y-%m-%d %H:%M:%S')} ===")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "status": "ok",
        "manifest_path": str(manifest_path),
        "log_path": str(log_path),
        "rows_total": len(rows),
        **stats,
    }


# ---------------------------------------------------------------------------
# Public run helpers (used by CLI)
# ---------------------------------------------------------------------------

def run_scan(
    *,
    source: str | Path,
    job_name: str | None = None,
    assets_root: str | Path | None = None,
    exclude_patterns: Sequence[str] | None = None,
) -> dict[str, Any]:
    job = job_name or f"job-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    return scan(
        Path(source),
        job_name=job,
        assets_root=Path(assets_root) if assets_root else None,
        exclude_patterns=exclude_patterns,
    )


def run_execute(
    *,
    manifest_path: str | Path | None = None,
    assets_root: str | Path | None = None,
    brain_root: str | Path | None = None,
) -> dict[str, Any]:
    return execute(
        manifest_path=Path(manifest_path) if manifest_path else None,
        assets_root=Path(assets_root) if assets_root else None,
        brain_root=Path(brain_root) if brain_root else None,
    )
