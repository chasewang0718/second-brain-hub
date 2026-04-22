"""Read-only access to wechat-decoder SQLite exports (contact DB + chat JSON)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator


def _has_contact_table(db_path: Path) -> bool:
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact' LIMIT 1"
        ).fetchone()
        conn.close()
        return row is not None
    except sqlite3.Error:
        return False


def find_contact_database(decoder_root: Path) -> Path | None:
    """Locate decrypted contact DB under wechat-decoder tree."""
    candidates: list[Path] = []
    for pattern in (
        "contact.db",
        "MicroMsg.db",
        "micro_msg.db",
        "decoded_contact.db",
    ):
        candidates.extend(decoder_root.rglob(pattern))
    for sub in ("decrypted", "artifacts", "output", "export"):
        d = decoder_root / sub
        if d.is_dir():
            candidates.extend(d.glob("*.db"))
            candidates.extend(d.glob("**/*.db"))
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in candidates:
        try:
            rp = str(p.resolve())
        except OSError:
            continue
        if rp not in seen and p.is_file():
            seen.add(rp)
            uniq.append(p)
    if not uniq:
        return None
    with_contact = [p for p in uniq if _has_contact_table(p)]
    pool = with_contact or uniq
    return max(pool, key=lambda x: x.stat().st_mtime)


def iter_contact_rows(db_path: Path) -> Iterator[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT username, nick_name, remark, alias, delete_flag
            FROM contact
            WHERE COALESCE(delete_flag, 0) = 0
            """
        )
        for row in cur:
            yield {
                "username": row["username"] or "",
                "nick_name": row["nick_name"] or "",
                "remark": row["remark"] or "",
                "alias": row["alias"] or "",
                "delete_flag": int(row["delete_flag"] or 0),
            }
    finally:
        conn.close()


def read_chat_json(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"expected JSON array in {path}")
    return [x for x in raw if isinstance(x, dict)]


def candidate_chat_json_files(artifacts_dir: Path, *, include_helper_chats: bool = False) -> list[Path]:
    out: list[Path] = []
    for f in sorted(artifacts_dir.glob("chat_*.json")):
        low = f.name.lower()
        if (not include_helper_chats) and ("filehelper" in low or "file_transfer_assistant" in low):
            continue
        out.append(f)
    return out
