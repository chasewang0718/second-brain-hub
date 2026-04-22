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


_GRAPH_HINTS_MAX_AGE_S = 3600  # 1 hour; keeps hints ≤ one E1 cycle behind


def _freshen_graph_if_needed() -> dict[str, Any] | None:
    """Call ``rebuild_if_stale`` so hints are never more than
    :data:`_GRAPH_HINTS_MAX_AGE_S` stale versus DuckDB. Returns the
    rebuild descriptor (for diagnostics), or ``None`` when Kuzu isn't
    available / building errored — in that case hint collection is
    already graceful so we just fall through.
    """
    try:
        from brain_agents.graph_build import rebuild_if_stale
    except Exception:  # pragma: no cover - import guard
        return None
    try:
        return rebuild_if_stale(max_age_seconds=_GRAPH_HINTS_MAX_AGE_S)
    except Exception:  # pragma: no cover - defensive
        return None


def _collect_graph_hints(person_id: str, *, limit: int = 5, auto_freshen: bool = True) -> dict[str, Any]:
    """Query the Kuzu read-only view for cross-links (F3 POC integration).

    When ``auto_freshen=True`` (default), first runs
    :func:`rebuild_if_stale` with a 1h max-age so hints stay fresh
    without waiting for the weekly E1 task. Cost is a few ms of
    mtime stats when the view is fresh.

    Graceful degradation: if Kuzu is not installed or the graph has not
    been built yet, return ``{"status": "skipped", "reason": ...}`` so
    the calling MD renderer can hide the section cleanly.
    """
    freshen: dict[str, Any] | None = None
    if auto_freshen:
        freshen = _freshen_graph_if_needed()

    try:
        from brain_agents.graph_query import shared_identifier
    except Exception as exc:  # pragma: no cover - import guard
        return {"status": "skipped", "reason": f"import:{exc.__class__.__name__}"}
    try:
        payload = shared_identifier(person_id, limit=limit)
    except RuntimeError as exc:
        return {"status": "skipped", "reason": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "skipped", "reason": f"runtime:{exc.__class__.__name__}"}

    out: dict[str, Any] = {
        "status": "ok",
        "shared_identifier": payload.get("results") or [],
        "elapsed_ms": payload.get("elapsed_ms"),
    }
    if freshen is not None:
        out["freshen"] = {
            "status": freshen.get("status"),
            "rebuilt": bool(freshen.get("rebuilt")),
            "reason": freshen.get("reason"),
        }
    return out


def context_for_meeting(
    name_or_alias: str,
    limit: int = 5,
    *,
    since_days: int | None = None,
    include_graph_hints: bool = True,
    auto_freshen_graph: bool = True,
) -> dict[str, Any]:
    candidates = who(name_or_alias)
    if not candidates:
        return {"contact": None, "recent_interactions": [], "graph_hints": None}
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
    graph_hints = (
        _collect_graph_hints(cid, limit=5, auto_freshen=auto_freshen_graph)
        if include_graph_hints
        else None
    )
    insights_rows = query(
        """
        SELECT insight_type, body, detail_json, created_at
        FROM person_insights
        WHERE person_id = ?
        ORDER BY created_at DESC
        LIMIT 20
        """,
        [cid],
    )
    latest_by_type: dict[str, dict[str, Any]] = {}
    for row in insights_rows:
        it = str(row.get("insight_type") or "").strip().lower()
        if it and it not in latest_by_type:
            latest_by_type[it] = row
    topics: list[str] = []
    commitments: list[str] = []
    warmth: int | None = None
    trow = latest_by_type.get("topics")
    if trow:
        try:
            d = json.loads(str(trow.get("detail_json") or "{}"))
            if isinstance(d, dict):
                topics = [str(x).strip() for x in (d.get("topics") or []) if str(x).strip()]
        except Exception:
            pass
        if not topics:
            body = str(trow.get("body") or "").strip()
            topics = [x.strip() for x in body.split(",") if x.strip()]
    crow = latest_by_type.get("commitments")
    if crow:
        try:
            d = json.loads(str(crow.get("detail_json") or "{}"))
            if isinstance(d, dict):
                commitments = [str(x).strip() for x in (d.get("commitments") or []) if str(x).strip()]
        except Exception:
            pass
        if not commitments:
            body = str(crow.get("body") or "").strip()
            commitments = [x.strip() for x in body.splitlines() if x.strip()]
    wrow = latest_by_type.get("warmth")
    if wrow:
        try:
            d = json.loads(str(wrow.get("detail_json") or "{}"))
            if isinstance(d, dict):
                warmth = int(d.get("warmth") or 0) or None
        except Exception:
            pass
        if warmth is None:
            try:
                warmth = int(str(wrow.get("body") or "").strip())
            except Exception:
                warmth = None
    insights = {
        "topics": topics[:10],
        "commitments": commitments[:10],
        "warmth": warmth,
        "available": bool(topics or commitments or warmth is not None),
    }
    return {
        "contact": contact,
        "recent_interactions": interactions,
        "graph_hints": graph_hints,
        "insights": insights,
    }


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

    ins = payload.get("insights") or {}
    topics = [str(x).strip() for x in (ins.get("topics") or []) if str(x).strip()]
    commitments = [str(x).strip() for x in (ins.get("commitments") or []) if str(x).strip()]
    warmth = ins.get("warmth")
    if topics or commitments or warmth is not None:
        lines.append("")
        lines.append("#### 近期洞察")
        lines.append("")
        if warmth is not None:
            lines.append(f"- **关系温度(1-5)**: {warmth}")
        if topics:
            lines.append(f"- **最近话题**: {', '.join(topics)}")
        if commitments:
            lines.append("- **最近承诺**:")
            for item in commitments:
                lines.append(f"  - {item}")

    hints = payload.get("graph_hints") or {}
    shared = hints.get("shared_identifier") or [] if hints.get("status") == "ok" else []
    if shared:
        lines.append("")
        lines.append("#### 潜在同一人线索 (shared identifier)")
        lines.append("")
        lines.append("| person_id | display_name | kind | value |")
        lines.append("| --- | --- | --- | --- |")
        for r in shared:
            pid2 = str(r.get("person_id") or "")
            nm = str(r.get("display_name") or "").replace("|", "\\|")
            kind = str(r.get("kind") or "")
            val = str(r.get("value_normalized") or "").replace("|", "\\|")
            lines.append(f"| `{pid2}` | {nm} | {kind} | `{val}` |")
    return "\n".join(lines)
