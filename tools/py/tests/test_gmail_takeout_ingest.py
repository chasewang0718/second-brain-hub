"""Gmail Takeout mbox → interactions."""

from __future__ import annotations

import mailbox
from email.message import EmailMessage
from pathlib import Path

import pytest

from brain_agents.gmail_takeout_ingest import ingest_takeout_mbox
from brain_memory.structured import ensure_schema, fetch_one


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_DB_PATH", str(tmp_path / "g.duckdb"))
    ensure_schema()
    return tmp_path


def test_ingest_takeout_mbox_inserts(iso: Path) -> None:
    mbox_path = iso / "mail.mbox"
    mb = mailbox.mbox(str(mbox_path))
    msg = EmailMessage()
    msg["From"] = "Alice <alice@example.com>"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "Hello"
    msg["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    msg["Message-ID"] = "<unique-test-id-1@example.com>"
    msg.set_content("Body line one.")
    mb.add(msg)
    mb.close()

    out = ingest_takeout_mbox(mbox_path, dry_run=False, limit=10)
    assert out["status"] == "ok"
    assert out["inserted"] == 1
    row = fetch_one(
        "SELECT channel, source_kind, summary FROM interactions WHERE source_kind = 'gmail_mbox' LIMIT 1",
        [],
    )
    assert row["channel"] == "gmail"
    assert "Hello" in str(row["summary"])


def test_ingest_takeout_mbox_idempotent(iso: Path) -> None:
    mbox_path = iso / "t.mbox"
    mb = mailbox.mbox(str(mbox_path))
    msg = EmailMessage()
    msg["From"] = "x@y.com"
    msg["Subject"] = "S"
    msg["Date"] = "Tue, 2 Jan 2024 12:00:00 +0000"
    msg["Message-ID"] = "<idempotent@z.com>"
    msg.set_content("c")
    mb.add(msg)
    mb.close()
    ingest_takeout_mbox(mbox_path, dry_run=False)
    r2 = ingest_takeout_mbox(mbox_path, dry_run=False)
    assert r2["skipped_duplicate"] == 1
    assert r2["inserted"] == 0
