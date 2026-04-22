"""Ingest Google Takeout ``*.mbox`` mail into DuckDB ``interactions`` (CRM threads)."""

from __future__ import annotations

import email
import hashlib
import json
import mailbox
from datetime import UTC, datetime, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any

from brain_agents.identity_resolver import resolve_identifier
from brain_agents.ingest_log import log_ingest_event
from brain_memory.structured import ensure_schema, execute, fetch_one, transaction


def _decode_subject(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw or "")


def _plain_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")
                    except Exception:
                        return payload.decode("utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        charset = msg.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except Exception:
            return payload.decode("utf-8", errors="replace")
    return str(payload or "")


def _parse_date(msg: email.message.Message) -> datetime | None:
    ds = msg.get("Date")
    if not ds:
        return None
    try:
        dt = parsedate_to_datetime(str(ds))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _stable_source_id(msg: email.message.Message) -> str:
    mid = (msg.get("Message-ID") or "").strip()
    if mid:
        h = hashlib.sha256(mid.encode("utf-8", errors="replace")).hexdigest()
        return h[:48]
    blob = "|".join(
        [
            str(msg.get("From") or ""),
            str(msg.get("Date") or ""),
            _decode_subject(msg.get("Subject")),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8", errors="replace")).hexdigest()[:48]


def _from_address(msg: email.message.Message) -> str | None:
    _, addr = parseaddr(str(msg.get("From") or ""))
    if addr and "@" in addr:
        return addr.strip().lower()
    return None


def _resolve_person_from_email(addr: str | None) -> str | None:
    if not addr:
        return None
    for kind in ("gmail_addr", "email"):
        pid = resolve_identifier(kind, addr)
        if pid:
            return pid
    return None


def _brief(subject: str, body: str) -> str:
    sub = (subject or "").strip().replace("\n", " ")[:100]
    b = (body or "").replace("\n", " ").strip()
    b = b[:140] + ("…" if len(b) > 140 else "")
    if sub and b:
        return f"{sub} — {b}"
    return sub or b or "[email]"


def _collect_mbox_paths(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() == ".mbox" else []
    return sorted({p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".mbox"})


def ingest_takeout_mbox(
    root: Path,
    *,
    dry_run: bool = False,
    limit: int = 0,
    since: datetime | None = None,
    wrap_transaction: bool = True,
    emit_log: bool = True,
    backup_descriptor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Import messages from Takeout ``.mbox`` file(s) under ``root`` (file or directory).

    Idempotency: ``source_kind=gmail_mbox`` + ``source_id`` derived from Message-ID (or hash).
    """
    import time as _time

    ensure_schema()
    paths = _collect_mbox_paths(root.resolve())
    if not paths:
        return {"status": "skipped", "reason": "no_mbox_found", "root": str(root)}

    lim = max(0, int(limit))
    seen = 0
    inserted = 0
    skipped_dup = 0
    skipped_since = 0
    errors: list[str] = []

    def _process_one_mbox(mbox_path: Path) -> None:
        nonlocal seen, inserted, skipped_dup, skipped_since
        try:
            mbox_obj = mailbox.mbox(str(mbox_path))
        except Exception as exc:
            errors.append(f"{mbox_path}:{exc}")
            return
        try:
            for key in mbox_obj.keys():
                if lim and inserted >= lim:
                    break
                msg_obj = mbox_obj.get(key)
                if msg_obj is None:
                    continue
                seen += 1
                ts = _parse_date(msg_obj)
                if since is not None and ts is not None and ts < since:
                    skipped_since += 1
                    continue
                sid = _stable_source_id(msg_obj)
                exists = fetch_one(
                    "SELECT id FROM interactions WHERE source_kind = ? AND source_id = ?",
                    ["gmail_mbox", sid],
                )
                if exists:
                    skipped_dup += 1
                    continue
                subj = _decode_subject(msg_obj.get("Subject"))
                body = _plain_body(msg_obj)
                frm = _from_address(msg_obj)
                pid = _resolve_person_from_email(frm)
                detail = {
                    "subject": subj[:500],
                    "from": frm,
                    "mbox_file": str(mbox_path),
                    "message_id": (msg_obj.get("Message-ID") or "")[:500],
                }
                summary = _brief(subj, body)
                ts_sql = ts if ts is not None else datetime.now(UTC).replace(tzinfo=None)
                detail_json = json.dumps(detail, ensure_ascii=False)[:8000]
                if dry_run:
                    inserted += 1
                    continue
                execute(
                    """
                    INSERT INTO interactions
                      (id, person_id, ts_utc, channel, summary, source_path, detail_json, source_kind, source_id)
                    VALUES
                      (nextval('interactions_id_seq'), ?, ?, 'gmail', ?, ?, ?, 'gmail_mbox', ?)
                    """,
                    [pid, ts_sql, summary, str(mbox_path), detail_json, sid],
                )
                inserted += 1
        finally:
            try:
                mbox_obj.close()
            except Exception:
                pass

    t0 = _time.monotonic()
    try:
        if not dry_run and wrap_transaction:
            with transaction():
                for mp in paths:
                    if lim and inserted >= lim:
                        break
                    _process_one_mbox(mp)
        else:
            for mp in paths:
                if lim and inserted >= lim:
                    break
                _process_one_mbox(mp)
    except Exception as exc:
        err = {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"}
        if emit_log:
            log_ingest_event(
                source="gmail_mbox",
                mode="dry_run" if dry_run else "apply",
                stats=err,
                source_path=root,
                elapsed_ms=(_time.monotonic() - t0) * 1000,
                backup=backup_descriptor,
            )
        raise

    stats = {
        "status": "dry_run" if dry_run else "ok",
        "mbox_files": len(paths),
        "messages_seen": seen,
        "inserted": inserted,
        "skipped_duplicate": skipped_dup,
        "skipped_since_filter": skipped_since,
        "errors": errors[:20],
        "root": str(root),
    }
    elapsed_ms = (_time.monotonic() - t0) * 1000
    if emit_log:
        log_ingest_event(
            source="gmail_mbox",
            mode="dry_run" if dry_run else "apply",
            stats=stats,
            source_path=root,
            elapsed_ms=elapsed_ms,
            backup=backup_descriptor,
        )
    return stats
