from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from brain_agents.people import overdue
from brain_core.config import load_paths_config
from brain_memory.structured import query


def _digest_dir() -> Path:
    content_root = Path(load_paths_config()["paths"]["content_root"])
    out_dir = content_root / "08-indexes" / "digests"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _history_path() -> Path:
    return _digest_dir() / "relationship-deltas-history.jsonl"


def _report_path() -> Path:
    today = datetime.now(UTC).date().isoformat()
    return _digest_dir() / f"relationship-deltas-{today}.md"


def _load_last_snapshot() -> dict[str, Any] | None:
    p = _history_path()
    if not p.exists():
        return None
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        obj = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _build_snapshot() -> dict[str, Any]:
    overdue_rows = overdue(days=30)[:20]
    recent_rows = query(
        """
        WITH latest AS (
          SELECT person_id, MAX(ts_utc) AS last_ts
          FROM interactions
          GROUP BY person_id
        )
        SELECT p.person_id AS id, p.primary_name AS name, l.last_ts AS last_interaction_utc
        FROM latest l
        JOIN persons p ON p.person_id = l.person_id
        ORDER BY l.last_ts DESC
        LIMIT 20
        """
    )
    return {
        "ts_utc": datetime.now(UTC).isoformat(),
        "overdue": [
            {"id": r.get("id"), "name": r.get("name"), "days": int(r.get("days_since_contact") or 0)}
            for r in overdue_rows
        ],
        "recent": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "last_interaction_utc": (
                    r.get("last_interaction_utc").isoformat()
                    if hasattr(r.get("last_interaction_utc"), "isoformat")
                    else r.get("last_interaction_utc")
                ),
            }
            for r in recent_rows
        ],
    }


def _diff_overdue(prev: dict[str, Any] | None, curr: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prev_map: dict[str, int] = {}
    for r in (prev or {}).get("overdue", []) if prev else []:
        pid = str(r.get("id") or "")
        if pid:
            prev_map[pid] = int(r.get("days") or 0)

    new_overdue: list[dict[str, Any]] = []
    biggest_increase: list[dict[str, Any]] = []
    for r in curr.get("overdue", []):
        pid = str(r.get("id") or "")
        if not pid:
            continue
        days = int(r.get("days") or 0)
        old = prev_map.get(pid)
        if old is None:
            new_overdue.append(r)
            continue
        delta = days - old
        if delta > 0:
            biggest_increase.append({**r, "delta_days": delta})
    biggest_increase.sort(key=lambda x: int(x.get("delta_days") or 0), reverse=True)
    return new_overdue[:10], biggest_increase[:10]


def _render(prev: dict[str, Any] | None, curr: dict[str, Any]) -> str:
    new_overdue, biggest_increase = _diff_overdue(prev, curr)
    lines = [
        "# Relationship Deltas",
        "",
        f"- generated_utc: {curr.get('ts_utc')}",
        f"- snapshot_file: `{_history_path()}`",
        "",
        "## Newly Overdue (vs previous snapshot)",
    ]
    if new_overdue:
        for r in new_overdue:
            lines.append(f"- {r.get('name') or r.get('id')}: {r.get('days')} days")
    else:
        lines.append("- none")

    lines.extend(["", "## Biggest Overdue Increases", ""])
    if biggest_increase:
        for r in biggest_increase:
            lines.append(f"- {r.get('name') or r.get('id')}: +{r.get('delta_days')}d (now {r.get('days')}d)")
    else:
        lines.append("- none")

    lines.extend(["", "## Most Recent Interactions", ""])
    for r in curr.get("recent", [])[:10]:
        lines.append(f"- {r.get('name') or r.get('id')}: {r.get('last_interaction_utc')}")
    return "\n".join(lines)


def main() -> int:
    prev = _load_last_snapshot()
    curr = _build_snapshot()
    report = _render(prev, curr)

    hp = _history_path()
    with hp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(curr, ensure_ascii=False) + "\n")

    rp = _report_path()
    rp.write_text(report, encoding="utf-8")
    print(
        json.dumps(
            {"status": "ok", "history_path": str(hp), "report_path": str(rp)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
