"""CLI surface tests for hub's people / CRM commands (non-destructive)."""

from __future__ import annotations

import json

from brain_agents.people import seed_demo_people_data
from brain_cli.main import app
from typer.testing import CliRunner


def _run(args: list[str]) -> tuple[int, str]:
    r = CliRunner().invoke(app, args)
    return r.exit_code, r.stdout or ""


def test_health_ok() -> None:
    code, out = _run(["health"])
    assert code == 0 and out.strip() == "ok"


def test_overdue_channel_wechat_returns_json() -> None:
    seed_demo_people_data()
    code, out = _run(["overdue", "--days", "1", "--channel", "wechat"])
    assert code == 0
    data = json.loads(out)
    assert isinstance(data, list)
    if data:
        assert "days_since_channel_contact" in data[0]


def test_context_for_meeting_markdown_renders() -> None:
    seed_demo_people_data()
    code, out = _run(["context-for-meeting", "Alice", "--format", "md", "--since-days", "365"])
    assert code == 0
    assert "Meeting context" in out
    assert "Recent interactions" in out


def test_identifiers_repair_dry_run_default_phone() -> None:
    code, out = _run(["identifiers-repair", "--dry-run"])
    assert code == 0
    data = json.loads(out)
    assert data.get("status") == "dry_run"
    assert "results" in data and "phone" in data["results"]
    assert "rows_scanned" in data["results"]["phone"]
    assert "totals" in data


def test_identifiers_repair_all_kinds_dry_run() -> None:
    code, out = _run(["identifiers-repair", "--dry-run", "--kinds", "all"])
    assert code == 0
    data = json.loads(out)
    assert set(data["results"].keys()) >= {"phone", "email", "wxid"}


def test_merge_candidates_list_returns_json_array() -> None:
    code, out = _run(["merge-candidates", "list"])
    assert code == 0
    data = json.loads(out)
    assert isinstance(data, list)


def test_cloud_flush_dry_run_handles_empty_queue() -> None:
    code, out = _run(["cloud", "flush", "--dry-run"])
    assert code == 0
    data = json.loads(out)
    # With no pending tasks we expect 'empty'; with any queued tasks we expect dry_run / skipped.
    assert data.get("status") in {"empty", "dry_run", "skipped"}
