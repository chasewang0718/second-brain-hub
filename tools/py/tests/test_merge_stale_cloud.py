"""enqueue_stale_merge_candidates_for_cloud dry-run."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain_agents.merge_candidates import enqueue_stale_merge_candidates_for_cloud
from brain_memory.structured import ensure_schema, execute


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_DB_PATH", str(tmp_path / "m.duckdb"))
    ensure_schema()
    execute(
        """
        INSERT INTO merge_candidates (person_a, person_b, score, reason, status, detail_json)
        VALUES ('p_a', 'p_b', 0.5, 'test', 'pending', '{}')
        """
    )
    old = (datetime.now(UTC) - timedelta(days=30)).replace(tzinfo=None)
    execute("UPDATE merge_candidates SET created_at = ? WHERE person_a = 'p_a'", [old])
    return tmp_path


def test_enqueue_stale_dry_run_lists_old_pending(iso) -> None:
    out = enqueue_stale_merge_candidates_for_cloud(dry_run=True)
    assert out["status"] == "dry_run"
    assert out["enqueued"] >= 1
    assert len(out.get("sample") or []) >= 1
