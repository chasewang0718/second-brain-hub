"""Import WhatsApp iOS ChatStorage.sqlite messages into interactions."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from brain_agents.identity_resolver import ensure_person_with_seed, resolve_identifier
from brain_agents.ingest_log import log_ingest_event
from brain_memory.structured import execute, fetch_one, transaction


def _cocoa_to_naive_utc(value: float | int | None) -> datetime | None:
    """Convert Core Data / WhatsApp timestamp to naive UTC datetime."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1e12:
        v = v / 1e9
        return datetime.fromtimestamp(v, tz=timezone.utc).replace(tzinfo=None)
    if v > 1e11:
        v = v / 1e3
        return datetime.fromtimestamp(v, tz=timezone.utc).replace(tzinfo=None)
    ref = datetime(2001, 1, 1, tzinfo=timezone.utc)
    return (ref + timedelta(seconds=v)).replace(tzinfo=None)


def _brief(text: str | None, msg_type: Any) -> str:
    if text and str(text).strip():
        t = str(text).strip().replace("\n", " ")
        return t[:160] + ("…" if len(t) > 160 else "")
    return f"[type={msg_type}]"


def _pick_peer_jid(
    *,
    is_from_me: int,
    zfrom: str | None,
    zto: str | None,
) -> str | None:
    zfrom = (zfrom or "").strip()
    zto = (zto or "").strip()
    if is_from_me:
        return zto or zfrom or None
    return zfrom or zto or None


def ingest_chatstorage_sqlite(
    db_path: Path,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    wrap_transaction: bool = True,
    emit_log: bool = True,
    backup_descriptor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        has_msg = conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND lower(name)=lower('ZWAMESSAGE')
            """
        ).fetchone()
        if not has_msg:
            return {"status": "unsupported", "reason": "no_ZWAMESSAGE", "path": str(db_path)}

        lim_sql = ""
        if limit is not None:
            lim_sql = f"LIMIT {max(1, int(limit))}"

        rows = conn.execute(
            f"""
            SELECT
              Z_PK AS z_pk,
              ZTEXT AS ztext,
              ZMESSAGEDATE AS zmessagedate,
              ZMESSAGETYPE AS zmessagetype,
              ZISFROMME AS zisfromme,
              ZFROMJID AS zfrom,
              ZTOJID AS zto,
              ZPUSHNAME AS zpush
            FROM ZWAMESSAGE
            WHERE Z_PK IS NOT NULL
            ORDER BY ZMESSAGEDATE DESC
            {lim_sql}
            """
        ).fetchall()
    except sqlite3.OperationalError as exc:
        return {"status": "error", "path": str(db_path), "detail": str(exc)}
    finally:
        conn.close()

    stats: dict[str, Any] = {
        "status": "ok",
        "path": str(db_path),
        "rows_seen": len(rows),
        "inserted": 0,
        "skipped_existing": 0,
        "messages_without_peer": 0,
        "persons_created": 0,
    }

    if dry_run:
        stats["status"] = "dry_run"
        stats["sample"] = []
        for row in rows[:15]:
            is_me = int(row["zisfromme"] or 0)
            peer = _pick_peer_jid(is_from_me=is_me, zfrom=row["zfrom"], zto=row["zto"])
            stats["sample"].append(
                {
                    "Z_PK": int(row["z_pk"]),
                    "ts": str(_cocoa_to_naive_utc(row["zmessagedate"])),
                    "peer": peer,
                    "preview": _brief(row["ztext"], row["zmessagetype"]),
                }
            )
        if emit_log:
            log_ingest_event(
                source="whatsapp_ios",
                mode="dry_run",
                stats=stats,
                source_path=db_path,
                backup=backup_descriptor,
            )
        return stats

    def _apply() -> None:
        for row in rows:
            z_pk = int(row["z_pk"])
            source_id = f"wa_ios:{z_pk}"
            exists = fetch_one(
                "SELECT id FROM interactions WHERE source_kind = ? AND source_id = ?",
                ["whatsapp_ios", source_id],
            )
            if exists:
                stats["skipped_existing"] += 1
                continue

            is_me = int(row["zisfromme"] or 0)
            peer = _pick_peer_jid(is_from_me=is_me, zfrom=row["zfrom"], zto=row["zto"])
            push = str(row["zpush"] or "").strip()

            person_id: str | None = None
            if peer:
                person_id = resolve_identifier("wa_jid", peer)
                if person_id is None:
                    label = push or peer.split("@", 1)[0]
                    person_id = ensure_person_with_seed(
                        label,
                        seed_identifiers=[("wa_jid", peer)],
                        source_kind="whatsapp_ios",
                    )
                    stats["persons_created"] += 1
            else:
                stats["messages_without_peer"] += 1

            ts = _cocoa_to_naive_utc(row["zmessagedate"]) or datetime.now(timezone.utc).replace(tzinfo=None)
            summary = _brief(row["ztext"], row["zmessagetype"])
            detail_obj = {k: row[k] for k in row.keys()}
            detail = json.dumps(detail_obj, ensure_ascii=False, default=str)[:8000]

            execute(
                """
                INSERT INTO interactions
                  (id, person_id, ts_utc, channel, summary, source_path, detail_json, source_kind, source_id)
                VALUES
                  (nextval('interactions_id_seq'), ?, ?, 'whatsapp', ?, ?, ?, 'whatsapp_ios', ?)
                """,
                [person_id, ts, summary, str(db_path), detail, source_id],
            )
            stats["inserted"] += 1

    t0 = time.monotonic()
    try:
        if wrap_transaction:
            with transaction():
                _apply()
        else:
            _apply()
    except Exception as exc:
        stats["status"] = "error"
        stats["error"] = f"{exc.__class__.__name__}: {exc}"
        if emit_log:
            log_ingest_event(
                source="whatsapp_ios",
                mode="apply",
                stats=stats,
                source_path=db_path,
                elapsed_ms=(time.monotonic() - t0) * 1000,
                backup=backup_descriptor,
            )
        raise

    elapsed_ms = (time.monotonic() - t0) * 1000
    stats["elapsed_ms"] = round(elapsed_ms, 1)
    if emit_log:
        log_ingest_event(
            source="whatsapp_ios",
            mode="apply",
            stats=stats,
            source_path=db_path,
            elapsed_ms=elapsed_ms,
            backup=backup_descriptor,
        )
    return stats
