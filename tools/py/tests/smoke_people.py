"""
Non-destructive smoke: People stack + iOS locate + cloud queue (no Ollama required).

Run: cd tools/py && set PYTHONPATH=src && python tests/smoke_people.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    repo_py = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_py / "src"))

    from brain_agents.cloud_queue import list_pending
    from brain_agents.ios_backup_locator import locate_bundle
    from brain_agents.people import overdue, seed_demo_people_data, who
    from typer.testing import CliRunner

    from brain_cli.main import app

    seed_demo_people_data()
    rows = who("Alice")
    assert rows, "who Alice should hit demo seed"

    overdue(days=365)  # exercise query path

    pend = list_pending(limit=5)
    assert isinstance(pend, list)

    loc = locate_bundle()
    assert isinstance(loc, dict)

    runner = CliRunner()
    r = runner.invoke(app, ["cloud", "queue", "list"])
    assert r.exit_code == 0

    print(
        "smoke_people_ok",
        {"who_rows": len(rows), "backup_locate_keys": list(loc.keys()), "pending_queue": len(pend)},
    )

    print(
        "\nManual smoke (human):\n"
        "- peopleA-13: brain wechat-sync → brain who '<remark>' → context-for-meeting\n"
        "- peopleA-18: contacts-ingest-ios + whatsapp-ingest-ios → brain who (same phone)\n"
        "- peopleA-22: Caps+D paste with [people-note: Alice Zhang] → text-inbox-ingest → check person_notes\n",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
