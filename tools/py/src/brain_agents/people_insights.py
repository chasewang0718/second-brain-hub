"""Offline people-insights extraction from recent interactions."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from ollama import Client

from brain_memory.structured import execute, query


def _client() -> Client:
    host = os.getenv("OLLAMA_HOST", "").strip()
    return Client(host=host) if host else Client()


def _model() -> str:
    legacy = os.getenv("BRAIN_PEOPLE_INSIGHTS_MODEL", "").strip()
    if legacy:
        return legacy
    from brain_core.ollama_models import brain_heavy_model

    return brain_heavy_model()


def _heuristic_fallback(summaries: list[str]) -> dict[str, Any]:
    text = " ".join(summaries).lower()
    topic_tags: list[str] = []
    for needle, tag in [
        ("wechat", "wechat"),
        ("whatsapp", "whatsapp"),
        ("budget", "budget"),
        ("contract", "contract"),
        ("meeting", "meeting"),
        ("follow", "follow-up"),
        ("ios", "ios"),
    ]:
        if needle in text:
            topic_tags.append(tag)
    commitments: list[str] = []
    for s in summaries:
        if re.search(r"\b(will|promise|send|follow up|remind)\b", s, re.IGNORECASE):
            commitments.append(s[:120])
    warmth = 3
    if len(summaries) >= 20:
        warmth = 5
    elif len(summaries) >= 8:
        warmth = 4
    elif len(summaries) <= 2:
        warmth = 2
    return {
        "topics": topic_tags[:8],
        "commitments": commitments[:8],
        "warmth": warmth,
        "status": "heuristic",
    }


def _extract_with_ollama(summaries: list[str]) -> dict[str, Any]:
    sample = "\n".join(f"- {s}" for s in summaries[:50])
    prompt = (
        "You are extracting CRM meeting prep insights from chat summaries.\n"
        "Return ONE JSON object only with keys:\n"
        '- "topics": array of short topic tags\n'
        '- "commitments": array of concrete follow-up promises/tasks\n'
        '- "warmth": integer 1-5 (relationship interaction warmth)\n'
        "Do not add markdown.\n\n"
        "Summaries:\n"
        f"{sample}\n"
    )
    out = _client().generate(model=_model(), prompt=prompt)
    if hasattr(out, "response"):
        raw = str(getattr(out, "response") or "").strip()
    elif isinstance(out, dict):
        raw = str(out.get("response", "")).strip()
    else:
        raw = str(out).strip()
    raw = re.sub(r"^```[a-zA-Z0-9]*\n?", "", raw).strip()
    raw = re.sub(r"\n?```$", "", raw).strip()
    data = json.loads(raw)
    topics = [str(x).strip() for x in (data.get("topics") or []) if str(x).strip()]
    commitments = [str(x).strip() for x in (data.get("commitments") or []) if str(x).strip()]
    warmth = int(data.get("warmth") or 3)
    warmth = max(1, min(5, warmth))
    return {
        "topics": topics[:10],
        "commitments": commitments[:10],
        "warmth": warmth,
        "status": "ollama",
    }


def _resolve_person_ids(person_id: str | None, name: str | None) -> list[str]:
    if person_id and person_id.strip():
        return [person_id.strip()]
    if name and name.strip():
        needle = f"%{name.strip().lower()}%"
        rows = query(
            """
            SELECT person_id
            FROM persons
            WHERE lower(primary_name) LIKE ?
               OR lower(aliases_json) LIKE ?
            ORDER BY last_seen_utc DESC
            LIMIT 20
            """,
            [needle, needle],
        )
        return [str(r.get("person_id") or "").strip() for r in rows if str(r.get("person_id") or "").strip()]
    rows = query(
        """
        WITH latest AS (
            SELECT person_id, MAX(ts_utc) AS last_ts
            FROM interactions
            WHERE coalesce(person_id, '') <> ''
            GROUP BY person_id
        )
        SELECT person_id
        FROM latest
        ORDER BY last_ts DESC
        LIMIT 30
        """
    )
    return [str(r.get("person_id") or "").strip() for r in rows if str(r.get("person_id") or "").strip()]


def refresh_people_insights(
    *,
    person_id: str | None = None,
    name: str | None = None,
    limit: int = 50,
    since_days: int = 90,
) -> dict[str, Any]:
    people = _resolve_person_ids(person_id, name)
    if not people:
        return {"status": "ok", "updated": 0, "reason": "no_target_people"}
    lim = max(5, min(200, int(limit)))
    days = max(1, min(3650, int(since_days)))
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

    updated = 0
    skipped = 0
    used = {"ollama": 0, "heuristic": 0}
    details: list[dict[str, Any]] = []
    for pid in people:
        rows = query(
            """
            SELECT ts_utc, channel, summary
            FROM interactions
            WHERE person_id = ? AND ts_utc >= ?
            ORDER BY ts_utc DESC
            LIMIT ?
            """,
            [pid, cutoff, lim],
        )
        summaries = [str(r.get("summary") or "").strip() for r in rows if str(r.get("summary") or "").strip()]
        if not summaries:
            skipped += 1
            continue
        try:
            insight = _extract_with_ollama(summaries)
        except Exception:
            insight = _heuristic_fallback(summaries)
        used[str(insight.get("status") or "heuristic")] = used.get(str(insight.get("status") or "heuristic"), 0) + 1

        execute("DELETE FROM person_insights WHERE person_id = ?", [pid])
        execute(
            """
            INSERT INTO person_insights (person_id, insight_type, body, detail_json)
            VALUES
              (?, 'topics', ?, ?),
              (?, 'commitments', ?, ?),
              (?, 'warmth', ?, ?)
            """,
            [
                pid,
                ", ".join(insight.get("topics") or []),
                json.dumps({"topics": insight.get("topics") or []}, ensure_ascii=False),
                pid,
                "\n".join(insight.get("commitments") or []),
                json.dumps({"commitments": insight.get("commitments") or []}, ensure_ascii=False),
                pid,
                str(int(insight.get("warmth") or 3)),
                json.dumps({"warmth": int(insight.get("warmth") or 3)}, ensure_ascii=False),
            ],
        )
        updated += 1
        details.append({"person_id": pid, "rows_used": len(summaries), "mode": insight.get("status")})
    return {
        "status": "ok",
        "updated": updated,
        "skipped": skipped,
        "target_people": len(people),
        "limit": lim,
        "since_days": days,
        "mode_counts": used,
        "details": details[:20],
    }

