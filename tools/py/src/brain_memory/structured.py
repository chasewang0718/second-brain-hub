"""Structured memory tables in DuckDB for F3 (persons / CRM v2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from brain_core.config import load_paths_config


def _db_path() -> Path:
    logs_dir = Path(load_paths_config()["paths"]["telemetry_logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / "brain-telemetry.duckdb"


def _connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(_db_path()))


def _list_tables(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SHOW TABLES").fetchall()
    return {str(r[0]) for r in rows}


def _table_columns(conn: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    try:
        rows = conn.execute(f'DESCRIBE "{table}"').fetchall()
    except Exception:
        return set()
    return {str(r[0]) for r in rows}


def _migration_version(conn: duckdb.DuckDBPyConnection) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _brain_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM _brain_migrations").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _record_migration(conn: duckdb.DuckDBPyConnection, version: int) -> None:
    conn.execute("INSERT INTO _brain_migrations (version) VALUES (?)", [version])


def _ensure_persons_primary_key(conn: duckdb.DuckDBPyConnection) -> None:
    """CTAS migration leaves persons without PK; DuckDB INSERT OR REPLACE needs one."""
    if "persons" not in _list_tables(conn):
        return
    row = conn.execute(
        """
        SELECT COUNT(*) FROM information_schema.table_constraints
        WHERE table_schema = 'main'
          AND table_name = 'persons'
          AND constraint_type = 'PRIMARY KEY'
        """
    ).fetchone()
    if row and int(row[0]) > 0:
        return
    try:
        conn.execute("ALTER TABLE persons ADD PRIMARY KEY (person_id)")
    except Exception:
        pass


def _migrate_v1_to_v2(conn: duckdb.DuckDBPyConnection) -> None:
    """Rename legacy contacts + contact_id into persons + person_id."""
    if _migration_version(conn) >= 2:
        return
    tables = _list_tables(conn)
    if "contacts" in tables and "persons" not in tables:
        conn.execute(
            """
            CREATE TABLE persons AS
            SELECT
                id AS person_id,
                name AS primary_name,
                aliases_json,
                tags_json,
                last_seen_utc
            FROM contacts
            """
        )
        conn.execute("DROP TABLE contacts")
    if "interactions" in tables:
        cols = _table_columns(conn, "interactions")
        if "contact_id" in cols and "person_id" not in cols:
            conn.execute('ALTER TABLE interactions RENAME "contact_id" TO "person_id"')
    _record_migration(conn, 2)


def _ensure_v2_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS persons (
            person_id VARCHAR PRIMARY KEY,
            primary_name VARCHAR,
            aliases_json VARCHAR,
            tags_json VARCHAR,
            last_seen_utc TIMESTAMP
        )
        """
    )
    conn.execute("CREATE SEQUENCE IF NOT EXISTS person_identifiers_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS person_identifiers (
            id BIGINT PRIMARY KEY DEFAULT nextval('person_identifiers_id_seq'),
            person_id VARCHAR NOT NULL,
            kind VARCHAR NOT NULL,
            value_normalized VARCHAR NOT NULL,
            value_original VARCHAR,
            confidence DOUBLE DEFAULT 1.0,
            source_kind VARCHAR DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (person_id, kind, value_normalized)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS interactions (
            id BIGINT PRIMARY KEY,
            person_id VARCHAR,
            ts_utc TIMESTAMP,
            channel VARCHAR,
            summary VARCHAR,
            source_path VARCHAR,
            detail_json VARCHAR,
            source_kind VARCHAR DEFAULT '',
            source_id VARCHAR DEFAULT ''
        )
        """
    )
    conn.execute("CREATE SEQUENCE IF NOT EXISTS interactions_id_seq START 1")
    cols = _table_columns(conn, "interactions")
    if "source_kind" not in cols:
        conn.execute("ALTER TABLE interactions ADD COLUMN source_kind VARCHAR DEFAULT ''")
    if "source_id" not in cols:
        conn.execute("ALTER TABLE interactions ADD COLUMN source_id VARCHAR DEFAULT ''")

    conn.execute("CREATE SEQUENCE IF NOT EXISTS person_notes_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS person_notes (
            id BIGINT PRIMARY KEY DEFAULT nextval('person_notes_id_seq'),
            person_id VARCHAR NOT NULL,
            ts_utc TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            body TEXT,
            source_kind VARCHAR DEFAULT '',
            detail_json VARCHAR DEFAULT '{}'
        )
        """
    )

    conn.execute("CREATE SEQUENCE IF NOT EXISTS person_insights_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS person_insights (
            id BIGINT PRIMARY KEY DEFAULT nextval('person_insights_id_seq'),
            person_id VARCHAR NOT NULL,
            insight_type VARCHAR DEFAULT '',
            body TEXT,
            detail_json VARCHAR DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute("CREATE SEQUENCE IF NOT EXISTS open_threads_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS open_threads (
            id BIGINT PRIMARY KEY DEFAULT nextval('open_threads_id_seq'),
            person_id VARCHAR NOT NULL,
            summary VARCHAR,
            status VARCHAR DEFAULT 'open',
            detail_json VARCHAR DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute("CREATE SEQUENCE IF NOT EXISTS relationship_edges_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS relationship_edges (
            id BIGINT PRIMARY KEY DEFAULT nextval('relationship_edges_id_seq'),
            person_a VARCHAR NOT NULL,
            person_b VARCHAR NOT NULL,
            relation_kind VARCHAR DEFAULT '',
            detail_json VARCHAR DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute("CREATE SEQUENCE IF NOT EXISTS merge_candidates_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS merge_candidates (
            id BIGINT PRIMARY KEY DEFAULT nextval('merge_candidates_id_seq'),
            person_a VARCHAR NOT NULL,
            person_b VARCHAR NOT NULL,
            score DOUBLE DEFAULT 0.0,
            reason VARCHAR DEFAULT '',
            status VARCHAR DEFAULT 'pending',
            detail_json VARCHAR DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute("CREATE SEQUENCE IF NOT EXISTS merge_log_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS merge_log (
            id BIGINT PRIMARY KEY DEFAULT nextval('merge_log_id_seq'),
            kept_person_id VARCHAR NOT NULL,
            absorbed_person_id VARCHAR NOT NULL,
            reason VARCHAR DEFAULT '',
            detail_json VARCHAR DEFAULT '{}',
            ts_utc TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute("CREATE SEQUENCE IF NOT EXISTS cloud_queue_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_queue (
            id BIGINT PRIMARY KEY DEFAULT nextval('cloud_queue_id_seq'),
            task_kind VARCHAR NOT NULL,
            payload_json VARCHAR NOT NULL,
            priority VARCHAR DEFAULT 'normal',
            local_attempt_json VARCHAR DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR DEFAULT 'pending',
            result_json VARCHAR,
            processed_at TIMESTAMP
        )
        """
    )

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


def ensure_schema() -> None:
    conn = _connect()
    try:
        _migrate_v1_to_v2(conn)
        _ensure_v2_tables(conn)
        _ensure_persons_primary_key(conn)
        ver = _migration_version(conn)
        if ver < 2:
            _record_migration(conn, 2)
    finally:
        conn.close()


import contextlib
import threading

# Thread-local "active connection". When set, execute/query/fetch_one
# reuse it instead of opening+closing a fresh one per call. The
# ``transaction`` context manager is the only thing that should set
# this — nested use is not supported (raises).
_tx_state = threading.local()


def _active_conn() -> Any | None:
    return getattr(_tx_state, "conn", None)


@contextlib.contextmanager
def transaction() -> Any:
    """Open a persistent DuckDB connection and wrap all inner
    ``execute`` / ``query`` / ``fetch_one`` calls inside
    ``BEGIN`` / ``COMMIT`` (or ``ROLLBACK`` on exception).

    Used by real-ingest apply paths (B-ING-0) so that a partial
    failure in a multi-row insert never leaves DuckDB in a mixed
    state. Nested transactions are not supported.
    """
    if _active_conn() is not None:
        raise RuntimeError("nested transaction not supported")
    ensure_schema()
    conn = _connect()
    _tx_state.conn = conn
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        finally:
            _tx_state.conn = None
            conn.close()
        raise
    conn.execute("COMMIT")
    _tx_state.conn = None
    conn.close()


def query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    conn = _active_conn()
    close_after = False
    if conn is None:
        ensure_schema()
        conn = _connect()
        close_after = True
    try:
        cursor = conn.execute(sql, params or [])
        columns = [item[0] for item in cursor.description or []]
        rows = cursor.fetchall()
        return [{columns[i]: row[i] for i in range(len(columns))} for row in rows]
    finally:
        if close_after:
            conn.close()


def execute(sql: str, params: list[Any] | None = None) -> None:
    conn = _active_conn()
    close_after = False
    if conn is None:
        ensure_schema()
        conn = _connect()
        close_after = True
    try:
        conn.execute(sql, params or [])
    finally:
        if close_after:
            conn.close()


def fetch_one(sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None
