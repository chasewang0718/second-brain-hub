from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config


def _content_root() -> Path:
    return Path(load_paths_config()["paths"]["content_root"])


def _digest_dir() -> Path:
    p = _content_root() / "08-indexes" / "digests"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _append_journal(line: str) -> str:
    now = datetime.now(UTC)
    journal_dir = _content_root() / "04-journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    path = journal_dir / f"{now.date().isoformat()}.md"
    if not path.exists():
        path.write_text(
            "\n".join(
                [
                    "---",
                    f"date: {now.date().isoformat()}",
                    "type: journal",
                    "---",
                    "",
                    f"# Journal · {now.date().isoformat()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return str(path)


def main() -> int:
    now = datetime.now(UTC)
    dig = _digest_dir()
    gate = _read_json(dig / "v6-gate-report.json")
    hist = _read_jsonl(dig / "v6-gate-history.jsonl")
    if not gate:
        out = {"status": "skipped", "reason": "missing_v6_gate_report"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    a5 = int(((gate.get("a5") or {}).get("consecutive_days") or 0))
    e2 = int(((gate.get("e2") or {}).get("consecutive_days") or 0))
    ready = bool(gate.get("v6_ready"))
    prev_a5 = int(hist[-2].get("a5_consecutive_days") or 0) if len(hist) >= 2 else a5
    prev_e2 = int(hist[-2].get("e2_consecutive_days") or 0) if len(hist) >= 2 else e2

    broken = (a5 < prev_a5) or (e2 < prev_e2)
    status = "broken" if broken else "ok"
    tag = "[hub-gate]"
    line = (
        f"- {tag} status={status} ts={now.isoformat()} "
        f"a5={a5} (prev={prev_a5}) e2={e2} (prev={prev_e2}) v6_ready={str(ready).lower()}"
    )
    journal_path = _append_journal(line)
    out = {
        "status": "ok",
        "gate_status": status,
        "a5_consecutive_days": a5,
        "e2_consecutive_days": e2,
        "prev_a5_consecutive_days": prev_a5,
        "prev_e2_consecutive_days": prev_e2,
        "v6_ready": ready,
        "journal_path": journal_path,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

