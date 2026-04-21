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
    execute("DELETE FROM persons WHERE person_id IN ('p_alice','p_bob')")
    execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
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
    execute("DELETE FROM interactions WHERE person_id IN ('p_alice','p_bob')")
    execute(
        """
        INSERT INTO interactions (id, person_id, ts_utc, channel, summary, source_path, detail_json)
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
    return {"status": "ok", "seeded_persons": 2, "seeded_interactions": 3}


def who(name_or_alias: str) -> list[dict[str, Any]]:
    needle = f"%{name_or_alias.lower()}%"
    return query(
        """
        SELECT person_id AS id, primary_name AS name, aliases_json, tags_json, last_seen_utc
        FROM persons
        WHERE lower(primary_name) LIKE ?
           OR lower(aliases_json) LIKE ?
        ORDER BY last_seen_utc DESC
        LIMIT 10
        """,
        [needle, needle],
    )


def overdue(days: int = 30) -> list[dict[str, Any]]:
    return query(
        """
        SELECT person_id AS id, primary_name AS name, last_seen_utc,
               date_diff('day', last_seen_utc::DATE, current_date) AS days_since_contact
        FROM persons
        WHERE date_diff('day', last_seen_utc::DATE, current_date) >= ?
        ORDER BY days_since_contact DESC
        LIMIT 50
        """,
        [max(1, days)],
    )


def context_for_meeting(name_or_alias: str, limit: int = 5) -> dict[str, Any]:
    candidates = who(name_or_alias)
    if not candidates:
        return {"contact": None, "recent_interactions": []}
    contact = candidates[0]
    cid = contact["id"]
    interactions = query(
        """
        SELECT ts_utc, channel, summary, source_path
        FROM interactions
        WHERE person_id = ?
        ORDER BY ts_utc DESC
        LIMIT ?
        """,
        [cid, max(1, min(limit, 20))],
    )
    return {"contact": contact, "recent_interactions": interactions}
