"""B-ING-1.9: contacts_ingest_ios must be idempotent across repeated applies.

Second apply on the same AddressBook.sqlitedb must:
- create zero new persons,
- add zero new person_identifiers rows,
- leave the persons table row count unchanged.

Relies on the B-ING-1.5 autouse fixture in conftest.py for DuckDB isolation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from brain_agents.contacts_ingest_ios import ingest_address_book_sqlite
from brain_memory.structured import query


def _build_addressbook(tmp_path: Path) -> Path:
    """Write a minimal ABPerson + ABMultiValue SQLite that the ingester accepts."""
    db_path = tmp_path / "AddressBook.sqlitedb"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE ABPerson (
                ROWID INTEGER PRIMARY KEY,
                First TEXT,
                Last TEXT,
                Organization TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE ABMultiValue (
                record_id INTEGER,
                property INTEGER,
                value TEXT
            )
            """
        )
        persons = [
            (1, "Idem", "Alpha", None),
            (2, "Idem", "Beta", None),
            (3, None, None, "Idempotent Co"),
        ]
        conn.executemany("INSERT INTO ABPerson VALUES (?, ?, ?, ?)", persons)
        mv = [
            (1, 3, "+31600000001"),  # phone
            (1, 4, "alpha@idem.example"),  # email
            (2, 3, "+31600000002"),
            (3, 4, "hq@idem.example"),
        ]
        conn.executemany("INSERT INTO ABMultiValue VALUES (?, ?, ?)", mv)
        conn.commit()
    finally:
        conn.close()
    return db_path


def _counts() -> dict[str, int]:
    return {
        "persons": int(query("SELECT count(1) AS n FROM persons")[0]["n"]),
        "identifiers": int(query("SELECT count(1) AS n FROM person_identifiers")[0]["n"]),
        "ios_row_identifiers": int(
            query(
                "SELECT count(1) AS n FROM person_identifiers WHERE lower(kind) = 'ios_contact_row'"
            )[0]["n"]
        ),
    }


def test_ios_addressbook_ingest_is_idempotent(tmp_path: Path) -> None:
    ab = _build_addressbook(tmp_path)

    before = _counts()
    first = ingest_address_book_sqlite(ab, emit_log=False)
    assert first["status"] == "ok"
    assert first["person_rows"] == 3
    assert first["persons_created"] == 3
    mid = _counts()
    assert mid["persons"] == before["persons"] + 3
    assert mid["ios_row_identifiers"] == before["ios_row_identifiers"] + 3

    # Second apply on the same source must be a no-op for persons.
    second = ingest_address_book_sqlite(ab, emit_log=False)
    assert second["status"] == "ok"
    assert second["person_rows"] == 3
    assert second["persons_created"] == 0, (
        f"expected zero new persons on re-ingest, got {second['persons_created']}"
    )
    after = _counts()
    assert after["persons"] == mid["persons"], (
        f"persons count drifted on re-ingest: {mid['persons']} -> {after['persons']}"
    )
    assert after["identifiers"] == mid["identifiers"], (
        f"identifiers count drifted on re-ingest: {mid['identifiers']} -> {after['identifiers']}"
    )


def test_ios_addressbook_ingest_dry_run_is_side_effect_free(tmp_path: Path) -> None:
    ab = _build_addressbook(tmp_path)

    before = _counts()
    dry = ingest_address_book_sqlite(ab, dry_run=True, emit_log=False)
    assert dry["status"] == "dry_run"
    assert "sample" in dry
    after = _counts()
    assert after == before, f"dry_run mutated DuckDB: {before} -> {after}"
