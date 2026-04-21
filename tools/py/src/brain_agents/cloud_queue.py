"""Outbound queue for work local models decline (manual `brain cloud flush`)."""

from __future__ import annotations

import json
from datetime import datetime, UTC
from typing import Any

from brain_memory.structured import execute, query


def enqueue(
    task_kind: str,
    payload: dict[str, Any],
    *,
    priority: str = "normal",
    local_attempt_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload_json = json.dumps(payload, ensure_ascii=False)
    detail = json.dumps(local_attempt_json or {}, ensure_ascii=False)
    rows = query(
        """
        INSERT INTO cloud_queue (task_kind, payload_json, priority, local_attempt_json, status)
        VALUES (?, ?, ?, ?, 'pending')
        RETURNING id
        """,
        [task_kind, payload_json, priority, detail],
    )
    rid = int(rows[0]["id"]) if rows else None
    return {"status": "ok", "cloud_queue_id": rid}


def list_pending(limit: int = 50) -> list[dict[str, Any]]:
    return query(
        """
        SELECT id, task_kind, priority, created_at, status,
               substr(payload_json, 1, 2000) AS payload_preview
        FROM cloud_queue
        WHERE status = 'pending'
        ORDER BY id ASC
        LIMIT ?
        """,
        [limit],
    )


def show(queue_id: int) -> dict[str, Any] | None:
    rows = query(
        """
        SELECT id, task_kind, payload_json, priority, local_attempt_json,
               created_at, status, result_json, processed_at
        FROM cloud_queue WHERE id = ?
        """,
        [queue_id],
    )
    return rows[0] if rows else None


def drop(queue_id: int) -> dict[str, Any]:
    execute("DELETE FROM cloud_queue WHERE id = ?", [queue_id])
    return {"status": "dropped", "id": queue_id}


def mark_processed(queue_id: int, result: dict[str, Any] | None = None) -> None:
    result_json = json.dumps(result or {}, ensure_ascii=False)
    now = datetime.now(UTC).replace(tzinfo=None)
    execute(
        """
        UPDATE cloud_queue
        SET status = 'done', result_json = ?, processed_at = ?
        WHERE id = ?
        """,
        [result_json, now, queue_id],
    )


TASK_KIND_REGISTRY: dict[str, str] = {
    "capsd-note-hard": "Caps+D inbox note needing cloud model / human merge",
    "ocr-hard": "OCR extraction failed locally",
    "merge-t3-review": "Ambiguous identifier merge_candidate needs review",
}
