"""LLM-assisted commitment extraction (Phase A6 Sprint 2).

Scans recent ``interactions`` for promises / follow-ups and proposes
candidate ``open_threads`` rows. Default mode is **dry-run**: caller
previews the candidates and decides whether to ``--apply`` them.

Design notes
------------
- Fast model by default (``brain_core.ollama_models.brain_fast_model``).
  Override via ``BRAIN_COMMITMENT_MODEL`` env var.
- Grouped by ``person_id`` — the LLM sees one person's summaries at a
  time, small enough to fit in the fast model's context comfortably.
- Output JSON schema is fixed and validated; malformed responses
  degrade to an empty list for that person (we never crash the scan).
- Idempotency: on ``--apply`` we call :func:`open_threads.add_thread`
  with ``source_kind='llm_extracted'`` — that module auto-hashes body
  text per-person and dedupes, so re-running the scan is safe.
- Robustness: ``_call_llm`` is a thin wrapper so tests can monkeypatch
  it without standing up a real Ollama.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from brain_memory.structured import query


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _model() -> str:
    override = os.getenv("BRAIN_COMMITMENT_MODEL", "").strip()
    if override:
        return override
    from brain_core.ollama_models import brain_fast_model

    return brain_fast_model()


def _ollama_client():
    from ollama import Client  # lazy so tests can avoid the dep

    host = os.getenv("OLLAMA_HOST", "").strip()
    return Client(host=host) if host else Client()


def _call_llm(prompt: str, model: str) -> str:
    """Single-turn prompt → raw string. Isolated for test mocking."""
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


_PROMPT = """\
你是一个冷静、保守的 CRM 承诺抽取器。从下面与某人的最近对话摘要中，抽取**确定的**、\
**未完成的**承诺或跟进事项（例如"下周寄书给他""周三前给他反馈""提醒她看文件"）。

严格要求：
1. 只抽取真实的承诺 / 待办，不要抽取闲聊、已完成的事、或模糊的意向。
2. 返回 **JSON 数组**，无其它文字、无 markdown 代码块。
3. 数组每个元素的 schema：
   {{
     "body": "一句话描述承诺，控制在 60 字以内",
     "due_utc": "ISO 日期或日期时间（YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS），找不到明确时间则填 null",
     "promised_by": "self 或 other（self 表示我欠对方，other 表示对方欠我）",
     "confidence": 0.0 到 1.0 的浮点数
   }}
4. 如果没有可抽取的承诺，返回 `[]`。

参考今天日期：{today}

对话摘要（按时间倒序，最近在最前）：
{summaries}
"""


def _build_prompt(summaries: list[str], today: datetime) -> str:
    body = "\n".join(f"- {s}" for s in summaries[:40]) or "(empty)"
    return _PROMPT.format(today=today.strftime("%Y-%m-%d"), summaries=body)


def _parse_candidates(raw: str) -> list[dict[str, Any]]:
    """Parse LLM output → list of candidate dicts. Never raises."""
    s = _strip_fence(raw)
    if not s:
        return []
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        # Try to recover by locating the first '[' ... ']' block
        m = re.search(r"\[.*\]", s, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        body = str(item.get("body") or "").strip()
        if not body:
            continue
        due = item.get("due_utc")
        due_s = None
        if isinstance(due, str) and due.strip() and due.strip().lower() not in {"null", "none"}:
            due_s = due.strip()
        pby = str(item.get("promised_by") or "").strip().lower() or None
        if pby not in {"self", "other", None}:
            pby = None
        try:
            conf = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        out.append(
            {
                "body": body[:240],
                "due_utc": due_s,
                "promised_by": pby,
                "confidence": conf,
            }
        )
    return out


def _fetch_grouped_interactions(
    *,
    since_days: int,
    person_id: str | None,
    per_person_limit: int,
) -> dict[str, list[dict[str, Any]]]:
    since = _utc_now() - timedelta(days=max(1, int(since_days)))
    params: list[Any] = [since]
    where = ["ts_utc >= ?"]
    if person_id:
        where.append("person_id = ?")
        params.append(person_id)
    rows = query(
        f"""
        SELECT id, person_id, ts_utc, channel, summary
        FROM interactions
        WHERE {' AND '.join(where)}
          AND person_id IS NOT NULL
          AND trim(coalesce(summary, '')) <> ''
        ORDER BY person_id, ts_utc DESC
        """,
        params,
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        pid = str(r["person_id"]).strip()
        bucket = grouped.setdefault(pid, [])
        if len(bucket) < per_person_limit:
            bucket.append(r)
    return grouped


def scan_commitments(
    *,
    since_days: int = 14,
    person_id: str | None = None,
    per_person_limit: int = 30,
    max_persons: int = 50,
    min_confidence: float = 0.6,
    apply: bool = False,
    llm_fn: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Scan recent interactions → candidate commitments.

    - ``apply=False`` (default) → return candidates only (dry-run).
    - ``apply=True``            → also call :func:`open_threads.add_thread`
      for every candidate with ``confidence >= min_confidence``. The
      ``add_thread`` idempotency (body_hash per person) makes this safe
      to rerun.

    ``llm_fn(prompt, model) -> str`` is an injection point for tests; when
    ``None`` we use :func:`_call_llm` which hits local Ollama.
    """
    if apply and min_confidence < 0.0:
        raise ValueError("min_confidence must be >= 0")
    pid = (person_id or "").strip() or None
    model = _model()
    today = _utc_now()
    invoke = llm_fn or _call_llm

    grouped = _fetch_grouped_interactions(
        since_days=since_days,
        person_id=pid,
        per_person_limit=per_person_limit,
    )
    target_persons = list(grouped.items())[: max(1, int(max_persons))]

    all_candidates: list[dict[str, Any]] = []
    applied_ids: list[int] = []
    skipped_low_conf = 0
    dedup_hits = 0
    errors: list[dict[str, str]] = []

    for pid_k, rows in target_persons:
        summaries = [str(r.get("summary") or "").strip() for r in rows if r.get("summary")]
        if not summaries:
            continue
        prompt = _build_prompt(summaries, today)
        try:
            raw = invoke(prompt, model)
        except Exception as exc:  # pragma: no cover - external service
            errors.append({"person_id": pid_k, "error": str(exc)[:240]})
            continue
        candidates = _parse_candidates(raw)
        most_recent_id = int(rows[0]["id"]) if rows and rows[0].get("id") is not None else None
        for c in candidates:
            c["person_id"] = pid_k
            c["source_interaction_id"] = most_recent_id
        all_candidates.extend(candidates)

    if apply and all_candidates:
        from brain_agents.open_threads import add_thread

        for c in all_candidates:
            if float(c.get("confidence") or 0.0) < float(min_confidence):
                skipped_low_conf += 1
                continue
            try:
                res = add_thread(
                    person_id=c["person_id"],
                    body=c["body"],
                    due_utc=c.get("due_utc"),
                    promised_by=c.get("promised_by"),
                    source_kind="llm_extracted",
                    source_interaction_id=c.get("source_interaction_id"),
                )
            except Exception as exc:
                errors.append({"person_id": c["person_id"], "error": str(exc)[:240]})
                continue
            if res.get("status") == "ok" and res.get("id") is not None:
                applied_ids.append(int(res["id"]))
                c["applied_id"] = int(res["id"])
                c["applied_status"] = "ok"
            elif res.get("status") == "noop":
                dedup_hits += 1
                c["applied_status"] = "noop"
                c["applied_reason"] = res.get("reason")

    return {
        "status": "ok",
        "mode": "apply" if apply else "dry-run",
        "scanned_persons": len(target_persons),
        "since_days": int(since_days),
        "model": model,
        "candidates": all_candidates,
        "candidate_count": len(all_candidates),
        "applied_count": len(applied_ids),
        "deduped_count": dedup_hits,
        "skipped_low_confidence": skipped_low_conf,
        "min_confidence": float(min_confidence),
        "errors": errors,
    }
