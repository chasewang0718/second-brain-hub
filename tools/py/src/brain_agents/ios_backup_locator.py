"""Locate iTunes/Finder iPhone backup folders and resolve hashed files via Manifest.db."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def default_backup_roots() -> list[Path]:
    roots: list[Path] = []
    user = os.environ.get("USERPROFILE", "").strip()
    if user:
        base = Path(user) / "Apple"
        roots.extend(
            [
                base / "Mobile Sync" / "Backup",
                base / "MobileSync" / "Backup",
            ]
        )
    lad = os.environ.get("LOCALAPPDATA", "").strip()
    if lad:
        roots.append(Path(lad) / "Apple Computer" / "MobileSync" / "Backup")
    return roots


def iter_backup_udid_dirs(roots: list[Path] | None = None) -> list[Path]:
    """Enumerate child UDID folders that contain Manifest.db."""
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots or default_backup_roots():
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            manifest = child / "Manifest.db"
            if not manifest.is_file():
                continue
            try:
                key = str(child.resolve())
            except OSError:
                continue
            if key not in seen:
                seen.add(key)
                out.append(child)
    return out


def latest_backup_dir(roots: list[Path] | None = None) -> Path | None:
    cand = iter_backup_udid_dirs(roots)
    if not cand:
        return None
    return max(cand, key=lambda p: p.stat().st_mtime)


def _physical_path(backup_udid_dir: Path, file_id: str) -> Path | None:
    fid = file_id.strip()
    if len(fid) < 3:
        return None
    c1 = backup_udid_dir / fid[:2] / fid
    if c1.is_file():
        return c1
    c2 = backup_udid_dir / fid
    if c2.is_file():
        return c2
    return None


@dataclass
class ManifestHit:
    file_id: str
    domain: str
    relative_path: str
    resolved_path: Path | None


def query_manifest_files(
    manifest_db: Path,
    *,
    relative_path_substring: str,
    domain_like: str | None = None,
) -> list[ManifestHit]:
    conn = sqlite3.connect(f"file:{manifest_db.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT fileID, domain, relativePath FROM Files WHERE relativePath LIKE ?",
            [f"%{relative_path_substring}%"],
        ).fetchall()
    finally:
        conn.close()

    backup_root = manifest_db.parent
    hits: list[ManifestHit] = []
    for file_id, domain, rel_path in rows:
        dom = domain or ""
        if domain_like and domain_like.lower() not in dom.lower():
            continue
        rp = _physical_path(backup_root, str(file_id))
        hits.append(
            ManifestHit(
                file_id=str(file_id),
                domain=str(domain or ""),
                relative_path=str(rel_path or ""),
                resolved_path=rp,
            )
        )
    return hits


def find_chatstorage_sqlite(
    backup_udid_dir: Path | None = None,
    *,
    roots: list[Path] | None = None,
) -> dict[str, Any]:
    base = backup_udid_dir or latest_backup_dir(roots)
    if base is None:
        return {"status": "not_found", "reason": "no_backup_with_manifest"}
    mf = base / "Manifest.db"
    if not mf.is_file():
        return {"status": "not_found", "backup_dir": str(base), "reason": "missing_manifest_db"}
    hits = query_manifest_files(mf, relative_path_substring="ChatStorage.sqlite", domain_like="whatsapp")
    if not hits:
        hits = query_manifest_files(mf, relative_path_substring="ChatStorage.sqlite", domain_like=None)
    best = next((h for h in hits if h.resolved_path and h.resolved_path.is_file()), None)
    return {
        "status": "ok" if best and best.resolved_path else "unresolved",
        "backup_dir": str(base),
        "hits": [
            {
                "file_id": h.file_id,
                "domain": h.domain,
                "relative_path": h.relative_path,
                "resolved_path": str(h.resolved_path) if h.resolved_path else None,
            }
            for h in hits[:20]
        ],
        "selected": str(best.resolved_path) if best and best.resolved_path else None,
    }


def find_addressbook_sqlitedb(
    backup_udid_dir: Path | None = None,
    *,
    roots: list[Path] | None = None,
) -> dict[str, Any]:
    base = backup_udid_dir or latest_backup_dir(roots)
    if base is None:
        return {"status": "not_found", "reason": "no_backup_with_manifest"}
    mf = base / "Manifest.db"
    if not mf.is_file():
        return {"status": "not_found", "backup_dir": str(base), "reason": "missing_manifest_db"}
    hits = query_manifest_files(mf, relative_path_substring="AddressBook.sqlitedb", domain_like="HomeDomain")
    if not hits:
        hits = query_manifest_files(mf, relative_path_substring="AddressBook.sqlitedb", domain_like=None)
    best = next((h for h in hits if h.resolved_path and h.resolved_path.is_file()), None)
    return {
        "status": "ok" if best and best.resolved_path else "unresolved",
        "backup_dir": str(base),
        "hits": [
            {
                "file_id": h.file_id,
                "domain": h.domain,
                "relative_path": h.relative_path,
                "resolved_path": str(h.resolved_path) if h.resolved_path else None,
            }
            for h in hits[:20]
        ],
        "selected": str(best.resolved_path) if best and best.resolved_path else None,
    }


def locate_bundle(
    backup_udid_dir: Path | None = None,
    *,
    roots: list[Path] | None = None,
) -> dict[str, Any]:
    """Return resolved paths for WhatsApp ChatStorage + AddressBook when possible."""
    wa = find_chatstorage_sqlite(backup_udid_dir=backup_udid_dir, roots=roots)
    ab = find_addressbook_sqlitedb(backup_udid_dir=backup_udid_dir, roots=roots)
    return {"whatsapp": wa, "address_book": ab}
