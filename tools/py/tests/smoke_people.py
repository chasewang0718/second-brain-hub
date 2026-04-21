"""
Non-destructive smoke tests for the People stack + iOS locate + cloud queue.

- Exposes pytest-compatible `test_*` functions (collected under tests/).
- Can still be invoked directly via `python tests/smoke_people.py` for a one-shot verdict.

No Ollama or network required; DuckDB writes go to the local telemetry DB.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_path() -> None:
    repo_py = Path(__file__).resolve().parents[1]
    src = str(repo_py / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


_bootstrap_path()

from brain_agents.cloud_queue import list_pending  # noqa: E402
from brain_agents.ios_backup_locator import locate_bundle  # noqa: E402
from brain_agents.people import overdue, seed_demo_people_data, who  # noqa: E402
from brain_cli.main import app  # noqa: E402
from typer.testing import CliRunner  # noqa: E402


def test_seed_demo_and_who_alice() -> None:
    seed_demo_people_data()
    rows = who("Alice")
    assert rows, "who Alice should hit demo seed"


def test_overdue_query_executes() -> None:
    seed_demo_people_data()
    result = overdue(days=365)
    assert isinstance(result, list)


def test_cloud_queue_list_returns_list() -> None:
    pend = list_pending(limit=5)
    assert isinstance(pend, list)


def test_ios_backup_locate_returns_dict() -> None:
    loc = locate_bundle()
    assert isinstance(loc, dict)
    assert {"whatsapp", "address_book"}.issubset(loc.keys())


def test_cli_cloud_queue_list_runs() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["cloud", "queue", "list"])
    assert r.exit_code == 0


def test_cli_who_via_runner() -> None:
    seed_demo_people_data()
    runner = CliRunner()
    r = runner.invoke(app, ["who", "Alice"])
    assert r.exit_code == 0
    assert "Alice" in (r.stdout or "")


def _run_all_as_script() -> int:
    test_seed_demo_and_who_alice()
    test_overdue_query_executes()
    test_cloud_queue_list_returns_list()
    test_ios_backup_locate_returns_dict()
    test_cli_cloud_queue_list_runs()
    test_cli_who_via_runner()

    rows = who("Alice")
    pend = list_pending(limit=5)
    loc = locate_bundle()
    print(
        "smoke_people_ok",
        {"who_rows": len(rows), "backup_locate_keys": list(loc.keys()), "pending_queue": len(pend)},
    )
    print(
        "\nManual smoke (human):\n"
        "- peopleA-13: brain wechat-sync -> brain who '<remark>' -> context-for-meeting\n"
        "- peopleA-18: contacts-ingest-ios + whatsapp-ingest-ios -> brain who (same phone)\n"
        "- peopleA-22: Caps+D paste with [people-note: Alice Zhang] -> text-inbox-ingest -> check person_notes\n",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_all_as_script())
