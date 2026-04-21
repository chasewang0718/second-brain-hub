"""DuckDB-backed telemetry storage for F1.1."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from brain_core.config import load_paths_config


def _telemetry_db_path() -> Path:
    paths = load_paths_config()["paths"]
    logs_dir = Path(paths["telemetry_logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / "brain-telemetry.duckdb"


def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(_telemetry_db_path()))


def ensure_schema() -> None:
    conn = _conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry_events (
            id BIGINT PRIMARY KEY,
            ts_utc TIMESTAMP,
            source VARCHAR,
            event VARCHAR,
            detail_json VARCHAR
        )
        """
    )
    conn.execute("CREATE SEQUENCE IF NOT EXISTS telemetry_event_id_seq START 1")
    conn.close()


def normalize_detail_json(raw: str) -> str:
    candidate = (raw or "").lstrip("\ufeff").strip()
    if not candidate:
        return "{}"
    parsed = json.loads(candidate)
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True)


def append_event(source: str, event: str, detail_json: str = "{}") -> int:
    ensure_schema()
    conn = _conn()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    normalized = normalize_detail_json(detail_json)
    row = conn.execute(
        """
        INSERT INTO telemetry_events
            (id, ts_utc, source, event, detail_json)
        VALUES
            (nextval('telemetry_event_id_seq'), ?, ?, ?, ?)
        RETURNING id
        """,
        [now, source, event, normalized],
    ).fetchone()
    conn.close()
    return int(row[0])


def list_recent(limit: int = 10) -> list[dict[str, Any]]:
    ensure_schema()
    conn = _conn()
    rows = conn.execute(
        """
        SELECT id, ts_utc, source, event, detail_json
        FROM telemetry_events
        ORDER BY id DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "ts_utc": str(r[1]),
            "source": r[2],
            "event": r[3],
            "detail_json": r[4],
        }
        for r in rows
    ]

