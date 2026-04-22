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


def _hit_info(hit: ManifestHit) -> tuple[str, int]:
    basename = Path(hit.relative_path).name if hit.relative_path else ""
    size = 0
    if hit.resolved_path and hit.resolved_path.is_file():
        try:
            size = hit.resolved_path.stat().st_size
        except OSError:
            size = 0
    return basename, size


def _select_best_hit(hits: list[ManifestHit], *, exact_basename: str) -> tuple[ManifestHit | None, str, list[dict[str, Any]]]:
    """Rank Manifest hits and pick the real deal.

    B-ING-1.4: the first ingest grabbed an empty 20KB ``AddressBook.sqlitedb``
    that happened to be the first row returned by ``query_manifest_files``,
    which put the runbook into a "why is my person count so low?" spiral.
    This selector:

    1. Keeps only hits whose physical file actually exists.
    2. Strongly prefers hits whose basename exactly equals ``exact_basename``
       (e.g. ``AddressBook.sqlitedb``) over siblings like
       ``AddressBookImages.sqlitedb`` or ``AddressBook-v22.abcddb``.
    3. Among those, picks the one with the **largest non-zero size**.
    4. Falls back to "first resolved" only when every candidate is 0-byte.

    Returns ``(best_hit, selected_reason, ranked_candidates_dicts)``.
    """
    resolved = [h for h in hits if h.resolved_path and h.resolved_path.is_file()]

    enriched: list[tuple[ManifestHit, str, int, bool]] = []
    for h in resolved:
        base, size = _hit_info(h)
        exact = base.lower() == exact_basename.lower()
        enriched.append((h, base, size, exact))

    candidates = [
        {
            "file_id": h.file_id,
            "domain": h.domain,
            "relative_path": h.relative_path,
            "basename": base,
            "resolved_path": str(h.resolved_path) if h.resolved_path else None,
            "size": size,
            "exact_basename_match": exact,
        }
        for (h, base, size, exact) in enriched
    ]

    if not enriched:
        return None, "no_resolved_candidate", candidates

    exact_pool = [t for t in enriched if t[3]]
    pool = exact_pool if exact_pool else enriched

    nonempty = [t for t in pool if t[2] > 0]
    reason_prefix = "exact_basename" if exact_pool else "no_exact_basename_match"
    if nonempty:
        nonempty.sort(key=lambda t: t[2], reverse=True)
        best_hit, _, best_size, _ = nonempty[0]
        reason = f"{reason_prefix}+largest_size_{best_size}"
        return best_hit, reason, candidates

    pool.sort(key=lambda t: t[0].file_id)
    best_hit = pool[0][0]
    return best_hit, f"{reason_prefix}+all_empty_fallback", candidates


def _find_backup_file(
    *,
    backup_udid_dir: Path | None,
    roots: list[Path] | None,
    relative_path_substring: str,
    exact_basename: str,
    primary_domain_like: str | None,
) -> dict[str, Any]:
    """Shared plumbing for address-book / chat-storage locators."""
    base = backup_udid_dir or latest_backup_dir(roots)
    if base is None:
        return {"status": "not_found", "reason": "no_backup_with_manifest"}
    mf = base / "Manifest.db"
    if not mf.is_file():
        return {"status": "not_found", "backup_dir": str(base), "reason": "missing_manifest_db"}

    hits = query_manifest_files(mf, relative_path_substring=relative_path_substring, domain_like=primary_domain_like)
    if not hits:
        hits = query_manifest_files(mf, relative_path_substring=relative_path_substring, domain_like=None)

    best, reason, candidates = _select_best_hit(hits, exact_basename=exact_basename)
    selected_path = str(best.resolved_path) if best and best.resolved_path else None
    _, selected_size = _hit_info(best) if best else ("", 0)

    status = "ok" if selected_path else "unresolved"
    return {
        "status": status,
        "backup_dir": str(base),
        "hits": [
            {k: v for k, v in c.items() if k in ("file_id", "domain", "relative_path", "resolved_path")}
            for c in candidates[:20]
        ],
        "candidates": candidates[:20],
        "selected": selected_path,
        "selected_reason": reason,
        "selected_size": selected_size if best else 0,
    }


def find_chatstorage_sqlite(
    backup_udid_dir: Path | None = None,
    *,
    roots: list[Path] | None = None,
) -> dict[str, Any]:
    return _find_backup_file(
        backup_udid_dir=backup_udid_dir,
        roots=roots,
        relative_path_substring="ChatStorage.sqlite",
        exact_basename="ChatStorage.sqlite",
        primary_domain_like="whatsapp",
    )


def find_addressbook_sqlitedb(
    backup_udid_dir: Path | None = None,
    *,
    roots: list[Path] | None = None,
) -> dict[str, Any]:
    return _find_backup_file(
        backup_udid_dir=backup_udid_dir,
        roots=roots,
        relative_path_substring="AddressBook.sqlitedb",
        exact_basename="AddressBook.sqlitedb",
        primary_domain_like="HomeDomain",
    )


def locate_bundle(
    backup_udid_dir: Path | None = None,
    *,
    roots: list[Path] | None = None,
) -> dict[str, Any]:
    """Return resolved paths for WhatsApp ChatStorage + AddressBook when possible."""
    wa = find_chatstorage_sqlite(backup_udid_dir=backup_udid_dir, roots=roots)
    ab = find_addressbook_sqlitedb(backup_udid_dir=backup_udid_dir, roots=roots)
    return {"whatsapp": wa, "address_book": ab}
