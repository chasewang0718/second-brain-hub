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


def _v6_gate_snapshot() -> dict[str, Any] | None:
    path = _digest_dir() / "v6-gate-report.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def generate_daily_digest() -> dict[str, Any]:
    now = _today_utc()
    today = now.date().isoformat()
    target = _digest_dir() / f"daily-{today}.md"
    recent = _recent_markdown(limit=15)
    overdue_people = overdue(days=30)[:10]
    v6_gate = _v6_gate_snapshot() or {}
    a5_days = int(((v6_gate.get("a5") or {}).get("consecutive_days") or 0))
    e2_days = int(((v6_gate.get("e2") or {}).get("consecutive_days") or 0))
    v6_ready = bool(v6_gate.get("v6_ready"))
    lines = [
        "---",
        f"generated_utc: {now.isoformat()}",
        "type: daily-digest",
        "---",
        "",
        f"# Daily Digest · {today}",
        "",
        "## V6 Gate Status",
        f"- a5_consecutive_days: {a5_days}",
        f"- e2_consecutive_days: {e2_days}",
        f"- v6_ready: {str(v6_ready).lower()}",
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

    # --- A6 Sprint 2: Today's due + overdue commitments ---------------------
    # Uses open_threads.list_due() scoped by due_utc (NOT by sender dormancy
    # like `overdue()` above — these are different signals).
    from brain_agents.open_threads import _utc_now, list_due

    now_plain = _utc_now()
    day_end = now_plain.replace(hour=23, minute=59, second=59, microsecond=0)
    day_start = now_plain.replace(hour=0, minute=0, second=0, microsecond=0)

    # within_days=1 so list_due's horizon reaches through tomorrow morning;
    # then filter to strictly today — this covers the "due at 23:59 today"
    # edge case where list_due(within_days=0) would use horizon=wall_clock_now
    # and miss anything due later this same day.
    within_today = list_due(within_days=1, include_overdue=False, limit=50)
    due_today = [
        r for r in within_today
        if r.get("due_utc") and day_start <= r["due_utc"] <= day_end
    ]

    overdue_threads = [
        r for r in list_due(within_days=0, include_overdue=True, limit=100)
        if r.get("due_utc") and r["due_utc"] < day_start
    ]
    overdue_threads.sort(key=lambda r: r.get("due_utc"))  # oldest overdue first

    def _thread_line(r: dict[str, Any]) -> str:
        pid = str(r.get("person_id") or "")
        body = str(r.get("body") or r.get("summary") or "").strip().replace("\n", " ")
        due = r.get("due_utc")
        pby = str(r.get("promised_by") or "").strip()
        bits: list[str] = []
        if pby:
            bits.append(f"[{pby}]")
        bits.append(f"`{pid}`")
        bits.append(body[:100])
        if due:
            bits.append(f"(due {due})")
        return "- " + " ".join(bits)

    lines.extend(["", "## Today's Commitments"])
    if due_today:
        for r in due_today:
            lines.append(_thread_line(r))
    else:
        lines.append("- none")

    lines.extend(["", "## Overdue Commitments"])
    if overdue_threads:
        for r in overdue_threads[:20]:
            days_over = max(0, (day_start - r["due_utc"]).days)
            lines.append(_thread_line(r) + f"  · **{days_over}d overdue**")
    else:
        lines.append("- none")

    lines.extend(["", "## Next Action", "- Review top 3 updates and ping 1 overdue contact."])
    target.write_text("\n".join(lines), encoding="utf-8")
    return {
        "type": "daily",
        "path": str(target),
        "recent_count": len(recent[:10]),
        "overdue_count": len(overdue_people),
        "due_today_count": len(due_today),
        "overdue_commitments_count": len(overdue_threads),
        "v6_gate": {
            "a5_consecutive_days": a5_days,
            "e2_consecutive_days": e2_days,
            "v6_ready": v6_ready,
        },
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


def generate_relationship_alerts(days: int = 45) -> dict[str, Any]:
    """Produce the relationship-alerts digest.

    Phase A6 Sprint 4 made this tier-aware:
    - A ``## Tiered Cadence Alarm`` section groups overdue people by
      tier (inner/close/working/acquaintance), each with its own
      ``cadence_target_days`` from ``config/thresholds.yaml``.
    - The original ``## Overdue Contacts (>=Nd)`` section is kept as a
      flat baseline so untiered people aren't lost.
    """
    now = _today_utc()
    today = now.date().isoformat()
    target = _digest_dir() / f"relationship-alerts-{today}.md"
    threshold = max(1, int(days))
    flat_rows = overdue(days=threshold)[:30]

    by_tier: dict[str, list[dict[str, Any]]] = {}
    cadence: dict[str, int | None] = {}
    try:
        from brain_agents.relationship_tier import list_overdue_by_tier, load_cadence_config

        cadence = load_cadence_config()
        by_tier = list_overdue_by_tier(cadence=cadence)
    except Exception:  # pragma: no cover - defensive, digest must never crash
        by_tier = {}
        cadence = {}
    tiered_total = sum(len(v) for v in by_tier.values())

    lines = [
        "---",
        f"generated_utc: {now.isoformat()}",
        "type: relationship-alerts",
        f"threshold_days: {threshold}",
        f"tiered_overdue: {tiered_total}",
        "---",
        "",
        f"# Relationship Alerts · {today}",
        "",
        "## Tiered Cadence Alarm",
    ]
    if tiered_total == 0:
        lines.append("- none (nobody with a `relationship_tier` fact has exceeded their cadence target)")
    else:
        # Render tier sections in a stable, prioritized order.
        priority = ("inner", "close", "working", "acquaintance", "dormant")
        for tier_name in priority:
            rows = by_tier.get(tier_name) or []
            if not rows:
                continue
            target_days = cadence.get(tier_name)
            label = f"{tier_name} (cadence {target_days}d)" if target_days is not None else tier_name
            lines.append("")
            lines.append(f"### `{label}` · {len(rows)} overdue")
            lines.append("")
            lines.append("| name | person_id | dormancy | over target | last seen |")
            lines.append("| --- | --- | --- | --- | --- |")
            for r in rows[:25]:
                nm = str(r.get("primary_name") or "").replace("|", "\\|") or "(unnamed)"
                pid = str(r.get("person_id") or "")
                dormancy = r.get("dormancy_days")
                over = r.get("days_overdue")
                last = str(r.get("last_seen_utc") or "")
                lines.append(f"| {nm} | `{pid}` | {dormancy}d | +{over}d | {last} |")

    lines.extend([
        "",
        f"## Overdue Contacts (>={threshold}d, flat baseline)",
    ])
    if flat_rows:
        for r in flat_rows:
            name = r.get("name", r.get("id"))
            gap = r.get("days_since_contact", r.get("days_since_channel_contact", "?"))
            lines.append(f"- {name}: {gap} days")
    else:
        lines.append("- none")
    lines.extend(["", "## Suggested Action", "- Pick top 3 people and send a quick catch-up message."])
    target.write_text("\n".join(lines), encoding="utf-8")
    return {
        "type": "relationship-alerts",
        "path": str(target),
        "threshold_days": threshold,
        "alert_count": len(flat_rows),
        "tiered_overdue": tiered_total,
        "tiered_by_tier": {k: len(v) for k, v in by_tier.items()},
    }


def generate_budget_tracker() -> dict[str, Any]:
    now = _today_utc()
    today = now.date().isoformat()
    target = _digest_dir() / f"budget-{today}.md"
    events = list_recent(limit=1000)
    cursor_events = [e for e in events if "cursor" in str(e.get("source", "")).lower()]
    lines = [
        "---",
        f"generated_utc: {now.isoformat()}",
        "type: budget-tracker",
        "---",
        "",
        f"# Budget Tracker · {today}",
        "",
        "## Cursor Usage Proxy (telemetry source contains 'cursor')",
        f"- events_seen: {len(cursor_events)} (recent window=1000)",
        "",
        "## Power Cost (manual)",
        "- Fill kWh and local tariff manually if you need exact hardware cost.",
        "",
        "## Notes",
        "- This is a lightweight placeholder metric until a dedicated usage meter is wired.",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    return {"type": "budget-tracker", "path": str(target), "cursor_events_seen": len(cursor_events)}

