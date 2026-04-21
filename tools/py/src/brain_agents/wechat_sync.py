"""Import wechat-decoder artifacts into DuckDB persons / interactions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brain_agents.identity_resolver import (
    ensure_person_with_seed,
    register_identifier,
    resolve_identifier,
)
from brain_agents.wechat_decoder_io import (
    candidate_chat_json_files,
    find_contact_database,
    iter_contact_rows,
    read_chat_json,
)
from brain_agents.wechat_remark_extract import extract_from_remark
from brain_memory.structured import execute, fetch_one


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is not None:
            dt = dt.astimezone(UTC).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _primary_label(row: dict[str, Any]) -> str:
    r = (row.get("remark") or "").strip()
    n = (row.get("nick_name") or "").strip()
    u = (row.get("username") or "").strip()
    return r or n or u or "unknown"


def sync_contacts(
    decoder_root: Path,
    *,
    contact_db: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    db_path = contact_db or find_contact_database(decoder_root)
    if db_path is None:
        return {"status": "skipped", "reason": "contact_db_not_found", "decoder_root": str(decoder_root)}
    stats = {"contacts_seen": 0, "persons_created": 0, "identifiers_added": 0}
    rows: list[dict[str, Any]] = list(iter_contact_rows(db_path))
    stats["contacts_seen"] = len(rows)
    if dry_run:
        return {"status": "dry_run", "contact_db": str(db_path), **stats}

    for row in rows:
        wxid = (row.get("username") or "").strip()
        if not wxid:
            continue
        label = _primary_label(row)
        pid = resolve_identifier("wxid", wxid)
        if pid is None:
            pid = ensure_person_with_seed(label, seed_identifiers=[("wxid", wxid)], source_kind="wechat")
            stats["persons_created"] += 1
        else:
            if (row.get("remark") or "").strip():
                execute(
                    "UPDATE persons SET primary_name = ? WHERE person_id = ?",
                    [label, pid],
                )

        register_identifier(pid, "wxid", wxid, source_kind="wechat")

        alias = (row.get("alias") or "").strip()
        if alias:
            r = register_identifier(pid, "wechat_alias", alias, source_kind="wechat")
            if r.get("status") == "ok":
                stats["identifiers_added"] += 1

        sig = extract_from_remark(row.get("remark") or "")
        for phone in sig["phones"]:
            r = register_identifier(pid, "phone", phone, source_kind="wechat_remark")
            if r.get("status") == "ok":
                stats["identifiers_added"] += 1
        for email in sig["emails"]:
            r = register_identifier(pid, "email", email, source_kind="wechat_remark")
            if r.get("status") == "ok":
                stats["identifiers_added"] += 1

    return {"status": "ok", "contact_db": str(db_path), **stats}


def _conversation_peer(conversation: str) -> str | None:
    c = (conversation or "").strip()
    if not c or "chatroom" in c.lower():
        return None
    return c


def _brief_summary(msg: dict[str, Any]) -> str:
    mt = msg.get("msg_type")
    if mt == 1:
        text = str(msg.get("content") or "").strip().replace("\n", " ")
        return text[:120] + ("…" if len(text) > 120 else "")
    return f"[msg_type={mt}]"


def sync_chat_json(
    path: Path,
    *,
    dry_run: bool = False,
    since: datetime | None = None,
) -> dict[str, Any]:
    messages = read_chat_json(path)
    conversation = ""
    if messages:
        conversation = str(messages[0].get("conversation") or "")
    peer = _conversation_peer(conversation)
    person_id: str | None = None
    if peer:
        person_id = resolve_identifier("wxid", peer)

    inserted = 0
    skipped = 0
    pending: list[tuple[Any, ...]] = []

    for msg in messages:
        ts = _parse_ts(str(msg.get("ts") or ""))
        if since is not None and ts is not None and ts < since:
            continue
        local_id = msg.get("local_id")
        if local_id is None:
            continue
        source_id = f"{local_id}@{conversation or path.stem}"
        exists = fetch_one(
            "SELECT id FROM interactions WHERE source_kind = ? AND source_id = ?",
            ["wechat", source_id],
        )
        if exists:
            skipped += 1
            continue
        summary = _brief_summary(msg)
        detail = json.dumps(msg, ensure_ascii=False)[:8000]
        ts_sql = ts if ts is not None else datetime.now(UTC).replace(tzinfo=None)
        pending.append(
            (
                person_id,
                ts_sql,
                summary,
                str(path),
                detail,
                source_id,
            )
        )

    if dry_run:
        return {
            "status": "dry_run",
            "file": str(path),
            "conversation": conversation,
            "would_insert": len(pending),
            "skipped_existing": skipped,
        }

    for row in pending:
        person_id, ts_sql, summary, src_path, detail, source_id = row
        execute(
            """
            INSERT INTO interactions
              (id, person_id, ts_utc, channel, summary, source_path, detail_json, source_kind, source_id)
            VALUES
              (nextval('interactions_id_seq'), ?, ?, 'wechat', ?, ?, ?, 'wechat', ?)
            """,
            [person_id, ts_sql, summary, src_path, detail, source_id],
        )
        inserted += 1

    return {
        "status": "ok",
        "file": str(path),
        "conversation": conversation,
        "inserted": inserted,
        "skipped_existing": skipped,
        "person_id": person_id,
    }


def sync_all(
    decoder_root: Path,
    *,
    artifacts_dir: Path | None = None,
    contact_db: Path | None = None,
    since: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    art = artifacts_dir or (decoder_root / "artifacts")
    since_dt = _parse_ts(since) if since else None
    out: dict[str, Any] = {"contacts": sync_contacts(decoder_root, contact_db=contact_db, dry_run=dry_run)}
    out["chats"] = []
    if not art.is_dir():
        out["chats_error"] = f"artifacts_dir_missing:{art}"
        return out
    for chat_file in candidate_chat_json_files(art):
        out["chats"].append(sync_chat_json(chat_file, dry_run=dry_run, since=since_dt))
    return out


def sync_from_cli(
    decoder_dir: str,
    *,
    contact_db: str = "",
    since: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    root = Path(decoder_dir)
    cdb = Path(contact_db) if contact_db.strip() else None
    return sync_all(root, contact_db=cdb, since=since or None, dry_run=dry_run)
