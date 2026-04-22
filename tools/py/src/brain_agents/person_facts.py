"""Bi-temporal person facts (Phase A6 Sprint 1).

Write model: every (person_id, key) has at most ONE row with
``valid_to IS NULL`` at any given time (= "currently valid"). Writing a
new fact for the same key automatically closes the previous open row by
setting its ``valid_to = now``.

Value model: ``value_json`` is always JSON-encoded (``json.dumps`` applied
once). Callers should pass raw Python values via ``add_fact(value=...)``
and rely on the module to serialize. To store a pre-built JSON string
verbatim, use ``add_fact(value_json=...)``.

All writes go through the :func:`brain_memory.structured.transaction`
context so B-ING-0 rollback guarantees extend here too.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from brain_memory.structured import ensure_schema, execute, fetch_one, query, transaction


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _normalize_value_json(
    *,
    value: Any,
    value_json: str | None,
) -> str:
    if value_json is not None:
        s = str(value_json).strip()
        if not s:
            raise ValueError("value_json must be non-empty")
        try:
            json.loads(s)
        except json.JSONDecodeError as exc:
            raise ValueError(f"value_json must be valid JSON: {exc}") from exc
        return s
    return json.dumps(value, ensure_ascii=False)


def _current_open_fact(person_id: str, key: str) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT id, value_json, confidence, source_kind, source_interaction_id, valid_from
        FROM person_facts
        WHERE person_id = ? AND key = ? AND valid_to IS NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        [person_id, key],
    )
    return row


def add_fact(
    person_id: str,
    key: str,
    value: Any = None,
    *,
    value_json: str | None = None,
    confidence: float = 1.0,
    source_kind: str = "manual",
    source_interaction_id: int | None = None,
    valid_from: datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Insert a new current fact, closing any prior open fact for the same key.

    Returns ``{"status": "ok"|"noop", "person_id", "key", "value_json",
    "inserted_id", "closed_id", "valid_from"}``.

    When ``force=False`` (default) and the current open fact has identical
    ``value_json`` + ``confidence`` + ``source_kind``, we skip writing and
    return ``status="noop"`` to keep history tidy. Set ``force=True`` to
    record the assertion anyway (useful when ``source_interaction_id``
    changes even though the value didn't).
    """
    pid = (person_id or "").strip()
    k = (key or "").strip()
    if not pid:
        raise ValueError("person_id is required")
    if not k:
        raise ValueError("key is required")
    vj = _normalize_value_json(value=value, value_json=value_json)
    conf = float(confidence if confidence is not None else 1.0)
    sk = str(source_kind or "manual")
    sid = int(source_interaction_id) if source_interaction_id else None
    vf = valid_from.replace(tzinfo=None) if (valid_from and valid_from.tzinfo) else (valid_from or _utc_now())

    ensure_schema()
    current = _current_open_fact(pid, k)
    if (
        current is not None
        and not force
        and str(current.get("value_json") or "") == vj
        and float(current.get("confidence") or 0.0) == conf
        and str(current.get("source_kind") or "") == sk
    ):
        return {
            "status": "noop",
            "person_id": pid,
            "key": k,
            "value_json": vj,
            "inserted_id": None,
            "closed_id": None,
            "valid_from": str(current.get("valid_from")),
            "reason": "identical_current_fact",
        }

    closed_id = None
    with transaction() as conn:
        if current is not None:
            closed_id = int(current["id"])
            prior_from = current.get("valid_from")
            # Close the prior row at the new fact's valid_from (seamless bi-temporal
            # handoff). If the caller backfilled a valid_from that's earlier than
            # the prior row's own valid_from, fall back to vf anyway — the row
            # will collapse (valid_to <= valid_from) and be correctly excluded
            # from point-in-time queries, which is the least-surprising behaviour
            # for "I mis-ordered my backfill".
            close_at = vf
            if prior_from is not None and close_at < prior_from:
                close_at = prior_from
            conn.execute(
                "UPDATE person_facts SET valid_to = ? WHERE id = ?",
                [close_at, closed_id],
            )
        conn.execute(
            """
            INSERT INTO person_facts
              (person_id, key, value_json, valid_from, valid_to,
               confidence, source_kind, source_interaction_id)
            VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            [pid, k, vj, vf, conf, sk, sid],
        )
        row = conn.execute(
            "SELECT id FROM person_facts WHERE person_id=? AND key=? AND valid_to IS NULL ORDER BY id DESC LIMIT 1",
            [pid, k],
        ).fetchone()
        inserted_id = int(row[0]) if row else None

    return {
        "status": "ok",
        "person_id": pid,
        "key": k,
        "value_json": vj,
        "inserted_id": inserted_id,
        "closed_id": closed_id,
        "valid_from": str(vf),
    }


def invalidate_fact(fact_id: int, *, reason: str = "") -> dict[str, Any]:
    """Close an open fact (set ``valid_to = now``).

    Returns ``status=ok`` on success, ``status=noop`` if the row is already
    closed, ``status=error`` if the fact_id doesn't exist. ``reason`` is
    currently advisory (logged by caller); we keep the schema minimal.
    """
    fid = int(fact_id)
    ensure_schema()
    row = fetch_one("SELECT id, valid_to FROM person_facts WHERE id = ?", [fid])
    if row is None:
        return {"status": "error", "reason": "not_found", "fact_id": fid}
    if row.get("valid_to") is not None:
        return {"status": "noop", "reason": "already_closed", "fact_id": fid}
    now = _utc_now()
    with transaction() as conn:
        conn.execute("UPDATE person_facts SET valid_to = ? WHERE id = ?", [now, fid])
    return {"status": "ok", "fact_id": fid, "valid_to": str(now), "note": reason or ""}


def list_facts(
    person_id: str,
    *,
    at: datetime | None = None,
    include_history: bool = False,
    key: str | None = None,
) -> list[dict[str, Any]]:
    """Return facts for ``person_id``.

    - ``include_history=True`` → all rows (ordered by key, valid_from DESC);
      ``at`` is ignored.
    - ``include_history=False`` and ``at=None`` → only currently-valid facts
      (``valid_to IS NULL``).
    - ``include_history=False`` and ``at=<datetime>`` → facts that were valid
      at that instant (``valid_from <= at AND (valid_to IS NULL OR valid_to > at)``).

    Pass ``key=`` to filter to a single key.
    """
    pid = (person_id or "").strip()
    if not pid:
        return []
    ensure_schema()

    params: list[Any] = [pid]
    where = ["person_id = ?"]
    if key and key.strip():
        where.append("key = ?")
        params.append(key.strip())

    if include_history:
        sql = f"""
            SELECT id, person_id, key, value_json, valid_from, valid_to,
                   confidence, source_kind, source_interaction_id, created_at
            FROM person_facts
            WHERE {' AND '.join(where)}
            ORDER BY key, valid_from DESC, id DESC
        """
        return query(sql, params)

    if at is None:
        where.append("valid_to IS NULL")
        sql = f"""
            SELECT id, person_id, key, value_json, valid_from, valid_to,
                   confidence, source_kind, source_interaction_id, created_at
            FROM person_facts
            WHERE {' AND '.join(where)}
            ORDER BY key
        """
        return query(sql, params)

    at_clean = at.replace(tzinfo=None) if at.tzinfo else at
    where.append("valid_from <= ?")
    params.append(at_clean)
    where.append("(valid_to IS NULL OR valid_to > ?)")
    params.append(at_clean)
    sql = f"""
        SELECT id, person_id, key, value_json, valid_from, valid_to,
               confidence, source_kind, source_interaction_id, created_at
        FROM person_facts
        WHERE {' AND '.join(where)}
        ORDER BY key
    """
    return query(sql, params)


def get_fact(person_id: str, key: str, *, at: datetime | None = None) -> dict[str, Any] | None:
    rows = list_facts(person_id, at=at, include_history=False, key=key)
    return rows[0] if rows else None


def decode_value(row: dict[str, Any]) -> Any:
    """Best-effort decode of ``value_json`` back to a Python value."""
    try:
        return json.loads(str(row.get("value_json") or "null"))
    except json.JSONDecodeError:
        return row.get("value_json")
