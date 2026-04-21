"""F3 Kuzu POC: build a read-only graph view from DuckDB CRM tables.

Inputs (DuckDB, brain-telemetry.duckdb):
  - persons(person_id, primary_name, last_seen_utc)
  - person_identifiers(person_id, kind, value_normalized)
  - relationship_edges(person_a, person_b, relation_kind)
  - interactions(person_id, ts_utc, channel)  -- fallback edges

Output (Kuzu, telemetry_logs_dir/kuzu-graph/):
  Node tables:
    Person(person_id, display_name, last_seen_utc)
    Identifier(value_normalized, kind)
  Rel tables:
    Interacted(FROM Person TO Person, reason, score)
    HasIdentifier(FROM Person TO Identifier)

Rebuilds the Kuzu dir from scratch each call (cheap: derived data).
Kuzu is imported lazily so the hub does not hard-depend on it.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import duckdb

from brain_core.config import load_paths_config


DB_FILENAME = "brain.kuzu"


def default_kuzu_dir() -> Path:
    logs_dir = Path(load_paths_config()["paths"]["telemetry_logs_dir"])
    return logs_dir / "kuzu-graph"


def _db_file(kuzu_dir: Path) -> Path:
    """Kuzu treats the path as a DB file (with sidecars). We standardize
    on ``<kuzu_dir>/brain.kuzu`` so the directory stays self-contained
    and clean.
    """
    return kuzu_dir / DB_FILENAME


def _duckdb_path() -> Path:
    logs_dir = Path(load_paths_config()["paths"]["telemetry_logs_dir"])
    return logs_dir / "brain-telemetry.duckdb"


def _clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def _fetch_all(conn: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    try:
        return conn.execute(sql).fetchall()
    except Exception:
        return []


def _derive_coactivity_edges(conn: duckdb.DuckDBPyConnection) -> list[tuple[str, str, float, str]]:
    """Derive Person↔Person edges from interactions: two persons are
    linked when they have interactions on the same channel + calendar
    day. Returns list of (a, b, score, reason) with a<b.
    """
    rows = _fetch_all(
        conn,
        """
        WITH paired AS (
            SELECT
                i1.person_id AS a,
                i2.person_id AS b,
                date_trunc('day', i1.ts_utc) AS d,
                i1.channel AS ch
            FROM interactions i1
            JOIN interactions i2
              ON i1.person_id < i2.person_id
             AND i1.channel = i2.channel
             AND date_trunc('day', i1.ts_utc) = date_trunc('day', i2.ts_utc)
            WHERE i1.person_id IS NOT NULL
              AND i2.person_id IS NOT NULL
        )
        SELECT a, b, COUNT(*)::DOUBLE AS score
        FROM paired
        GROUP BY a, b
        """,
    )
    out: list[tuple[str, str, float, str]] = []
    for a, b, score in rows:
        out.append((str(a), str(b), float(score or 0.0), "co-activity"))
    return out


def build_graph(kuzu_dir: Path | None = None) -> dict[str, Any]:
    """Rebuild the Kuzu graph from the live DuckDB snapshot.

    Returns a stats dict: {persons, identifiers, interacted_edges,
    has_identifier_edges, path}.
    Raises ``RuntimeError`` when kuzu is not importable (caller
    should catch and fall back).
    """
    try:
        import kuzu  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"kuzu_missing:{exc.__class__.__name__}") from exc

    kuzu_dir = kuzu_dir or default_kuzu_dir()
    _clean_dir(kuzu_dir)

    db_file = _db_file(kuzu_dir)
    duckdb_path = _duckdb_path()
    if not duckdb_path.exists():
        # no data yet: emit an empty graph so queries return cleanly
        db = kuzu.Database(str(db_file))
        conn = kuzu.Connection(db)
        conn.execute(
            "CREATE NODE TABLE Person(person_id STRING, display_name STRING, last_seen_utc TIMESTAMP, PRIMARY KEY(person_id))"
        )
        conn.execute(
            "CREATE NODE TABLE Identifier(value_normalized STRING, kind STRING, PRIMARY KEY(value_normalized))"
        )
        conn.execute("CREATE REL TABLE Interacted(FROM Person TO Person, reason STRING, score DOUBLE)")
        conn.execute("CREATE REL TABLE HasIdentifier(FROM Person TO Identifier)")
        return {
            "persons": 0,
            "identifiers": 0,
            "interacted_edges": 0,
            "has_identifier_edges": 0,
            "path": str(kuzu_dir),
            "duckdb_missing": True,
        }

    src = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        persons = _fetch_all(
            src,
            "SELECT person_id, COALESCE(primary_name, ''), last_seen_utc FROM persons",
        )
        identifiers = _fetch_all(
            src,
            "SELECT DISTINCT value_normalized, kind FROM person_identifiers WHERE value_normalized IS NOT NULL",
        )
        has_ident = _fetch_all(
            src,
            "SELECT person_id, value_normalized FROM person_identifiers WHERE value_normalized IS NOT NULL",
        )
        rel_edges = _fetch_all(
            src,
            """
            SELECT person_a, person_b, COALESCE(relation_kind, 'edge')
            FROM relationship_edges
            WHERE person_a IS NOT NULL AND person_b IS NOT NULL
            """,
        )
        coact = _derive_coactivity_edges(src)
    finally:
        src.close()

    db = kuzu.Database(str(db_file))
    conn = kuzu.Connection(db)
    conn.execute(
        "CREATE NODE TABLE Person(person_id STRING, display_name STRING, last_seen_utc TIMESTAMP, PRIMARY KEY(person_id))"
    )
    conn.execute(
        "CREATE NODE TABLE Identifier(value_normalized STRING, kind STRING, PRIMARY KEY(value_normalized))"
    )
    conn.execute("CREATE REL TABLE Interacted(FROM Person TO Person, reason STRING, score DOUBLE)")
    conn.execute("CREATE REL TABLE HasIdentifier(FROM Person TO Identifier)")

    seen_persons: set[str] = set()
    for pid, name, last_seen in persons:
        if not pid or pid in seen_persons:
            continue
        seen_persons.add(pid)
        conn.execute(
            "CREATE (:Person {person_id: $pid, display_name: $name, last_seen_utc: $ts})",
            {"pid": str(pid), "name": str(name or ""), "ts": last_seen},
        )

    seen_idents: set[str] = set()
    for value, kind in identifiers:
        if not value or value in seen_idents:
            continue
        seen_idents.add(value)
        conn.execute(
            "CREATE (:Identifier {value_normalized: $v, kind: $k})",
            {"v": str(value), "k": str(kind or "")},
        )

    has_ident_count = 0
    for pid, value in has_ident:
        if pid not in seen_persons or value not in seen_idents:
            continue
        conn.execute(
            "MATCH (p:Person {person_id: $pid}), (i:Identifier {value_normalized: $v}) "
            "CREATE (p)-[:HasIdentifier]->(i)",
            {"pid": str(pid), "v": str(value)},
        )
        has_ident_count += 1

    interacted_count = 0
    for a, b, reason in rel_edges:
        if a not in seen_persons or b not in seen_persons:
            continue
        conn.execute(
            "MATCH (x:Person {person_id: $a}), (y:Person {person_id: $b}) "
            "CREATE (x)-[:Interacted {reason: $r, score: 1.0}]->(y)",
            {"a": str(a), "b": str(b), "r": str(reason or "edge")},
        )
        interacted_count += 1

    for a, b, score, reason in coact:
        if a not in seen_persons or b not in seen_persons:
            continue
        conn.execute(
            "MATCH (x:Person {person_id: $a}), (y:Person {person_id: $b}) "
            "CREATE (x)-[:Interacted {reason: $r, score: $s}]->(y)",
            {"a": a, "b": b, "r": reason, "s": score},
        )
        interacted_count += 1

    return {
        "persons": len(seen_persons),
        "identifiers": len(seen_idents),
        "interacted_edges": interacted_count,
        "has_identifier_edges": has_ident_count,
        "path": str(kuzu_dir),
    }
