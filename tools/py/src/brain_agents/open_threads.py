"""Open threads / commitments (Phase A6 Sprint 2).

Wraps the ``open_threads`` DuckDB table with a minimal state machine:

    open  ──close(done)──▶  done
    open  ──close(dropped)──▶  dropped
    done/dropped ──reopen──▶  open

A "thread" here is a loose promise or commitment between the user and
``person_id`` — e.g. "下周三寄书" or "帮他改简历". Each row has an
optional ``due_utc`` (UTC TIMESTAMP) and ``promised_by`` = 'self' | 'other'
(who made the promise, the user or the counterpart).

Idempotency: callers (especially the LLM scanner) can supply
``body_hash`` + ``source_interaction_id``; a repeat write with the same
pair is a no-op. Manual entries (no ``body_hash``) never dedupe.

All writes flow through :func:`brain_memory.structured.transaction`.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from brain_memory.structured import ensure_schema, fetch_one, query, transaction

_ALLOWED_STATUS = {"open", "done", "dropped"}
_ALLOWED_PROMISED_BY = {"self", "other", None, ""}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _coerce_dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    s = str(value).strip()
    if not s:
        return None
    # Detect date-only input ("2026-05-01") and snap to end-of-day UTC
    # so "due by 2026-05-01" doesn't silently become 00:00 of that day
    # (which would mark it overdue at 00:01). Python 3.11+ `fromisoformat`
    # happily accepts date-only strings, so we must branch first.
    has_time = "T" in s or " " in s
    try:
        parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"unparseable datetime: {s!r}") from exc
    parsed = parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    if not has_time and parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0:
        parsed = parsed.replace(hour=23, minute=59, second=59)
    return parsed


def _compute_body_hash(person_id: str, body: str) -> str:
    """Stable hash for idempotency. Scoped per-person so the same canned
    phrase (e.g. 'send book') across different people is NOT collapsed.
    """
    h = hashlib.sha256()
    h.update(pid := (person_id or "").strip().encode("utf-8"))
    h.update(b"\x1f")
    h.update((body or "").strip().encode("utf-8"))
    _ = pid
    return h.hexdigest()[:16]


def add_thread(
    person_id: str,
    body: str,
    *,
    due_utc: datetime | str | None = None,
    promised_by: str | None = None,
    source_interaction_id: int | None = None,
    source_kind: str = "manual",
    last_mentioned_utc: datetime | str | None = None,
    body_hash: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Insert an open thread. Returns status/id/etc.

    When ``body_hash`` is provided (or auto-computed from ``body`` when
    ``source_kind != 'manual'``), a prior open row with the same
    ``(person_id, body_hash)`` → ``status='noop'``. Manual entries without
    a hash are always inserted (users may legitimately record
    duplicate-looking promises).
    """
    pid = (person_id or "").strip()
    txt = (body or "").strip()
    if not pid:
        raise ValueError("person_id is required")
    if not txt:
        raise ValueError("body is required")
    pby = (promised_by or "").strip().lower() or None
    if pby not in _ALLOWED_PROMISED_BY:
        raise ValueError(f"promised_by must be one of self/other/null, got {promised_by!r}")
    due_dt = _coerce_dt(due_utc)
    last_dt = _coerce_dt(last_mentioned_utc) or _utc_now()
    sk = (source_kind or "manual").strip() or "manual"
    sid = int(source_interaction_id) if source_interaction_id else None

    # Auto-hash for LLM (or any non-manual) source so repeated scans dedupe.
    bh = (body_hash or "").strip() or None
    if bh is None and sk != "manual":
        bh = _compute_body_hash(pid, txt)

    ensure_schema()
    now = _utc_now()

    if bh and not force:
        existing = fetch_one(
            """
            SELECT id, status FROM open_threads
            WHERE person_id = ? AND body_hash = ?
            ORDER BY id DESC LIMIT 1
            """,
            [pid, bh],
        )
        if existing is not None:
            # Refresh last_mentioned_utc so cadence-sensitive queries still reflect
            # that we "saw" this commitment again, but don't create a new row.
            with transaction() as conn:
                conn.execute(
                    "UPDATE open_threads SET last_mentioned_utc = ?, updated_at = ? WHERE id = ?",
                    [last_dt, now, int(existing["id"])],
                )
            return {
                "status": "noop",
                "reason": "duplicate_body_hash",
                "id": int(existing["id"]),
                "thread_status": str(existing.get("status") or "open"),
                "person_id": pid,
                "body_hash": bh,
            }

    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO open_threads
              (person_id, summary, status, detail_json, updated_at,
               due_utc, promised_by, last_mentioned_utc,
               source_interaction_id, source_kind, body_hash, created_at)
            VALUES (?, ?, 'open', '{}', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [pid, txt, now, due_dt, pby, last_dt, sid, sk, bh, now],
        )
        row = conn.execute(
            "SELECT id FROM open_threads WHERE person_id=? ORDER BY id DESC LIMIT 1",
            [pid],
        ).fetchone()
        new_id = int(row[0]) if row else None

    return {
        "status": "ok",
        "id": new_id,
        "person_id": pid,
        "body": txt,
        "due_utc": str(due_dt) if due_dt else None,
        "promised_by": pby,
        "source_kind": sk,
        "body_hash": bh,
    }


def close_thread(thread_id: int, *, status: str = "done", reason: str = "") -> dict[str, Any]:
    """Transition open → done/dropped. No-op if already closed to same status."""
    tid = int(thread_id)
    new_status = (status or "done").strip().lower()
    if new_status not in {"done", "dropped"}:
        raise ValueError("status must be 'done' or 'dropped'")

    ensure_schema()
    row = fetch_one("SELECT id, status FROM open_threads WHERE id = ?", [tid])
    if row is None:
        return {"status": "error", "reason": "not_found", "id": tid}
    current = str(row.get("status") or "open").lower()
    if current == new_status:
        return {"status": "noop", "reason": f"already_{new_status}", "id": tid}

    now = _utc_now()
    with transaction() as conn:
        conn.execute(
            "UPDATE open_threads SET status = ?, updated_at = ? WHERE id = ?",
            [new_status, now, tid],
        )
    return {"status": "ok", "id": tid, "from": current, "to": new_status, "note": reason or ""}


def reopen_thread(thread_id: int) -> dict[str, Any]:
    tid = int(thread_id)
    ensure_schema()
    row = fetch_one("SELECT id, status FROM open_threads WHERE id = ?", [tid])
    if row is None:
        return {"status": "error", "reason": "not_found", "id": tid}
    current = str(row.get("status") or "open").lower()
    if current == "open":
        return {"status": "noop", "reason": "already_open", "id": tid}
    now = _utc_now()
    with transaction() as conn:
        conn.execute(
            "UPDATE open_threads SET status = 'open', updated_at = ? WHERE id = ?",
            [now, tid],
        )
    return {"status": "ok", "id": tid, "from": current, "to": "open"}


def update_due(thread_id: int, *, due_utc: datetime | str | None) -> dict[str, Any]:
    """Set or clear the due timestamp on an existing thread.

    Pass ``due_utc=None`` to clear; any parseable string/datetime to set.
    """
    tid = int(thread_id)
    due_dt = _coerce_dt(due_utc) if due_utc is not None else None
    ensure_schema()
    row = fetch_one("SELECT id FROM open_threads WHERE id = ?", [tid])
    if row is None:
        return {"status": "error", "reason": "not_found", "id": tid}
    now = _utc_now()
    with transaction() as conn:
        conn.execute(
            "UPDATE open_threads SET due_utc = ?, updated_at = ? WHERE id = ?",
            [due_dt, now, tid],
        )
    return {"status": "ok", "id": tid, "due_utc": str(due_dt) if due_dt else None}


def list_threads(
    *,
    person_id: str | None = None,
    status: str | None = "open",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List threads. ``status=None`` returns all statuses."""
    ensure_schema()
    lim = max(1, min(int(limit), 1000))
    where = ["1=1"]
    params: list[Any] = []
    if person_id and person_id.strip():
        where.append("person_id = ?")
        params.append(person_id.strip())
    if status:
        where.append("lower(coalesce(status,'open')) = ?")
        params.append(status.strip().lower())
    params.append(lim)
    return query(
        f"""
        SELECT id, person_id, summary AS body, status, due_utc, promised_by,
               last_mentioned_utc, source_interaction_id, source_kind,
               body_hash, updated_at, created_at
        FROM open_threads
        WHERE {' AND '.join(where)}
        ORDER BY
          CASE WHEN due_utc IS NULL THEN 1 ELSE 0 END,
          due_utc ASC,
          updated_at DESC
        LIMIT ?
        """,
        params,
    )


def list_due(
    *,
    within_days: int = 7,
    include_overdue: bool = True,
    person_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Threads with ``due_utc`` in the next ``within_days`` days.

    - ``include_overdue=True`` also returns rows with ``due_utc`` in the past
      (but still ``status='open'``).
    - Results sorted: overdue first (by how overdue), then soonest-due.
    """
    ensure_schema()
    now = _utc_now()
    horizon = now + timedelta(days=max(0, int(within_days)))
    lim = max(1, min(int(limit), 1000))

    where = ["lower(coalesce(status,'open')) = 'open'", "due_utc IS NOT NULL"]
    params: list[Any] = []
    if include_overdue:
        where.append("due_utc <= ?")
        params.append(horizon)
    else:
        # "Not overdue" = due at/after start-of-today (00:00 UTC), up to horizon.
        # Use start-of-today (not wall-clock ``now``) so a thread due earlier
        # today — but not yet "overdue" in the human sense — still shows up.
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        where.append("due_utc BETWEEN ? AND ?")
        params.extend([day_start, horizon])
    if person_id and person_id.strip():
        where.append("person_id = ?")
        params.append(person_id.strip())
    params.append(lim)

    return query(
        f"""
        SELECT id, person_id, summary AS body, status, due_utc, promised_by,
               last_mentioned_utc, source_interaction_id, source_kind,
               body_hash, updated_at, created_at
        FROM open_threads
        WHERE {' AND '.join(where)}
        ORDER BY due_utc ASC
        LIMIT ?
        """,
        params,
    )


def get_thread(thread_id: int) -> dict[str, Any] | None:
    ensure_schema()
    return fetch_one(
        """
        SELECT id, person_id, summary AS body, status, due_utc, promised_by,
               last_mentioned_utc, source_interaction_id, source_kind,
               body_hash, updated_at, created_at
        FROM open_threads
        WHERE id = ?
        """,
        [int(thread_id)],
    )


def classify_due(due_utc: datetime | str | None, *, now: datetime | None = None) -> str:
    """Return 'overdue' / 'today' / 'soon' / 'later' / 'none' for UI chrome.

    'soon' = 1..7 days; 'later' = > 7 days; 'none' = no due set.
    """
    d = _coerce_dt(due_utc)
    if d is None:
        return "none"
    ref = (now or _utc_now()).replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = ref
    day_end = ref + timedelta(days=1)
    if d < day_start:
        return "overdue"
    if d < day_end:
        return "today"
    if d < day_end + timedelta(days=7):
        return "soon"
    return "later"
