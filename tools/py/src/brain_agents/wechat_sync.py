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
from brain_memory.structured import ensure_schema, execute, fetch_one, query


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
        if "@chatroom" in wxid.lower():
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


def is_wechat_group_export(conversation: str, path: Path) -> bool:
    """True for WeChat multi-user chats (conversation id ends with ``@chatroom``)."""
    c = (conversation or "").strip().lower()
    if "@chatroom" in c:
        return True
    return "@chatroom" in path.name.lower()


def _conversation_peer(conversation: str) -> str | None:
    c = (conversation or "").strip()
    if not c or "chatroom" in c.lower():
        return None
    return c


def _parse_csv_set(raw: str | None) -> set[str]:
    if not raw:
        return set()
    out: set[str] = set()
    for part in str(raw).split(","):
        token = part.strip().lower()
        if token:
            out.add(token)
    return out


def _chat_key(conversation: str, file_path: Path) -> str:
    conv = (conversation or "").strip().lower()
    if conv:
        return conv
    return file_path.stem.strip().lower()


def _is_helper_conversation(conversation: str, file_path: Path) -> bool:
    key = _chat_key(conversation, file_path)
    return "filehelper" in key or "file_transfer_assistant" in key


def _brief_summary(msg: dict[str, Any]) -> str:
    mt = msg.get("msg_type")
    if mt == 1:
        text = str(msg.get("content") or "").strip().replace("\n", " ")
        return text[:120] + ("…" if len(text) > 120 else "")
    return f"[msg_type={mt}]"


def _normalize_group_chat_mode(raw: str) -> str:
    m = (raw or "").strip().lower()
    if m in ("skip", "bind_sender"):
        return m
    raise ValueError(f"group_chat_mode must be 'skip' or 'bind_sender', got {raw!r}")


def _looks_like_wechat_wxid(token: str) -> bool:
    t = (token or "").strip().lower()
    if not t or "chatroom" in t:
        return False
    return t.startswith("wxid_") or t.startswith("gh_")


def _resolve_group_message_person_id(msg: dict[str, Any]) -> str | None:
    """Map a group-chat message to a person when sender looks like a wxid or matches wechat_alias."""
    for key in ("sender", "sender_display", "group_sender_prefix"):
        v = str(msg.get(key) or "").strip()
        if not v:
            continue
        if _looks_like_wechat_wxid(v):
            pid = resolve_identifier("wxid", v)
            if pid:
                return pid
        pid_a = resolve_identifier("wechat_alias", v)
        if pid_a:
            return pid_a
    return None


def sync_chat_json(
    path: Path,
    *,
    dry_run: bool = False,
    since: datetime | None = None,
    helper_chat_mode: str = "link-person",
    group_chat_mode: str = "bind_sender",
) -> dict[str, Any]:
    gmode = _normalize_group_chat_mode(group_chat_mode)
    messages = read_chat_json(path)
    conversation = ""
    if messages:
        conversation = str(messages[0].get("conversation") or "")
    is_group = is_wechat_group_export(conversation, path)
    if is_group and gmode == "skip":
        return {
            "status": "skipped_group",
            "file": str(path),
            "conversation": conversation,
            "inserted": 0,
            "would_insert": 0,
            "skipped_existing": 0,
        }

    peer = _conversation_peer(conversation)
    if _is_helper_conversation(conversation, path) and helper_chat_mode.strip().lower() == "no-person":
        peer = None
    file_person_id: str | None = None
    if not is_group and peer:
        file_person_id = resolve_identifier("wxid", peer)

    inserted = 0
    skipped = 0
    pending: list[tuple[Any, ...]] = []
    bind_hits = 0
    bind_misses = 0

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
        if is_group and gmode == "bind_sender":
            msg_person_id = _resolve_group_message_person_id(msg)
            if msg_person_id:
                bind_hits += 1
            else:
                bind_misses += 1
        else:
            msg_person_id = file_person_id

        summary = _brief_summary(msg)
        detail = json.dumps(msg, ensure_ascii=False)[:8000]
        ts_sql = ts if ts is not None else datetime.now(UTC).replace(tzinfo=None)
        pending.append(
            (
                msg_person_id,
                ts_sql,
                summary,
                str(path),
                detail,
                source_id,
            )
        )

    if dry_run:
        out: dict[str, Any] = {
            "status": "dry_run",
            "file": str(path),
            "conversation": conversation,
            "would_insert": len(pending),
            "skipped_existing": skipped,
            "is_group": is_group,
            "group_chat_mode": gmode,
        }
        if is_group:
            out["group_bind_hits"] = bind_hits
            out["group_bind_misses"] = bind_misses
        return out

    for row in pending:
        msg_person_id, ts_sql, summary, src_path, detail, source_id = row
        execute(
            """
            INSERT INTO interactions
              (id, person_id, ts_utc, channel, summary, source_path, detail_json, source_kind, source_id)
            VALUES
              (nextval('interactions_id_seq'), ?, ?, 'wechat', ?, ?, ?, 'wechat', ?)
            """,
            [msg_person_id, ts_sql, summary, src_path, detail, source_id],
        )
        inserted += 1

    ret: dict[str, Any] = {
        "status": "ok",
        "file": str(path),
        "conversation": conversation,
        "inserted": inserted,
        "skipped_existing": skipped,
        "person_id": file_person_id,
        "is_group": is_group,
        "group_chat_mode": gmode,
    }
    if is_group:
        ret["group_bind_hits"] = bind_hits
        ret["group_bind_misses"] = bind_misses
    return ret


def sync_all(
    decoder_root: Path,
    *,
    artifacts_dir: Path | None = None,
    contact_db: Path | None = None,
    since: str | None = None,
    include_helper_chats: bool = False,
    chat_whitelist: str | None = None,
    chat_blacklist: str | None = None,
    helper_chat_mode: str = "link-person",
    group_chat_mode: str = "bind_sender",
    dry_run: bool = False,
    wrap_transaction: bool = True,
    emit_log: bool = True,
    backup_descriptor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import time as _time
    from brain_agents.ingest_log import log_ingest_event
    from brain_memory.structured import transaction

    art = artifacts_dir or (decoder_root / "artifacts")
    since_dt = _parse_ts(since) if since else None
    allow_set = _parse_csv_set(chat_whitelist)
    block_set = _parse_csv_set(chat_blacklist)
    helper_mode = helper_chat_mode.strip().lower() or "link-person"
    if helper_mode not in {"link-person", "no-person"}:
        raise ValueError(f"invalid helper_chat_mode: {helper_chat_mode}")
    gmode = _normalize_group_chat_mode(group_chat_mode)

    def _do() -> dict[str, Any]:
        out: dict[str, Any] = {"contacts": sync_contacts(decoder_root, contact_db=contact_db, dry_run=dry_run)}
        out["chats"] = []
        if not art.is_dir():
            out["chats_error"] = f"artifacts_dir_missing:{art}"
            return out
        for chat_file in candidate_chat_json_files(art, include_helper_chats=include_helper_chats):
            messages = read_chat_json(chat_file)
            conversation = str(messages[0].get("conversation") or "") if messages else ""
            key = _chat_key(conversation, chat_file)
            if allow_set and key not in allow_set:
                out["chats"].append(
                    {"status": "skipped_filter", "file": str(chat_file), "conversation": conversation, "reason": "not_in_whitelist"}
                )
                continue
            if block_set and key in block_set:
                out["chats"].append(
                    {"status": "skipped_filter", "file": str(chat_file), "conversation": conversation, "reason": "in_blacklist"}
                )
                continue
            out["chats"].append(
                sync_chat_json(
                    chat_file,
                    dry_run=dry_run,
                    since=since_dt,
                    helper_chat_mode=helper_mode,
                    group_chat_mode=gmode,
                )
            )
        return out

    t0 = _time.monotonic()
    try:
        if not dry_run and wrap_transaction:
            with transaction():
                out = _do()
        else:
            out = _do()
    except Exception as exc:
        err = {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"}
        if emit_log:
            log_ingest_event(
                source="wechat",
                mode="dry_run" if dry_run else "apply",
                stats=err,
                source_path=decoder_root,
                elapsed_ms=(_time.monotonic() - t0) * 1000,
                backup=backup_descriptor,
            )
        raise

    # Aggregate stats across sub-calls for the log row.
    contacts_stats = out.get("contacts", {}) or {}
    chats = out.get("chats", []) or []
    persons_created = int(contacts_stats.get("persons_created", 0) or 0) + sum(
        int((c or {}).get("persons_created", 0) or 0) for c in chats
    )
    inserted = sum(int((c or {}).get("inserted", 0) or 0) for c in chats)
    identifiers_added = int(contacts_stats.get("identifiers_added", 0) or 0)
    skipped_group = sum(1 for c in chats if (c or {}).get("status") == "skipped_group")

    agg = {
        "status": "dry_run" if dry_run else "ok",
        "persons_created": persons_created,
        "inserted": inserted,
        "identifiers_added": identifiers_added,
        "chats_processed": len(chats),
        "skipped_group_chats": skipped_group,
        "group_chat_mode": gmode,
        "contact_db": contacts_stats.get("contact_db"),
        "include_helper_chats": bool(include_helper_chats),
        "helper_chat_mode": helper_mode,
        "chat_whitelist": sorted(allow_set),
        "chat_blacklist": sorted(block_set),
    }
    elapsed_ms = (_time.monotonic() - t0) * 1000
    if emit_log:
        log_ingest_event(
            source="wechat",
            mode="dry_run" if dry_run else "apply",
            stats=agg,
            source_path=decoder_root,
            elapsed_ms=elapsed_ms,
            backup=backup_descriptor,
        )
    out["_agg"] = agg
    return out


def sync_from_cli(
    decoder_dir: str,
    *,
    contact_db: str = "",
    since: str = "",
    include_helper_chats: bool = False,
    chat_whitelist: str = "",
    chat_blacklist: str = "",
    helper_chat_mode: str = "link-person",
    group_chat_mode: str = "bind_sender",
    dry_run: bool = False,
) -> dict[str, Any]:
    root = Path(decoder_dir)
    cdb = Path(contact_db) if contact_db.strip() else None
    return sync_all(
        root,
        contact_db=cdb,
        since=since or None,
        include_helper_chats=include_helper_chats,
        chat_whitelist=chat_whitelist or None,
        chat_blacklist=chat_blacklist or None,
        helper_chat_mode=helper_chat_mode,
        group_chat_mode=group_chat_mode,
        dry_run=dry_run,
    )


def _wechat_legacy_orphan_group_interactions_sql() -> str:
    """Match old group-ingest rows: wechat + @chatroom id with **no** person binding."""
    return """(
        source_kind = 'wechat'
        AND person_id IS NULL
        AND (
            lower(coalesce(source_id, '')) LIKE '%@chatroom%'
            OR lower(coalesce(source_path, '')) LIKE '%@chatroom%'
        )
    )"""


def _delete_person_cascade(person_id: str) -> None:
    execute("DELETE FROM interactions WHERE person_id = ?", [person_id])
    execute("DELETE FROM person_notes WHERE person_id = ?", [person_id])
    execute("DELETE FROM person_insights WHERE person_id = ?", [person_id])
    execute("DELETE FROM open_threads WHERE person_id = ?", [person_id])
    execute(
        "DELETE FROM relationship_edges WHERE person_a = ? OR person_b = ?",
        [person_id, person_id],
    )
    execute(
        "DELETE FROM merge_candidates WHERE person_a = ? OR person_b = ?",
        [person_id, person_id],
    )
    execute(
        "DELETE FROM merge_log WHERE kept_person_id = ? OR absorbed_person_id = ?",
        [person_id, person_id],
    )
    execute("DELETE FROM person_identifiers WHERE person_id = ?", [person_id])
    execute("DELETE FROM persons WHERE person_id = ?", [person_id])


def prune_wechat_group_artifacts(*, dry_run: bool = True, prune_chatroom_contacts: bool = True) -> dict[str, Any]:
    """Remove **legacy** WeChat group rows (no person) and optional ``@chatroom`` contact stubs.

    - Deletes ``interactions`` where ``source_kind='wechat'``, ``person_id IS NULL``, and
      ``source_id`` / ``source_path`` references ``@chatroom`` (old whole-room ingest).
      Rows produced by ``bind_sender`` (non-null ``person_id``) are **not** deleted.
    - Optionally removes ``persons`` that only have ``wxid`` identifiers ending with ``@chatroom``.
    """
    ensure_schema()
    pred = _wechat_legacy_orphan_group_interactions_sql()
    row = fetch_one(f"SELECT COUNT(*) AS c FROM interactions WHERE {pred}", [])
    n_ix = int((row or {}).get("c") or 0)
    pids: list[str] = []
    if prune_chatroom_contacts:
        rows = query(
            """
            SELECT DISTINCT pi.person_id AS person_id
            FROM person_identifiers pi
            WHERE pi.kind = 'wxid' AND lower(pi.value_normalized) LIKE '%@chatroom%'
              AND NOT EXISTS (
                SELECT 1 FROM person_identifiers pi2
                WHERE pi2.person_id = pi.person_id
                  AND NOT (pi2.kind = 'wxid' AND lower(pi2.value_normalized) LIKE '%@chatroom%')
              )
            """
        )
        pids = [str(r["person_id"]) for r in rows if r.get("person_id")]

    if dry_run:
        return {
            "status": "dry_run",
            "interactions_to_delete": n_ix,
            "persons_to_delete": len(pids),
            "person_ids_preview": pids[:50],
        }

    from brain_memory.structured import transaction

    deleted_persons = 0
    with transaction():
        execute(f"DELETE FROM interactions WHERE {pred}")
        deleted_ix = n_ix
        if prune_chatroom_contacts and pids:
            for pid in pids:
                _delete_person_cascade(pid)
                deleted_persons += 1

    return {
        "status": "ok",
        "interactions_deleted": deleted_ix,
        "persons_deleted": deleted_persons,
        "graph_note": "Run `brain graph-rebuild-if-stale` or weekly E1 if Kuzu should drop stale group nodes.",
    }
