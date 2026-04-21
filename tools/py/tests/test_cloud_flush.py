"""Integration tests for cloud_flush dry-run (no cursor-agent spawn in success path)."""

from __future__ import annotations

from pathlib import Path

from brain_agents.cloud_flush import flush
from brain_agents.cloud_queue import drop, enqueue
from brain_core.config import load_paths_config


def test_flush_dry_run_includes_tasks_when_queue_non_empty() -> None:
    root = Path(load_paths_config()["paths"]["content_root"]).resolve()
    lock = root / ".brain-autotrigger.lock"
    lock.unlink(missing_ok=True)

    en = enqueue("capsd-note-hard", {"smoke": True, "n": 1})
    qid = en.get("cloud_queue_id")
    assert qid is not None
    try:
        r = flush(dry_run=True)
        assert r["status"] in ("dry_run", "skipped")
        assert "tasks" in r or "overview" in r
        if r["status"] == "dry_run":
            assert int(r.get("prompt_chars") or 0) > 50
            tasks = r.get("tasks") or []
            assert len(tasks) >= 1
            assert any("capsd-note-hard" in str(t.get("task_kind", "")) for t in tasks)
        if r["status"] == "skipped" and r.get("reason") == "cursor_agent_missing":
            ov = r.get("overview") or []
            assert len(ov) >= 1
    finally:
        drop(int(qid))
