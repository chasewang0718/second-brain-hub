"""Kuzu graph schema bootstrap for F3."""

from __future__ import annotations

from pathlib import Path

import kuzu

from brain_core.config import load_paths_config


def _db_path() -> Path:
    logs_dir = Path(load_paths_config()["paths"]["telemetry_logs_dir"])
    path = logs_dir.parent / "kuzu-memory.kuzu"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_schema() -> dict[str, str]:
    db = kuzu.Database(str(_db_path()))
    conn = kuzu.Connection(db)
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Person(id STRING, name STRING, PRIMARY KEY(id));")
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Org(id STRING, name STRING, PRIMARY KEY(id));")
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Topic(id STRING, name STRING, PRIMARY KEY(id));")
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Event(id STRING, name STRING, ts STRING, PRIMARY KEY(id));")
    conn.execute(
        "CREATE REL TABLE IF NOT EXISTS MENTIONS(FROM Person TO Topic, source STRING, ts STRING);"
    )
    conn.execute("CREATE REL TABLE IF NOT EXISTS WORKS_AT(FROM Person TO Org, source STRING, ts STRING);")
    conn.execute(
        "CREATE REL TABLE IF NOT EXISTS RELATED_TO(FROM Topic TO Topic, source STRING, score DOUBLE);"
    )
    return {"db_path": str(_db_path()), "status": "ok"}


def query(cypher: str) -> list[dict]:
    db = kuzu.Database(str(_db_path()))
    conn = kuzu.Connection(db)
    result = conn.execute(cypher)
    cols = result.get_column_names()
    rows: list[dict] = []
    while result.has_next():
        row = result.get_next()
        rows.append({cols[i]: row[i] for i in range(len(cols))})
    return rows

