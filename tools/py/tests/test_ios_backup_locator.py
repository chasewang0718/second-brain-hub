"""Tests for B-ING-1.4: ios_backup_locator ranks candidates, skips empty sublibs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from brain_agents.ios_backup_locator import (
    _select_best_hit,
    find_addressbook_sqlitedb,
    find_chatstorage_sqlite,
    query_manifest_files,
)


def _build_manifest(manifest_path: Path, rows: list[tuple[str, str, str]]) -> None:
    """Create a tiny Manifest.db with the shape the real backup uses."""
    conn = sqlite3.connect(manifest_path)
    try:
        conn.execute(
            "CREATE TABLE Files (fileID TEXT PRIMARY KEY, domain TEXT, relativePath TEXT)"
        )
        conn.executemany("INSERT INTO Files VALUES (?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()


def _write_backup_file(backup_dir: Path, file_id: str, content: bytes) -> Path:
    sub = backup_dir / file_id[:2]
    sub.mkdir(parents=True, exist_ok=True)
    path = sub / file_id
    path.write_bytes(content)
    return path


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    udid = tmp_path / "abcd-udid"
    udid.mkdir()
    return udid


def test_prefers_exact_basename_over_wal_sibling(backup_dir: Path) -> None:
    # Real-world: AddressBook.sqlitedb + its WAL sibling both match the
    # substring query. Although WAL is bigger (uncheckpointed writes), we
    # must pick the .sqlitedb itself — that's the DB SQLite will open cleanly.
    rows = [
        ("aaawalside", "HomeDomain", "Library/AddressBook/AddressBook.sqlitedb-wal"),
        ("bbprimary0", "HomeDomain", "Library/AddressBook/AddressBook.sqlitedb"),
    ]
    _build_manifest(backup_dir / "Manifest.db", rows)
    _write_backup_file(backup_dir, "aaawalside", b"x" * 5_000_000)  # 5 MB WAL decoy
    _write_backup_file(backup_dir, "bbprimary0", b"y" * 200_000)   # 200 KB primary

    out = find_addressbook_sqlitedb(backup_dir)
    assert out["status"] == "ok"
    assert out["selected"].endswith("bbprimary0")
    assert "exact_basename" in out["selected_reason"]
    assert out["selected_size"] == 200_000
    basenames_ranked = [c["basename"] for c in out["candidates"]]
    assert "AddressBook.sqlitedb" in basenames_ranked
    assert "AddressBook.sqlitedb-wal" in basenames_ranked


def test_picks_nonempty_when_two_exact_basename_candidates(backup_dir: Path) -> None:
    # Both hits are exactly AddressBook.sqlitedb. One is the dreaded 0-byte
    # empty sublib (B-ING-1.4), the other has real data. Locator must pick
    # the non-empty one regardless of manifest row order.
    rows = [
        ("empty000000", "HomeDomain", "Library/AddressBook/AddressBook.sqlitedb"),
        ("real0000000", "HomeDomain", "Library/AddressBook/AddressBook.sqlitedb"),
    ]
    _build_manifest(backup_dir / "Manifest.db", rows)
    _write_backup_file(backup_dir, "empty000000", b"")
    _write_backup_file(backup_dir, "real0000000", b"z" * 150_000)

    out = find_addressbook_sqlitedb(backup_dir)
    assert out["status"] == "ok"
    assert out["selected"].endswith("real0000000")
    assert out["selected_size"] == 150_000
    assert "largest_size" in out["selected_reason"]


def test_reports_reason_when_only_empty_db_available(backup_dir: Path) -> None:
    rows = [
        ("only_empty_1", "HomeDomain", "Library/AddressBook/AddressBook.sqlitedb"),
    ]
    _build_manifest(backup_dir / "Manifest.db", rows)
    _write_backup_file(backup_dir, "only_empty_1", b"")

    out = find_addressbook_sqlitedb(backup_dir)
    # still returns ok=found, but tags it so the runbook / caller can warn.
    assert out["status"] == "ok"
    assert out["selected"].endswith("only_empty_1")
    assert out["selected_size"] == 0
    assert "all_empty_fallback" in out["selected_reason"]


def test_candidates_list_exposed_with_size_and_flag(backup_dir: Path) -> None:
    rows = [
        ("shmsibling", "HomeDomain", "Library/AddressBook/AddressBook.sqlitedb-shm"),
        ("primarydb0", "HomeDomain", "Library/AddressBook/AddressBook.sqlitedb"),
    ]
    _build_manifest(backup_dir / "Manifest.db", rows)
    _write_backup_file(backup_dir, "shmsibling", b"x" * 1000)
    _write_backup_file(backup_dir, "primarydb0", b"y" * 2000)

    out = find_addressbook_sqlitedb(backup_dir)
    cands = out["candidates"]
    assert {"file_id", "basename", "size", "exact_basename_match", "resolved_path"}.issubset(cands[0].keys())
    ab_entry = next(c for c in cands if c["file_id"] == "primarydb0")
    assert ab_entry["exact_basename_match"] is True
    assert ab_entry["size"] == 2000
    shm_entry = next(c for c in cands if c["file_id"] == "shmsibling")
    assert shm_entry["exact_basename_match"] is False


def test_chatstorage_also_uses_ranking(backup_dir: Path) -> None:
    # WhatsApp has ChatStorage.sqlite.wal / .shm siblings that resolve but are
    # not the primary DB. Exact basename beats them.
    rows = [
        ("wwshm", "AppDomainGroup-group.net.whatsapp.WhatsApp.shared",
         "ChatStorage.sqlite-shm"),
        ("wwreal", "AppDomainGroup-group.net.whatsapp.WhatsApp.shared",
         "ChatStorage.sqlite"),
    ]
    _build_manifest(backup_dir / "Manifest.db", rows)
    _write_backup_file(backup_dir, "wwshm", b"shm-ignored")
    _write_backup_file(backup_dir, "wwreal", b"real-wa-db-content")

    out = find_chatstorage_sqlite(backup_dir)
    assert out["status"] == "ok"
    assert out["selected"].endswith("wwreal")
    assert "exact_basename" in out["selected_reason"]


def test_select_best_hit_no_candidates_returns_sentinel(tmp_path: Path) -> None:
    # Direct unit test of the selector with an empty input.
    best, reason, candidates = _select_best_hit([], exact_basename="whatever")
    assert best is None
    assert reason == "no_resolved_candidate"
    assert candidates == []


def test_no_matching_manifest_rows_returns_unresolved(backup_dir: Path) -> None:
    _build_manifest(backup_dir / "Manifest.db", [])
    out = find_addressbook_sqlitedb(backup_dir)
    assert out["status"] == "unresolved"
    assert out["selected"] is None
    assert out["selected_reason"] == "no_resolved_candidate"


def test_query_manifest_files_filters_by_domain(backup_dir: Path) -> None:
    # Sanity: domain_like filter still works (existing behavior, regression-guard).
    rows = [
        ("homedom", "HomeDomain", "Library/AddressBook/AddressBook.sqlitedb"),
        ("wadom", "AppDomain-com.apple.WhatsApp", "Library/AddressBook/AddressBook.sqlitedb"),
    ]
    _build_manifest(backup_dir / "Manifest.db", rows)
    _write_backup_file(backup_dir, "homedom", b"home")
    _write_backup_file(backup_dir, "wadom", b"wa")

    hits_home = query_manifest_files(
        backup_dir / "Manifest.db",
        relative_path_substring="AddressBook.sqlitedb",
        domain_like="HomeDomain",
    )
    assert len(hits_home) == 1
    assert hits_home[0].file_id == "homedom"
