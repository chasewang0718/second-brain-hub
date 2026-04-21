"""F3 Kuzu POC: read-only graph queries.

Queries assume the graph was already built by ``graph_build.build_graph``.
All queries lazy-import ``kuzu`` so callers can catch ``RuntimeError``
and fall back gracefully.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from brain_agents.graph_build import DB_FILENAME, default_kuzu_dir


def _open(kuzu_dir: Path | None = None):
    try:
        import kuzu  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"kuzu_missing:{exc.__class__.__name__}") from exc
    path = kuzu_dir or default_kuzu_dir()
    if not path.exists():
        raise RuntimeError(f"kuzu_not_built:{path}")
    db_file = path / DB_FILENAME
    if not db_file.exists():
        raise RuntimeError(f"kuzu_not_built:{db_file}")
    db = kuzu.Database(str(db_file), read_only=True)
    conn = kuzu.Connection(db)
    return conn


def _result_rows(result) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    columns = result.get_column_names() if hasattr(result, "get_column_names") else []
    while result.has_next():
        row = result.get_next()
        if columns and len(columns) == len(row):
            out.append({c: row[i] for i, c in enumerate(columns)})
        else:
            out.append({"row": list(row)})
    return out


def fof(person_id: str, *, limit: int = 10, kuzu_dir: Path | None = None) -> dict[str, Any]:
    """Friends-of-friends: persons 2 hops away via Interacted edges,
    excluding the anchor and direct 1-hop neighbors.
    """
    conn = _open(kuzu_dir)
    t0 = time.perf_counter()
    q = (
        "MATCH (a:Person)-[:Interacted]-(b:Person)-[:Interacted]-(c:Person) "
        "WHERE a.person_id = $pid "
        "  AND c.person_id <> a.person_id "
        "  AND NOT EXISTS { MATCH (a)-[:Interacted]-(c) } "
        "RETURN DISTINCT c.person_id AS person_id, c.display_name AS display_name "
        "LIMIT $k"
    )
    res = conn.execute(q, {"pid": person_id, "k": int(limit)})
    rows = _result_rows(res)
    return {
        "anchor": person_id,
        "hops": 2,
        "count": len(rows),
        "results": rows,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def shared_identifier(person_id: str, *, limit: int = 20, kuzu_dir: Path | None = None) -> dict[str, Any]:
    """Persons sharing at least one identifier value with the anchor.
    Useful to surface likely duplicate identities.
    """
    conn = _open(kuzu_dir)
    t0 = time.perf_counter()
    q = (
        "MATCH (a:Person)-[:HasIdentifier]->(i:Identifier)<-[:HasIdentifier]-(b:Person) "
        "WHERE a.person_id = $pid AND b.person_id <> a.person_id "
        "RETURN b.person_id AS person_id, b.display_name AS display_name, "
        "       i.kind AS kind, i.value_normalized AS value_normalized "
        "LIMIT $k"
    )
    res = conn.execute(q, {"pid": person_id, "k": int(limit)})
    rows = _result_rows(res)
    return {
        "anchor": person_id,
        "count": len(rows),
        "results": rows,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def stats(kuzu_dir: Path | None = None) -> dict[str, Any]:
    """Node / edge counts for quick health check."""
    conn = _open(kuzu_dir)
    t0 = time.perf_counter()
    counts: dict[str, int] = {}
    for label in ("Person", "Identifier"):
        res = conn.execute(f"MATCH (n:{label}) RETURN count(n) AS c")
        counts[label] = int(_result_rows(res)[0]["c"]) if res else 0
    for rel in ("Interacted", "HasIdentifier"):
        res = conn.execute(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c")
        counts[rel] = int(_result_rows(res)[0]["c"]) if res else 0
    return {
        "counts": counts,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
