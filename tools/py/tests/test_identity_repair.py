"""Integration tests for identifiers repair (email/wxid lowercase)."""

from __future__ import annotations

import uuid

from brain_agents.identity_resolver import run_identifiers_repair
from brain_memory.structured import execute, fetch_one


def test_email_repair_fixes_mixed_case_normalized_value() -> None:
    pid = f"p_{uuid.uuid4().hex[:12]}"
    execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES (?, 'Repair Test Person', '[]', '[]', CURRENT_TIMESTAMP)
        """,
        [pid],
    )
    execute(
        """
        INSERT INTO person_identifiers (person_id, kind, value_normalized, value_original, confidence, source_kind)
        VALUES (?, 'email', 'OldMixed@Example.COM', 'OldMixed@Example.COM', 1.0, 'test')
        """,
        [pid],
    )

    rep = run_identifiers_repair(kinds={"email"}, dry_run=False)
    assert rep["status"] == "ok"
    assert rep["results"]["email"]["updated"] >= 1

    row = fetch_one(
        "SELECT value_normalized FROM person_identifiers WHERE person_id = ? AND lower(kind) = 'email'",
        [pid],
    )
    assert row and row["value_normalized"] == "oldmixed@example.com"

    execute("DELETE FROM person_identifiers WHERE person_id = ?", [pid])
    execute("DELETE FROM persons WHERE person_id = ?", [pid])


def test_wxid_repair_fixes_case() -> None:
    pid = f"p_{uuid.uuid4().hex[:12]}"
    execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES (?, 'Wx Repair', '[]', '[]', CURRENT_TIMESTAMP)
        """,
        [pid],
    )
    execute(
        """
        INSERT INTO person_identifiers (person_id, kind, value_normalized, value_original, confidence, source_kind)
        VALUES (?, 'wxid', 'WxId_ForceCase', 'WxId_ForceCase', 1.0, 'test')
        """,
        [pid],
    )

    rep = run_identifiers_repair(kinds={"wxid"}, dry_run=False)
    assert rep["status"] == "ok"
    assert rep["results"]["wxid"]["updated"] >= 1

    row = fetch_one(
        "SELECT value_normalized FROM person_identifiers WHERE person_id = ? AND lower(kind) = 'wxid'",
        [pid],
    )
    assert row and row["value_normalized"] == "wxid_forcecase"

    execute("DELETE FROM person_identifiers WHERE person_id = ?", [pid])
    execute("DELETE FROM persons WHERE person_id = ?", [pid])
