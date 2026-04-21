"""E2 MVP proactive digest generators."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
import json
from pathlib import Path
from typing import Any

from brain_agents.people import overdue
from brain_core.config import load_paths_config
from brain_core.telemetry import list_recent


def _content_root() -> Path:
    return Path(load_paths_config()["paths"]["content_root"])


def _digest_dir() -> Path:
    path = _content_root() / "08-indexes" / "digests"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _recent_markdown(limit: int = 20) -> list[Path]:
    files = sorted(_content_root().rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def _today_utc() -> datetime:
    return datetime.now(UTC)


def generate_daily_digest() -> dict[str, Any]:
    now = _today_utc()
    today = now.date().isoformat()
    target = _digest_dir() / f"daily-{today}.md"
    recent = _recent_markdown(limit=15)
    overdue_people = overdue(days=30)[:10]
    lines = [
        "---",
        f"generated_utc: {now.isoformat()}",
        "type: daily-digest",
        "---",
        "",
        f"# Daily Digest · {today}",
        "",
        "## Recent Markdown Updates",
    ]
    for path in recent[:10]:
        rel = path.relative_to(_content_root())
        lines.append(f"- `{rel}`")
    lines.extend(["", "## Overdue Contacts (>=30d)"])
    if overdue_people:
        for row in overdue_people:
            lines.append(f"- {row.get('name', row.get('id'))}: {row.get('days_since_contact', '?')} days")
    else:
        lines.append("- none")
    lines.extend(["", "## Next Action", "- Review top 3 updates and ping 1 overdue contact."])
    target.write_text("\n".join(lines), encoding="utf-8")
    return {
        "type": "daily",
        "path": str(target),
        "recent_count": len(recent[:10]),
        "overdue_count": len(overdue_people),
    }


def generate_weekly_review() -> dict[str, Any]:
    now = _today_utc()
    week_tag = f"{now.year}-W{now.isocalendar().week:02d}"
    target = _digest_dir() / f"weekly-{week_tag}.md"
    cutoff = now - timedelta(days=7)
    recent = [p for p in _recent_markdown(limit=300) if datetime.fromtimestamp(p.stat().st_mtime, UTC) >= cutoff]
    events = list_recent(limit=200)
    event_counts: dict[str, int] = {}
    for event in events:
        key = f"{event.get('source')}::{event.get('event')}"
        event_counts[key] = event_counts.get(key, 0) + 1
    lines = [
        "---",
        f"generated_utc: {now.isoformat()}",
        "type: weekly-review",
        "---",
        "",
        f"# Weekly Review · {week_tag}",
        "",
        f"- Markdown updates (7d): {len(recent)}",
        "",
        "## Most Active Event Types",
    ]
    ranked = sorted(event_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    if ranked:
        for key, count in ranked:
            lines.append(f"- {key}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "## Sample Updated Files"])
    for path in recent[:10]:
        rel = path.relative_to(_content_root())
        lines.append(f"- `{rel}`")
    lines.extend(["", "## Weekly Focus", "- Close pending backlog housekeeping and review structure dry-run suggestions."])
    target.write_text("\n".join(lines), encoding="utf-8")
    return {"type": "weekly", "path": str(target), "updated_files_7d": len(recent), "event_types": ranked}

