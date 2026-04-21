"""Import iOS AddressBook.sqlitedb into persons + phone/email identifiers."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from brain_agents.identity_resolver import ensure_person_with_seed, register_identifier, resolve_identifier
from brain_agents.ingest_log import log_ingest_event
from brain_memory.structured import transaction


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND lower(name)=lower(?)",
        [name],
    ).fetchone()
    return row is not None


def _compose_name(first: str, last: str, org: str) -> str:
    parts = [first.strip(), last.strip()]
    core = " ".join(p for p in parts if p).strip()
    return core or org.strip() or "unknown"


def ingest_address_book_sqlite(
    db_path: Path,
    *,
    dry_run: bool = False,
    wrap_transaction: bool = True,
    emit_log: bool = True,
    backup_descriptor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "ABPerson") or not _table_exists(conn, "ABMultiValue"):
            return {
                "status": "unsupported",
                "reason": "missing_ab_tables",
                "path": str(db_path),
            }

        persons = conn.execute(
            """
            SELECT ROWID AS rid, First, Last, Organization
            FROM ABPerson
            """
        ).fetchall()

        mv_rows = conn.execute(
            """
            SELECT record_id AS rid, property, value
            FROM ABMultiValue
            WHERE property IN (3, 4) AND value IS NOT NULL AND trim(value) != ''
            """
        ).fetchall()
    finally:
        conn.close()

    by_rid: dict[int, dict[str, list[str]]] = {}
    for row in mv_rows:
        rid = int(row["rid"])
        prop = int(row["property"])
        val = str(row["value"]).strip()
        if not val:
            continue
        bucket = by_rid.setdefault(rid, {"phones": [], "emails": []})
        if prop == 3:
            bucket["phones"].append(val)
        elif prop == 4:
            bucket["emails"].append(val)

    stats = {
        "status": "ok",
        "path": str(db_path),
        "person_rows": len(persons),
        "multi_value_rows": len(mv_rows),
        "persons_created": 0,
        "identifiers_added": 0,
    }

    if dry_run:
        stats["status"] = "dry_run"
        stats["sample"] = [
            {
                "rid": int(p["rid"]),
                "name": _compose_name(
                    str(p["First"] or ""),
                    str(p["Last"] or ""),
                    str(p["Organization"] or ""),
                ),
                "phones": by_rid.get(int(p["rid"]), {}).get("phones", [])[:3],
                "emails": by_rid.get(int(p["rid"]), {}).get("emails", [])[:3],
            }
            for p in persons[:20]
        ]
        if emit_log:
            log_ingest_event(
                source="ios_addressbook",
                mode="dry_run",
                stats=stats,
                source_path=db_path,
                backup=backup_descriptor,
            )
        return stats

    def _apply() -> None:
        for p in persons:
            rid = int(p["rid"])
            label = _compose_name(
                str(p["First"] or ""),
                str(p["Last"] or ""),
                str(p["Organization"] or ""),
            )
            stable = f"ios_ab:{rid}"
            pid = resolve_identifier("ios_contact_row", stable)
            phones = by_rid.get(rid, {}).get("phones", [])
            emails = by_rid.get(rid, {}).get("emails", [])
            seed: list[tuple[str, str]] = [("ios_contact_row", stable)]
            if pid is None:
                pid = ensure_person_with_seed(
                    label,
                    seed_identifiers=seed,
                    source_kind="ios_addressbook",
                )
                stats["persons_created"] += 1
            else:
                register_identifier(pid, "ios_contact_row", stable, source_kind="ios_addressbook")

            for ph in phones:
                r = register_identifier(pid, "phone", ph, source_kind="ios_addressbook")
                if r.get("status") == "ok":
                    stats["identifiers_added"] += 1
            for em in emails:
                r = register_identifier(pid, "email", em, source_kind="ios_addressbook")
                if r.get("status") == "ok":
                    stats["identifiers_added"] += 1

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
        elapsed_ms = (time.monotonic() - t0) * 1000
        if emit_log:
            log_ingest_event(
                source="ios_addressbook",
                mode="apply",
                stats=stats,
                source_path=db_path,
                elapsed_ms=elapsed_ms,
                backup=backup_descriptor,
            )
        raise

    elapsed_ms = (time.monotonic() - t0) * 1000
    stats["elapsed_ms"] = round(elapsed_ms, 1)
    if emit_log:
        log_ingest_event(
            source="ios_addressbook",
            mode="apply",
            stats=stats,
            source_path=db_path,
            elapsed_ms=elapsed_ms,
            backup=backup_descriptor,
        )
    return stats
