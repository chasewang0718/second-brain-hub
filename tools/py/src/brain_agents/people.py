"""A5 MVP people engine (read-only style outputs)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from typing import Any

from brain_memory.structured import execute, query


def seed_demo_people_data() -> dict[str, Any]:
    now = datetime.now(UTC).replace(tzinfo=None)
    old = now - timedelta(days=40)
    recent = now - timedelta(days=3)
    execute(
        """
        INSERT OR REPLACE INTO contacts (id, name, aliases_json, tags_json, last_seen_utc)
        VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)
        """,
        [
            "p_alice",
            "Alice Zhang",
            json.dumps(["alice", "alice z"]),
            json.dumps(["friend", "design"]),
            old,
            "p_bob",
            "Bob van Dijk",
            json.dumps(["bob"]),
            json.dumps(["partner", "nl"]),
            recent,
        ],
    )
    execute("DELETE FROM interactions WHERE contact_id IN ('p_alice','p_bob')")
    execute(
        """
        INSERT INTO interactions (id, contact_id, ts_utc, channel, summary, source_path, detail_json)
        VALUES
          (nextval('interactions_id_seq'), ?, ?, ?, ?, ?, ?),
          (nextval('interactions_id_seq'), ?, ?, ?, ?, ?, ?),
          (nextval('interactions_id_seq'), ?, ?, ?, ?, ?, ?)
        """,
        [
            "p_alice",
            old,
            "wechat",
            "Discussed landing page collaboration",
            "demo://seed",
            "{}",
            "p_bob",
            recent,
            "meeting",
            "Talked about Dutch supplier intro",
            "demo://seed",
            "{}",
            "p_alice",
            old + timedelta(days=1),
            "email",
            "Shared proposal draft",
            "demo://seed",
            "{}",
        ],
    )
    return {"status": "ok", "seeded_contacts": 2, "seeded_interactions": 3}


def who(name_or_alias: str) -> list[dict[str, Any]]:
    needle = name_or_alias.lower().replace("'", "''")
    return query(
        f"""
        SELECT id, name, aliases_json, tags_json, last_seen_utc
        FROM contacts
        WHERE lower(name) LIKE '%{needle}%'
           OR lower(aliases_json) LIKE '%{needle}%'
        ORDER BY last_seen_utc DESC
        LIMIT 10
        """
    )


def overdue(days: int = 30) -> list[dict[str, Any]]:
    return query(
        f"""
        SELECT id, name, last_seen_utc,
               date_diff('day', last_seen_utc::DATE, current_date) AS days_since_contact
        FROM contacts
        WHERE date_diff('day', last_seen_utc::DATE, current_date) >= {max(1, days)}
        ORDER BY days_since_contact DESC
        LIMIT 50
        """
    )


def context_for_meeting(name_or_alias: str, limit: int = 5) -> dict[str, Any]:
    candidates = who(name_or_alias)
    if not candidates:
        return {"contact": None, "recent_interactions": []}
    contact = candidates[0]
    cid = str(contact["id"]).replace("'", "''")
    interactions = query(
        f"""
        SELECT ts_utc, channel, summary, source_path
        FROM interactions
        WHERE contact_id = '{cid}'
        ORDER BY ts_utc DESC
        LIMIT {max(1, min(limit, 20))}
        """
    )
    return {"contact": contact, "recent_interactions": interactions}

