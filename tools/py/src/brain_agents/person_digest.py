"""Rolling topics + weekly digest (Phase A6 Sprint 3).

Writes two insight types to ``person_insights``:

- ``topics_30d``  — top-K topic tags + short narrative from last 30 days
- ``weekly_digest`` — narrative summary of last 7 days (or whatever window)

Versioning: each rebuild inserts a **new** row and points the previous row's
``superseded_by`` at the new row. "Current" = ``superseded_by IS NULL``.
That preserves the audit trail without ever mutating historical body text
(matches the :mod:`brain_agents.person_facts` pattern).

Robustness:
- LLM failures degrade to a heuristic summary (never crash the batch).
- ``_call_llm`` is isolated for test mocking.
- Empty interactions in the window → row is **not** written (skip cleanly).
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from brain_memory.structured import fetch_one, query, transaction

INSIGHT_TOPICS = "topics_30d"
INSIGHT_WEEKLY = "weekly_digest"
_ALLOWED_TYPES = {INSIGHT_TOPICS, INSIGHT_WEEKLY}


def _utc_now() -> datetime:
    # Preserve microseconds so ``ts_utc <= window_end`` doesn't accidentally
    # exclude interactions that landed in the same second as the rebuild.
    return datetime.now(UTC).replace(tzinfo=None)


def _model() -> str:
    override = os.getenv("BRAIN_PERSON_DIGEST_MODEL", "").strip()
    if override:
        return override
    from brain_core.ollama_models import brain_fast_model

    return brain_fast_model()


def _ollama_client():
    from ollama import Client

    host = os.getenv("OLLAMA_HOST", "").strip()
    return Client(host=host) if host else Client()


def _call_llm(prompt: str, model: str) -> str:
    out = _ollama_client().generate(model=model, prompt=prompt)
    if hasattr(out, "response"):
        return str(getattr(out, "response") or "").strip()
    if isinstance(out, dict):
        return str(out.get("response", "")).strip()
    return str(out).strip()


_FENCE_OPEN = re.compile(r"^```[a-zA-Z0-9]*\n?")
_FENCE_CLOSE = re.compile(r"\n?```$")


def _strip_fence(text: str) -> str:
    s = (text or "").strip()
    s = _FENCE_OPEN.sub("", s).strip()
    s = _FENCE_CLOSE.sub("", s).strip()
    return s


_TOPICS_PROMPT = """\
你是一个会做中文人物档案归纳的助手。下面是我和某人最近的对话摘要。请严格按 JSON 对象返回：

{{
  "topics": ["主题词 1", "主题词 2", ...]  // 3-8 个短词组，不要整句
  "narrative": "一段 60-160 字的中文小结，覆盖对话里反复出现的主题、情绪基调、未决事项"
}}

严格要求：
1. 只返回 JSON，不要 markdown 代码块、不要前言。
2. 语义重复/噪音内容（msg_type=50、空字符串等）要忽略。
3. 如果内容不足以归纳，返回 {{"topics":[],"narrative":""}}。

对话摘要（按时间倒序）：
{sample}
"""


_WEEKLY_PROMPT = """\
你是一个会做中文人物周报的助手。下面是我和某人最近 {days} 天的对话摘要。请用一段自然的中文（100-200 字）总结：

- 我们主要聊了什么
- 有没有我该跟进的未完成事项
- 对方最近的状态 / 情绪基调

严格要求：
1. 只返回这一段中文文本，不要标题、不要列表、不要 JSON。
2. 信息不足时用 "本周互动较少，暂无值得提炼的内容。" 兜底。

对话摘要（按时间倒序）：
{sample}
"""


def _parse_topics_payload(raw: str) -> dict[str, Any]:
    s = _strip_fence(raw)
    if not s:
        return {"topics": [], "narrative": ""}
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if not m:
            return {"topics": [], "narrative": ""}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {"topics": [], "narrative": ""}
    if not isinstance(data, dict):
        return {"topics": [], "narrative": ""}
    topics_raw = data.get("topics") or []
    topics = [str(x).strip() for x in topics_raw if isinstance(x, (str, int, float)) and str(x).strip()]
    narrative = str(data.get("narrative") or "").strip()
    return {"topics": topics[:10], "narrative": narrative[:1000]}


def _heuristic_topics(summaries: list[str]) -> dict[str, Any]:
    """Fallback: pick recurring short tokens, build a one-line narrative."""
    if not summaries:
        return {"topics": [], "narrative": ""}
    counts: dict[str, int] = {}
    for s in summaries:
        for word in re.findall(r"[\u4e00-\u9fa5]{2,6}|[A-Za-z][A-Za-z0-9_\-]{2,}", s):
            w = word.lower()
            if w in {"msg_type", "wechat", "whatsapp"}:
                continue
            counts[w] = counts.get(w, 0) + 1
    # Prefer recurring words, but fall back to any top words so we always
    # surface something when interactions exist (tests seed tiny samples).
    ranked = sorted(counts.items(), key=lambda x: -x[1])
    top = [w for w, c in ranked if c >= 2][:6]
    if not top:
        top = [w for w, _ in ranked[:6]]
    narrative = f"最近 {len(summaries)} 条互动的高频词汇：{', '.join(top) if top else '无'}。"
    return {"topics": top, "narrative": narrative}


def _heuristic_weekly(summaries: list[str], days: int) -> str:
    if not summaries:
        return ""
    return f"最近 {days} 天共有 {len(summaries)} 条对话摘要。（LLM 不可用，暂用启发式占位；下次 rebuild 会尝试重新生成。）"


def _fetch_summaries(person_id: str, window_start: datetime, window_end: datetime, limit: int) -> list[dict[str, Any]]:
    return query(
        """
        SELECT id, ts_utc, channel, summary
        FROM interactions
        WHERE person_id = ?
          AND ts_utc >= ?
          AND ts_utc <= ?
          AND trim(coalesce(summary, '')) <> ''
        ORDER BY ts_utc DESC
        LIMIT ?
        """,
        [person_id, window_start, window_end, int(limit)],
    )


def _latest_current(person_id: str, insight_type: str) -> dict[str, Any] | None:
    """Return the current (superseded_by IS NULL) row for this person+type."""
    return fetch_one(
        """
        SELECT id, body, detail_json, created_at, window_start_utc, window_end_utc, source_kind
        FROM person_insights
        WHERE person_id = ?
          AND insight_type = ?
          AND superseded_by IS NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        [person_id, insight_type],
    )


def _insert_and_supersede(
    *,
    person_id: str,
    insight_type: str,
    body: str,
    detail_json: dict[str, Any],
    window_start: datetime,
    window_end: datetime,
    source_kind: str,
    prior_id: int | None,
) -> int:
    """Insert the new row then point prior's superseded_by at it. Atomic."""
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO person_insights
              (person_id, insight_type, body, detail_json,
               window_start_utc, window_end_utc, source_kind)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                person_id,
                insight_type,
                body,
                json.dumps(detail_json, ensure_ascii=False),
                window_start,
                window_end,
                source_kind,
            ],
        )
        row = conn.execute(
            """
            SELECT id FROM person_insights
            WHERE person_id = ? AND insight_type = ? AND superseded_by IS NULL
            ORDER BY id DESC LIMIT 1
            """,
            [person_id, insight_type],
        ).fetchone()
        new_id = int(row[0]) if row else 0
        if prior_id is not None:
            conn.execute(
                "UPDATE person_insights SET superseded_by = ? WHERE id = ?",
                [new_id, prior_id],
            )
    return new_id


def _rebuild_topics(
    person_id: str,
    *,
    since_days: int,
    interaction_limit: int,
    window_end: datetime,
    llm_fn: Callable[[str, str], str],
    model: str,
) -> dict[str, Any]:
    window_start = window_end - timedelta(days=max(1, int(since_days)))
    rows = _fetch_summaries(person_id, window_start, window_end, interaction_limit)
    summaries = [str(r.get("summary") or "").strip() for r in rows if r.get("summary")]
    if not summaries:
        return {"status": "skipped", "reason": "no_interactions_in_window", "insight_type": INSIGHT_TOPICS}

    sample = "\n".join(f"- {s}" for s in summaries[:40])
    prompt = _TOPICS_PROMPT.format(sample=sample)
    used_fallback = False
    try:
        raw = llm_fn(prompt, model)
        parsed = _parse_topics_payload(raw)
        if not parsed.get("narrative") and not parsed.get("topics"):
            used_fallback = True
            parsed = _heuristic_topics(summaries)
    except Exception:
        used_fallback = True
        parsed = _heuristic_topics(summaries)

    body = parsed.get("narrative", "")
    detail = {
        "topics": parsed.get("topics", []),
        "narrative": body,
        "sample_count": len(summaries),
        "mode": "heuristic" if used_fallback else "llm",
        "model": model if not used_fallback else None,
    }

    prior = _latest_current(person_id, INSIGHT_TOPICS)
    new_id = _insert_and_supersede(
        person_id=person_id,
        insight_type=INSIGHT_TOPICS,
        body=body,
        detail_json=detail,
        window_start=window_start,
        window_end=window_end,
        source_kind="llm" if not used_fallback else "heuristic",
        prior_id=int(prior["id"]) if prior else None,
    )
    return {
        "status": "ok",
        "insight_type": INSIGHT_TOPICS,
        "id": new_id,
        "prior_id": int(prior["id"]) if prior else None,
        "sample_count": len(summaries),
        "topics_count": len(parsed.get("topics", [])),
        "mode": "heuristic" if used_fallback else "llm",
    }


def _rebuild_weekly(
    person_id: str,
    *,
    since_days: int,
    interaction_limit: int,
    window_end: datetime,
    llm_fn: Callable[[str, str], str],
    model: str,
) -> dict[str, Any]:
    window_start = window_end - timedelta(days=max(1, int(since_days)))
    rows = _fetch_summaries(person_id, window_start, window_end, interaction_limit)
    summaries = [str(r.get("summary") or "").strip() for r in rows if r.get("summary")]
    if not summaries:
        return {"status": "skipped", "reason": "no_interactions_in_window", "insight_type": INSIGHT_WEEKLY}

    sample = "\n".join(f"- {s}" for s in summaries[:40])
    prompt = _WEEKLY_PROMPT.format(days=int(since_days), sample=sample)
    used_fallback = False
    narrative = ""
    try:
        raw = llm_fn(prompt, model)
        narrative = _strip_fence(raw).strip()
        # Guard against the LLM returning JSON despite the prompt
        if narrative.startswith("{") and narrative.endswith("}"):
            try:
                j = json.loads(narrative)
                if isinstance(j, dict):
                    narrative = str(
                        j.get("narrative") or j.get("summary") or j.get("text") or ""
                    ).strip()
            except json.JSONDecodeError:
                pass
        if not narrative:
            used_fallback = True
            narrative = _heuristic_weekly(summaries, since_days)
    except Exception:
        used_fallback = True
        narrative = _heuristic_weekly(summaries, since_days)

    narrative = narrative[:2000]
    detail = {
        "sample_count": len(summaries),
        "since_days": int(since_days),
        "mode": "heuristic" if used_fallback else "llm",
        "model": model if not used_fallback else None,
    }

    prior = _latest_current(person_id, INSIGHT_WEEKLY)
    new_id = _insert_and_supersede(
        person_id=person_id,
        insight_type=INSIGHT_WEEKLY,
        body=narrative,
        detail_json=detail,
        window_start=window_start,
        window_end=window_end,
        source_kind="llm" if not used_fallback else "heuristic",
        prior_id=int(prior["id"]) if prior else None,
    )
    return {
        "status": "ok",
        "insight_type": INSIGHT_WEEKLY,
        "id": new_id,
        "prior_id": int(prior["id"]) if prior else None,
        "sample_count": len(summaries),
        "mode": "heuristic" if used_fallback else "llm",
    }


def rebuild_one(
    person_id: str,
    *,
    insight_types: list[str] | None = None,
    topics_days: int = 30,
    weekly_days: int = 7,
    interaction_limit: int = 40,
    window_end: datetime | None = None,
    llm_fn: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Rebuild the specified insight types for one person. Idempotent.

    - ``insight_types=None`` → both topics_30d and weekly_digest.
    - ``window_end`` defaults to now (UTC).
    """
    pid = (person_id or "").strip()
    if not pid:
        raise ValueError("person_id is required")
    types = list(insight_types) if insight_types else [INSIGHT_TOPICS, INSIGHT_WEEKLY]
    for t in types:
        if t not in _ALLOWED_TYPES:
            raise ValueError(f"unknown insight_type: {t}")

    invoke = llm_fn or _call_llm
    model = _model()
    end = window_end or _utc_now()
    results: list[dict[str, Any]] = []

    if INSIGHT_TOPICS in types:
        results.append(
            _rebuild_topics(
                pid,
                since_days=topics_days,
                interaction_limit=interaction_limit,
                window_end=end,
                llm_fn=invoke,
                model=model,
            )
        )
    if INSIGHT_WEEKLY in types:
        results.append(
            _rebuild_weekly(
                pid,
                since_days=weekly_days,
                interaction_limit=interaction_limit,
                window_end=end,
                llm_fn=invoke,
                model=model,
            )
        )

    return {
        "status": "ok",
        "person_id": pid,
        "window_end": str(end),
        "results": results,
    }


def rebuild_all(
    *,
    insight_types: list[str] | None = None,
    topics_days: int = 30,
    weekly_days: int = 7,
    interaction_limit: int = 40,
    max_persons: int = 500,
    min_interactions_30d: int = 1,
    window_end: datetime | None = None,
    llm_fn: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Rebuild for every person who has ≥ ``min_interactions_30d`` summaries
    in the last 30 days (cheap filter — skips totally cold persons)."""
    end = window_end or _utc_now()
    cutoff = end - timedelta(days=30)
    rows = query(
        """
        SELECT person_id, COUNT(*) AS n
        FROM interactions
        WHERE ts_utc >= ?
          AND coalesce(person_id, '') <> ''
          AND trim(coalesce(summary, '')) <> ''
        GROUP BY person_id
        HAVING COUNT(*) >= ?
        ORDER BY n DESC
        LIMIT ?
        """,
        [cutoff, int(min_interactions_30d), int(max_persons)],
    )
    ok = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    persons: list[str] = []
    for r in rows:
        pid = str(r["person_id"]).strip()
        persons.append(pid)
        try:
            res = rebuild_one(
                pid,
                insight_types=insight_types,
                topics_days=topics_days,
                weekly_days=weekly_days,
                interaction_limit=interaction_limit,
                window_end=end,
                llm_fn=llm_fn,
            )
        except Exception as exc:
            errors.append({"person_id": pid, "error": str(exc)[:240]})
            continue
        ok += 1
        any_skipped = any(x.get("status") == "skipped" for x in res.get("results") or [])
        if any_skipped:
            skipped += 1

    return {
        "status": "ok",
        "scanned": len(rows),
        "rebuilt": ok,
        "partial_skips": skipped,
        "errors": errors,
        "window_end": str(end),
        "persons": persons[:50],
    }


def get_current_insights(person_id: str) -> dict[str, Any]:
    """Return the current topics_30d + weekly_digest rows for this person.

    Each value is either a dict (row) or ``None`` when absent. Handy for
    people_render and CLI ``show``.
    """
    pid = (person_id or "").strip()
    if not pid:
        return {"topics": None, "weekly": None}
    topics = _latest_current(pid, INSIGHT_TOPICS)
    weekly = _latest_current(pid, INSIGHT_WEEKLY)

    def _decorate(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        try:
            det = json.loads(row.get("detail_json") or "{}")
        except json.JSONDecodeError:
            det = {}
        return {
            "id": int(row.get("id") or 0),
            "body": str(row.get("body") or ""),
            "created_at": row.get("created_at"),
            "window_start_utc": row.get("window_start_utc"),
            "window_end_utc": row.get("window_end_utc"),
            "source_kind": str(row.get("source_kind") or ""),
            "detail": det,
        }

    return {"topics": _decorate(topics), "weekly": _decorate(weekly)}
