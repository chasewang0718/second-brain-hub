"""B-ING-0 · Structured ingest event log (JSONL, append-only).

One line per ingest apply (or dry-run, if the caller asks). Lives at::

    <telemetry_logs_dir>/ingest-YYYY-MM-DD.jsonl

Schema (required keys)::

    ts_utc          ISO-8601 UTC string (event written ≈ ingest end)
    started_at      ISO-8601 UTC string when known (explicit or derived from ts_utc − elapsed_ms)
    source          "ios_addressbook" | "whatsapp_ios" | "wechat" | ...
    mode            "dry_run" | "apply"
    status          "ok" | "error" | "dry_run" | <module-specific>
    source_path     absolute path of the file read (may be None)
    source_sha256   sha256 of the source file (None on dry_run)
    persons_added   int (>=0)
    interactions_added int (>=0)
    identifiers_added  int (>=0)
    t3_queued       int (>=0)
    elapsed_ms      number
    backup          snapshot descriptor dict or None
    detail          free-form (original stats dict from the agent)

Philosophy: we **never** block on this. If the log file can't be
written (disk full, permission denied, etc.), we swallow the
IOError and return {"status":"log_skipped","reason":...}; ingest
itself is the source of truth, the log is the audit trail.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config


def _log_dir() -> Path:
    logs_dir = Path(load_paths_config()["paths"]["telemetry_logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def log_file_for(now: datetime | None = None) -> Path:
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return _log_dir() / f"ingest-{ts}.jsonl"


def _safe_sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        p = Path(path)
    except TypeError:
        return None
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    try:
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def log_ingest_event(
    *,
    source: str,
    mode: str,
    stats: dict[str, Any],
    source_path: str | Path | None = None,
    elapsed_ms: float | None = None,
    started_at_utc: datetime | None = None,
    backup: dict[str, Any] | None = None,
    now: datetime | None = None,
    log_dir: Path | None = None,
) -> dict[str, Any]:
    """Append one event line to ``ingest-YYYY-MM-DD.jsonl`` and
    return the event dict (caller can log/display it).

    Never raises: any ``OSError`` writing the log is caught and
    returned as ``{"status":"log_skipped","reason":...}``.
    """
    ts = now or datetime.now(timezone.utc)
    sp = Path(source_path) if source_path else None
    sha = _safe_sha256(sp) if mode == "apply" else None

    start_dt: datetime | None = started_at_utc
    if start_dt is None and elapsed_ms is not None:
        try:
            start_dt = ts - timedelta(milliseconds=float(elapsed_ms))
        except (TypeError, ValueError, OverflowError):
            start_dt = None

    event = {
        "ts_utc": ts.isoformat(timespec="seconds"),
        "started_at": start_dt.isoformat(timespec="seconds") if start_dt else None,
        "source": str(source),
        "mode": str(mode),
        "status": str(stats.get("status", "unknown")),
        "source_path": str(sp) if sp else None,
        "source_sha256": sha,
        "persons_added": int(stats.get("persons_created", 0) or 0),
        "interactions_added": int(stats.get("inserted", 0) or 0),
        "identifiers_added": int(stats.get("identifiers_added", 0) or 0),
        "t3_queued": int(stats.get("t3_queued", 0) or 0),
        "elapsed_ms": round(float(elapsed_ms), 1) if elapsed_ms is not None else None,
        "backup": backup,
        "detail": {k: v for k, v in stats.items() if k != "sample"},
    }

    log_path = (log_dir / f"ingest-{ts.strftime('%Y-%m-%d')}.jsonl") if log_dir else log_file_for(ts)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        return {"status": "log_skipped", "reason": str(exc), "event": event}

    return {"status": "logged", "event": event, "path": str(log_path)}


def list_recent_events(
    *,
    days: int = 7,
    source: str | None = None,
    log_dir: Path | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Read up to ``limit`` most recent events from the last ``days`` of
    daily log files. Optional ``source`` filter.
    """
    base = log_dir or _log_dir()
    today = datetime.now(timezone.utc).date()
    files: list[Path] = []
    for d in range(max(1, int(days))):
        stamp = (today.toordinal() - d)
        date = type(today).fromordinal(stamp)
        f = base / f"ingest-{date.strftime('%Y-%m-%d')}.jsonl"
        if f.exists():
            files.append(f)

    out: list[dict[str, Any]] = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if source and ev.get("source") != source:
                continue
            out.append(ev)
    out.sort(key=lambda r: r.get("ts_utc", ""), reverse=True)
    return out[: max(1, int(limit))]
