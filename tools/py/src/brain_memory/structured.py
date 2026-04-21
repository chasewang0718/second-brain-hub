"""Structured memory tables in DuckDB for F3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from brain_core.config import load_paths_config


def _db_path() -> Path:
    logs_dir = Path(load_paths_config()["paths"]["telemetry_logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / "brain-telemetry.duckdb"


def ensure_schema() -> None:
    conn = duckdb.connect(str(_db_path()))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id VARCHAR PRIMARY KEY,
            name VARCHAR,
            aliases_json VARCHAR,
            tags_json VARCHAR,
            last_seen_utc TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS interactions (
            id BIGINT PRIMARY KEY,
            contact_id VARCHAR,
            ts_utc TIMESTAMP,
            channel VARCHAR,
            summary VARCHAR,
            source_path VARCHAR,
            detail_json VARCHAR
        )
        """
    )
    conn.execute("CREATE SEQUENCE IF NOT EXISTS interactions_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS escalations (
            id BIGINT PRIMARY KEY,
            ts_utc TIMESTAMP,
            queue_file VARCHAR,
            reason VARCHAR,
            status VARCHAR,
            detail_json VARCHAR
        )
        """
    )
    conn.execute("CREATE SEQUENCE IF NOT EXISTS escalations_id_seq START 1")
    conn.close()


def query(sql: str) -> list[dict[str, Any]]:
    ensure_schema()
    conn = duckdb.connect(str(_db_path()))
    cursor = conn.execute(sql)
    columns = [item[0] for item in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    return [{columns[i]: row[i] for i in range(len(columns))} for row in rows]


def execute(sql: str, params: list[Any] | None = None) -> None:
    ensure_schema()
    conn = duckdb.connect(str(_db_path()))
    conn.execute(sql, params or [])
    conn.close()

