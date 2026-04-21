"""F3 Kuzu POC smoke tests.

The whole module is skipped when ``kuzu`` cannot be imported so CI on
machines without Kuzu keeps green. On machines with Kuzu we build a
tiny synthetic graph in a tmp dir and assert the two POC queries
behave correctly and finish well under 1s.
"""

from __future__ import annotations

import pytest

kuzu = pytest.importorskip("kuzu")

from brain_agents import graph_query
from brain_agents.graph_build import DB_FILENAME


def _seed_tiny_graph(kuzu_dir):
    """Build a tiny synthetic graph at <kuzu_dir>/brain.kuzu so the
    query module (which assumes DB_FILENAME inside the dir) can read
    it directly.
    """
    kuzu_dir.mkdir(parents=True, exist_ok=True)
    db_file = kuzu_dir / DB_FILENAME
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

    # persons A, B, C, D
    for pid, name in [("A", "Alice"), ("B", "Bob"), ("C", "Cara"), ("D", "Dan")]:
        conn.execute(
            "CREATE (:Person {person_id: $p, display_name: $n, last_seen_utc: NULL})",
            {"p": pid, "n": name},
        )

    # A-B, B-C, C-D  → A's FoF should contain C (via B); not D (3 hops)
    for a, b in [("A", "B"), ("B", "C"), ("C", "D")]:
        conn.execute(
            "MATCH (x:Person {person_id: $a}), (y:Person {person_id: $b}) "
            "CREATE (x)-[:Interacted {reason: 'test', score: 1.0}]->(y)",
            {"a": a, "b": b},
        )

    # shared identifier: A and D both own phone 8613800138000
    conn.execute(
        "CREATE (:Identifier {value_normalized: '8613800138000', kind: 'phone'})"
    )
    for p in ("A", "D"):
        conn.execute(
            "MATCH (x:Person {person_id: $p}), (i:Identifier {value_normalized: '8613800138000'}) "
            "CREATE (x)-[:HasIdentifier]->(i)",
            {"p": p},
        )
    return db


def test_fof_returns_two_hop_neighbors(tmp_path):
    _seed_tiny_graph(tmp_path)
    out = graph_query.fof("A", limit=10, kuzu_dir=tmp_path)
    assert out["anchor"] == "A"
    assert out["hops"] == 2
    ids = {r["person_id"] for r in out["results"]}
    assert ids == {"C"}, f"expected FoF = {{C}} got {ids}"
    assert out["elapsed_ms"] < 1000


def test_shared_identifier_cross_person(tmp_path):
    _seed_tiny_graph(tmp_path)
    out = graph_query.shared_identifier("A", limit=10, kuzu_dir=tmp_path)
    ids = {r["person_id"] for r in out["results"]}
    assert ids == {"D"}
    assert all(r["kind"] == "phone" for r in out["results"])
    assert out["elapsed_ms"] < 1000


def test_stats(tmp_path):
    _seed_tiny_graph(tmp_path)
    out = graph_query.stats(kuzu_dir=tmp_path)
    c = out["counts"]
    assert c["Person"] == 4
    assert c["Identifier"] == 1
    assert c["Interacted"] == 3
    assert c["HasIdentifier"] == 2
    assert out["elapsed_ms"] < 1000


def test_fof_excludes_direct_neighbor(tmp_path):
    _seed_tiny_graph(tmp_path)
    # A-B direct; A-C via B (FoF). B should NOT appear in A's FoF.
    out = graph_query.fof("A", limit=10, kuzu_dir=tmp_path)
    ids = {r["person_id"] for r in out["results"]}
    assert "B" not in ids


def test_missing_dir_raises(tmp_path):
    with pytest.raises(RuntimeError):
        graph_query.fof("A", kuzu_dir=tmp_path / "does-not-exist")
