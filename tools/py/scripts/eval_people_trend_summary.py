from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config


def _digest_dir() -> Path:
    content_root = Path(load_paths_config()["paths"]["content_root"])
    out_dir = content_root / "08-indexes" / "digests"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _history_path() -> Path:
    return _digest_dir() / "people-eval-history.jsonl"


def _summary_path() -> Path:
    return _digest_dir() / "people-eval-trend.md"


def _load_rows(limit: int = 12) -> list[dict[str, Any]]:
    path = _history_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows[-max(1, int(limit)) :]


def _render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# People Eval Trend",
        "",
        f"- History file: `{_history_path()}`",
    ]
    if not rows:
        lines.extend(["", "- No snapshots yet."])
        return "\n".join(lines)

    total_runs = len(rows)
    all_pass = sum(1 for r in rows if int(r.get("failed") or 0) == 0)
    pass_rate = round((all_pass / total_runs) * 100, 1)
    latest = rows[-1]
    lines.extend(
        [
            f"- Window runs: {total_runs}",
            f"- Fully green runs: {all_pass}/{total_runs} ({pass_rate}%)",
            f"- Latest: `{latest.get('ts_utc', '')}` · passed={latest.get('passed', 0)}/{latest.get('total', 0)} failed={latest.get('failed', 0)}",
            "",
            "## Recent Snapshots",
            "",
            "| ts_utc | passed/total | failed | status |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for r in reversed(rows):
        ts = str(r.get("ts_utc", ""))
        passed = int(r.get("passed") or 0)
        total = int(r.get("total") or 0)
        failed = int(r.get("failed") or 0)
        status = str(r.get("status") or "")
        lines.append(f"| {ts} | {passed}/{total} | {failed} | {status} |")
    return "\n".join(lines)


def main() -> int:
    rows = _load_rows(limit=12)
    md = _render(rows)
    out = _summary_path()
    out.write_text(md, encoding="utf-8")
    print(
        json.dumps(
            {"status": "ok", "summary_path": str(out), "rows_used": len(rows)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
