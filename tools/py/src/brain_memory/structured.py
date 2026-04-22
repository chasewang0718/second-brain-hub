"""Structured memory tables in DuckDB for F3 (persons / CRM v2)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb

from brain_core.config import load_paths_config


def _db_path() -> Path:
    """Resolve the DuckDB file.

    Precedence:
    1. ``BRAIN_DB_PATH`` env var (non-empty) — used by pytest (B-ING-1.5) to
       point the whole stack at a throwaway tmp file so test fixtures like
       ``ensure_person_with_seed("T Reject A", ...)`` never leak into the
       production telemetry DB again.
    2. ``paths.yaml`` → ``telemetry_logs_dir`` / ``brain-telemetry.duckdb``.
    """
    override = os.environ.get("BRAIN_DB_PATH", "").strip()
    if override:
        path = Path(override).expanduser()
        parent = path.parent
        if str(parent) and parent != Path():
            parent.mkdir(parents=True, exist_ok=True)
        return path
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            window_start_utc TIMESTAMP,
            window_end_utc TIMESTAMP,
            source_kind VARCHAR DEFAULT '',
            superseded_by BIGINT
        )
        """
    )
    # v5 · Phase A6 Sprint 3: add versioning columns (superseded_by chain +
    # window markers) so a rebuild can preserve history the same way
    # person_facts does. All existing rows get NULL defaults, which is
    # backward compatible: a NULL `superseded_by` means "currently valid".
    _pi_cols = _table_columns(conn, "person_insights")
    for col, ddl in (
        ("window_start_utc", "TIMESTAMP"),
        ("window_end_utc", "TIMESTAMP"),
        ("source_kind", "VARCHAR DEFAULT ''"),
        ("superseded_by", "BIGINT"),
    ):
        if col not in _pi_cols:
            conn.execute(f"ALTER TABLE person_insights ADD COLUMN {col} {ddl}")

    conn.execute("CREATE SEQUENCE IF NOT EXISTS open_threads_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS open_threads (
            id BIGINT PRIMARY KEY DEFAULT nextval('open_threads_id_seq'),
            person_id VARCHAR NOT NULL,
            summary VARCHAR,
            status VARCHAR DEFAULT 'open',
            detail_json VARCHAR DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            due_utc TIMESTAMP,
            promised_by VARCHAR,
            last_mentioned_utc TIMESTAMP,
            source_interaction_id BIGINT,
            source_kind VARCHAR DEFAULT 'manual',
            body_hash VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # v4 · Phase A6 Sprint 2: backfill commitment columns on existing DBs
    # (CREATE TABLE above only applies to fresh DBs; production DBs with v3
    # schema must pick up the new columns via ALTER TABLE).
    _ot_cols = _table_columns(conn, "open_threads")
    for col, ddl in (
        ("due_utc", "TIMESTAMP"),
        ("promised_by", "VARCHAR"),
        ("last_mentioned_utc", "TIMESTAMP"),
        ("source_interaction_id", "BIGINT"),
        ("source_kind", "VARCHAR DEFAULT 'manual'"),
        ("body_hash", "VARCHAR"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ):
        if col not in _ot_cols:
            conn.execute(f"ALTER TABLE open_threads ADD COLUMN {col} {ddl}")

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

    # --- v3 · Phase A6 (Dynamic Person Profile) ---
    # person_facts: bi-temporal key-value store. value_json is ALWAYS a JSON
    # document (json.dumps-ed string/number/object/array). valid_to IS NULL
    # means "currently valid"; writing a new fact for the same (person_id, key)
    # must close the old row first (see brain_agents.person_facts.add_fact).
    conn.execute("CREATE SEQUENCE IF NOT EXISTS person_facts_id_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS person_facts (
            id BIGINT PRIMARY KEY DEFAULT nextval('person_facts_id_seq'),
            person_id VARCHAR NOT NULL,
            key VARCHAR NOT NULL,
            value_json VARCHAR NOT NULL,
            valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            valid_to TIMESTAMP,
            confidence DOUBLE DEFAULT 1.0,
            source_kind VARCHAR DEFAULT 'manual',
            source_interaction_id BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # person_metrics: overwrite-style derived table. ALL rows are recomputable
    # from interactions via brain_agents.person_metrics.recompute_all(). Never
    # treat this as source of truth — nuke + rebuild is always safe.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS person_metrics (
            person_id VARCHAR PRIMARY KEY,
            first_seen_utc TIMESTAMP,
            last_seen_utc TIMESTAMP,
            last_interaction_channel VARCHAR,
            interactions_all BIGINT DEFAULT 0,
            interactions_30d BIGINT DEFAULT 0,
            interactions_90d BIGINT DEFAULT 0,
            distinct_channels_30d INTEGER DEFAULT 0,
            dormancy_days INTEGER,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_schema() -> None:
    conn = _connect()
    try:
        _migrate_v1_to_v2(conn)
        _ensure_v2_tables(conn)
        _ensure_persons_primary_key(conn)
        ver = _migration_version(conn)
        if ver < 2:
            _record_migration(conn, 2)
        if ver < 3:
            _record_migration(conn, 3)
        if ver < 4:
            _record_migration(conn, 4)
        if ver < 5:
            _record_migration(conn, 5)
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
