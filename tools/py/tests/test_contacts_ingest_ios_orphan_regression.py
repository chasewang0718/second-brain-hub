"""B-ING-1.12: contacts_ingest_ios must not leak orphan person_identifiers.

Scenario:
  Two AddressBook rows share a phone number but carry different emails.
  Row-2's phone registration triggers an auto-T2 strong-identifier merge, so
  Row-2's local ``pid`` is absorbed into Row-1's survivor. Before the fix,
  Row-2's *subsequent* email registration still used the now-absorbed
  ``pid``, silently inserting an orphan ``person_identifiers`` row whose
  ``person_id`` no longer matches any ``persons`` row.

The fix requires callers of ``register_identifier`` to follow the returned
``person_id`` (the merge survivor) for subsequent inserts.

This test reproduces the exact production orphan pattern (phone-collision
before email-registration) and asserts:
  - zero orphaned ``person_identifiers`` rows,
  - both emails resolve to the same surviving person,
  - that surviving person still exists in ``persons``.

Relies on the B-ING-1.5 autouse fixture in conftest.py for DuckDB isolation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from brain_agents.contacts_ingest_ios import ingest_address_book_sqlite
from brain_agents.identity_resolver import resolve_identifier
from brain_memory.structured import query


def _build_collision_addressbook(tmp_path: Path) -> Path:
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
        conn.executemany(
            "INSERT INTO ABPerson VALUES (?, ?, ?, ?)",
            [
                (100, "Orphan", "Alpha", None),
                (101, "Orphan", "Beta", None),
            ],
        )
        # Both rows share +31 6 0000 9999 (strong identifier → triggers auto-T2
        # merge when the second one is registered). Each row has a *distinct*
        # email registered AFTER the phone → bug path.
        conn.executemany(
            "INSERT INTO ABMultiValue VALUES (?, ?, ?)",
            [
                (100, 3, "+31600009999"),
                (100, 4, "alpha-orphan@example.com"),
                (101, 3, "+31600009999"),
                (101, 4, "beta-orphan@example.com"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _orphan_identifier_count() -> int:
    rows = query(
        """
        SELECT count(1) AS n
        FROM person_identifiers pi
        LEFT JOIN persons p USING (person_id)
        WHERE p.person_id IS NULL
        """
    )
    return int(rows[0]["n"])


def test_phone_collision_does_not_leak_orphan_email(tmp_path: Path) -> None:
    ab = _build_collision_addressbook(tmp_path)

    assert _orphan_identifier_count() == 0, "fixture state is not clean"

    result = ingest_address_book_sqlite(ab, emit_log=False)
    assert result["status"] == "ok"
    assert result["person_rows"] == 2

    # After a shared-phone collision, exactly one of the two freshly created
    # persons must have been absorbed by auto-T2 merge. The survivor owns all
    # four identifiers (ios_ab:100, ios_ab:101, phone, both emails) — and
    # critically, **no orphan rows**.
    orphans = _orphan_identifier_count()
    assert orphans == 0, f"B-ING-1.12 regressed: {orphans} orphan person_identifiers"

    pid_alpha = resolve_identifier("email", "alpha-orphan@example.com")
    pid_beta = resolve_identifier("email", "beta-orphan@example.com")
    assert pid_alpha is not None, "alpha email must be resolvable"
    assert pid_beta is not None, "beta email must be resolvable (previously orphaned)"
    assert pid_alpha == pid_beta, (
        f"both emails must land on the merge survivor: alpha={pid_alpha} beta={pid_beta}"
    )

    # Survivor still exists in persons.
    survived = query("SELECT person_id FROM persons WHERE person_id = ?", [pid_beta])
    assert survived, "merge survivor must still be present in persons"


def test_phone_collision_survives_reingest(tmp_path: Path) -> None:
    """Second ingest of the same book must not re-create orphans or persons."""
    ab = _build_collision_addressbook(tmp_path)

    ingest_address_book_sqlite(ab, emit_log=False)
    mid_persons = int(query("SELECT count(1) AS n FROM persons")[0]["n"])
    mid_orphans = _orphan_identifier_count()
    assert mid_orphans == 0

    second = ingest_address_book_sqlite(ab, emit_log=False)
    assert second["status"] == "ok"
    assert second["persons_created"] == 0

    after_persons = int(query("SELECT count(1) AS n FROM persons")[0]["n"])
    assert after_persons == mid_persons
    assert _orphan_identifier_count() == 0
