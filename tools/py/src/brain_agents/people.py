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


def overdue(days: int = 30, *, channel: str | None = None) -> list[dict[str, Any]]:
    d = max(1, days)
    if channel and channel.strip():
        ch = channel.strip().lower()
        return query(
            """
            WITH latest AS (
                SELECT person_id, MAX(ts_utc) AS last_ts
                FROM interactions
                WHERE lower(channel) = ?
                GROUP BY person_id
            )
            SELECT
                p.person_id AS id,
                p.primary_name AS name,
                p.last_seen_utc,
                l.last_ts AS last_interaction_utc,
                date_diff('day', l.last_ts::DATE, current_date) AS days_since_channel_contact
            FROM latest l
            JOIN persons p ON p.person_id = l.person_id
            WHERE date_diff('day', l.last_ts::DATE, current_date) >= ?
            ORDER BY days_since_channel_contact DESC
            LIMIT 50
            """,
            [ch, d],
        )
    return query(
        """
        SELECT person_id AS id, primary_name AS name, last_seen_utc,
               date_diff('day', last_seen_utc::DATE, current_date) AS days_since_contact
        FROM persons
        WHERE date_diff('day', last_seen_utc::DATE, current_date) >= ?
        ORDER BY days_since_contact DESC
        LIMIT 50
        """,
        [d],
    )


def context_for_meeting(
    name_or_alias: str,
    limit: int = 5,
    *,
    since_days: int | None = None,
) -> dict[str, Any]:
    candidates = who(name_or_alias)
    if not candidates:
        return {"contact": None, "recent_interactions": []}
    contact = candidates[0]
    cid = contact["id"]
    lim = max(1, min(limit, 20))
    params: list[Any] = [cid]
    since_sql = ""
    if since_days is not None:
        sd = max(1, int(since_days))
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=sd)
        since_sql = " AND ts_utc >= ?"
        params.append(cutoff)
    params.append(lim)
    interactions = query(
        f"""
        SELECT ts_utc, channel, summary, source_path
        FROM interactions
        WHERE person_id = ?
          {since_sql}
        ORDER BY ts_utc DESC
        LIMIT ?
        """,
        params,
    )
    return {"contact": contact, "recent_interactions": interactions}


def context_for_meeting_markdown(payload: dict[str, Any]) -> str:
    """Turn context_for_meeting dict into Markdown for paste into notes."""
    c = payload.get("contact")
    rows = payload.get("recent_interactions") or []
    lines: list[str] = []
    if not c:
        lines.append("(no matching contact)")
        return "\n".join(lines)
    pid = c.get("id") or ""
    name = c.get("name") or ""
    lines.append(f"### Meeting context — {name}")
    lines.append("")
    lines.append(f"- **person_id**: `{pid}`")
    ls = c.get("last_seen_utc")
    if ls is not None:
        lines.append(f"- **last_seen_utc**: {ls}")
    lines.append("")
    lines.append("#### Recent interactions")
    lines.append("")
    if not rows:
        lines.append("(none)")
        return "\n".join(lines)
    lines.append("| ts_utc | channel | summary |")
    lines.append("| --- | --- | --- |")
    for r in rows:
        ts = r.get("ts_utc") or ""
        ch = str(r.get("channel") or "")
        summary = str(r.get("summary") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {ts} | {ch} | {summary} |")
    return "\n".join(lines)
