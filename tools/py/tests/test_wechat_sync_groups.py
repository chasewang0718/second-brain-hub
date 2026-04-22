"""WeChat @chatroom: bind_sender vs skip + legacy orphan prune."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from brain_agents.wechat_sync import (
    is_wechat_group_export,
    prune_wechat_group_artifacts,
    sync_chat_json,
    sync_contacts,
)
from brain_memory.structured import ensure_schema, execute, fetch_one, query


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_DB_PATH", str(tmp_path / "w.duckdb"))
    ensure_schema()
    return tmp_path


def test_is_wechat_group_export() -> None:
    p = Path("chat_abc@chatroom.json")
    assert is_wechat_group_export("", p) is True
    assert is_wechat_group_export("x@chatroom", Path("chat_x.json")) is True
    assert is_wechat_group_export("friend_wxid", Path("chat_friend.json")) is False


def test_sync_chat_json_skip_group_mode(iso_db, tmp_path) -> None:
    body = [
        {
            "conversation": "g@chatroom",
            "ts": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "local_id": 99,
            "content": "greet",
            "msg_type": 1,
            "sender": "wxid_abcd",
        }
    ]
    path = tmp_path / "chat_g.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    r = sync_chat_json(path, dry_run=False, group_chat_mode="skip")
    assert r["status"] == "skipped_group"
    assert r["inserted"] == 0


def test_sync_chat_json_bind_sender_resolves_wxid(iso_db, tmp_path) -> None:
    execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES ('p_wxid_one', 'Peer One', '[]', '[]', CURRENT_TIMESTAMP)
        """
    )
    execute(
        """
        INSERT INTO person_identifiers (person_id, kind, value_normalized, value_original, source_kind)
        VALUES ('p_wxid_one', 'wxid', 'wxid_abcd', 'wxid_abcd', 'wechat')
        """
    )
    body = [
        {
            "conversation": "room@chatroom",
            "ts": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "local_id": 501,
            "content": "hello group",
            "msg_type": 1,
            "sender": "wxid_abcd",
            "sender_display": "wxid_abcd",
        }
    ]
    path = tmp_path / "chat_room.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    r = sync_chat_json(path, dry_run=False, group_chat_mode="bind_sender")
    assert r["status"] == "ok"
    assert r["inserted"] == 1
    row = fetch_one(
        "SELECT person_id, summary FROM interactions WHERE source_kind='wechat' AND source_id LIKE '501@%'",
        [],
    )
    assert row["person_id"] == "p_wxid_one"
    assert "hello group" in str(row["summary"])


def test_prune_wechat_group_interactions_orphan_only(iso_db, tmp_path, monkeypatch) -> None:
    execute(
        """
        INSERT INTO interactions
          (id, person_id, ts_utc, channel, summary, source_path, detail_json, source_kind, source_id)
        VALUES
          (nextval('interactions_id_seq'), NULL, CURRENT_TIMESTAMP, 'wechat', 'g', 'D:/x/chat_a@chatroom.json', '{}', 'wechat', '1@a@chatroom')
        """
    )
    execute(
        """
        INSERT INTO interactions
          (id, person_id, ts_utc, channel, summary, source_path, detail_json, source_kind, source_id)
        VALUES
          (nextval('interactions_id_seq'), 'p_keep', CURRENT_TIMESTAMP, 'wechat', 'bound', 'D:/x/chat_a@chatroom.json', '{}', 'wechat', '2@a@chatroom')
        """
    )
    d = prune_wechat_group_artifacts(dry_run=True)
    assert d["interactions_to_delete"] == 1
    prune_wechat_group_artifacts(dry_run=False)
    n_null = fetch_one(
        "SELECT COUNT(*) AS c FROM interactions WHERE source_kind='wechat' AND person_id IS NULL",
        [],
    )
    n_keep = fetch_one(
        "SELECT COUNT(*) AS c FROM interactions WHERE source_kind='wechat' AND source_id LIKE '2@%'",
        [],
    )
    assert int(n_null["c"]) == 0
    assert int(n_keep["c"]) == 1


def test_sync_contacts_skips_chatroom_username(iso_db, tmp_path, monkeypatch) -> None:
    db = tmp_path / "contact.db"
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE contact (username, nick_name, remark, alias, delete_flag)")
    conn.execute("INSERT INTO contact VALUES ('gh_123@chatroom', 'GroupA', '', '', 0)")
    conn.execute("INSERT INTO contact VALUES ('wxid_real', 'Bob', '', '', 0)")
    conn.commit()
    conn.close()
    r = sync_contacts(tmp_path, contact_db=db, dry_run=False)
    assert r["status"] == "ok"
    rows = query("SELECT person_id, primary_name FROM persons ORDER BY primary_name")
    names = {str(x["primary_name"]) for x in rows}
    assert "GroupA" not in names
    assert "Bob" in names
