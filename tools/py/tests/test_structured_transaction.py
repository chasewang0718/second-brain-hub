"""B-ING-0 · structured.transaction context manager.

Covers: commit on success, rollback on exception, nested reject.
Uses a temp DuckDB via monkeypatching ``_telemetry_db_path``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain_memory import structured


@pytest.fixture
def isolated_duckdb(tmp_path: Path, monkeypatch):
    db = tmp_path / "tx.duckdb"
    monkeypatch.setattr(structured, "_db_path", lambda: db)
    # Ensure a fresh schema is built in this temp DB.
    structured.ensure_schema()
    # Seed a minimal table we can freely mutate.
    structured.execute("CREATE TABLE IF NOT EXISTS tx_test (k INTEGER PRIMARY KEY, v VARCHAR)")
    structured.execute("DELETE FROM tx_test")
    return db


def test_transaction_commits_on_success(isolated_duckdb):
    with structured.transaction():
        structured.execute("INSERT INTO tx_test VALUES (1, 'a')")
        structured.execute("INSERT INTO tx_test VALUES (2, 'b')")
    rows = structured.query("SELECT k FROM tx_test ORDER BY k")
    assert [r["k"] for r in rows] == [1, 2]


def test_transaction_rolls_back_on_exception(isolated_duckdb):
    with pytest.raises(RuntimeError):
        with structured.transaction():
            structured.execute("INSERT INTO tx_test VALUES (10, 'a')")
            structured.execute("INSERT INTO tx_test VALUES (11, 'b')")
            raise RuntimeError("boom")
    rows = structured.query("SELECT k FROM tx_test")
    assert rows == []  # both inserts rolled back


def test_transaction_nested_rejected(isolated_duckdb):
    with structured.transaction():
        with pytest.raises(RuntimeError, match="nested"):
            with structured.transaction():
                pass


def test_transaction_restores_after_error(isolated_duckdb):
    """After a rolled-back txn, subsequent plain execute() must still work."""
    with pytest.raises(RuntimeError):
        with structured.transaction():
            structured.execute("INSERT INTO tx_test VALUES (1, 'a')")
            raise RuntimeError("boom")
    # Now, no transaction — plain execute must still work.
    structured.execute("INSERT INTO tx_test VALUES (99, 'z')")
    rows = structured.query("SELECT k FROM tx_test")
    assert [r["k"] for r in rows] == [99]
