from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path
import sys

from brain_core.config import load_paths_config


def _history_path() -> Path:
    content_root = Path(load_paths_config()["paths"]["content_root"])
    out_dir = content_root / "08-indexes" / "digests"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "people-eval-history.jsonl"


def main() -> int:
    tests_dir = Path(__file__).resolve().parents[1] / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))

    from eval_people import run_eval  # pylint: disable=import-error,import-outside-toplevel

    report = run_eval()
    now = datetime.now(UTC).isoformat()
    row = {
        "ts_utc": now,
        "status": report.get("status"),
        "total": report.get("total"),
        "passed": report.get("passed"),
        "failed": report.get("failed"),
        "report": report.get("report"),
    }
    path = _history_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "status": "ok",
                "history_path": str(path),
                "snapshot": {
                    "total": row["total"],
                    "passed": row["passed"],
                    "failed": row["failed"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
