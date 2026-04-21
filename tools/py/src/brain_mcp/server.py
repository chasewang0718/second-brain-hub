"""FastMCP F1.0 stub tools: health, echo, paths."""

from __future__ import annotations

import json

from fastmcp import FastMCP

from brain_agents.ask import ask as ask_agent
from brain_agents.cloud_flush import flush as cloud_flush_run
from brain_agents.identity_resolver import parse_identifiers_repair_kinds, run_identifiers_repair
from brain_agents.merge_candidates import accept_candidate, list_candidates, reject_candidate
from brain_agents.people import context_for_meeting, context_for_meeting_markdown, overdue, who
from brain_core.config import load_paths_config
from brain_core.inbox import list_inbox
from brain_core.safety import list_history as list_git_history
from brain_core.safety import safety_status as get_safety_status
from brain_core.telemetry import append_event, list_recent
mcp = FastMCP(name="brain")


@mcp.tool
def health() -> dict[str, str]:
    return {"status": "ok", "service": "brain-mcp", "phase": "F1.0"}


@mcp.tool
def echo(text: str) -> dict[str, str]:
    return {"echo": text}


@mcp.tool
def paths() -> dict:
    return load_paths_config()


@mcp.tool
def telemetry_recent(limit: int = 10) -> list[dict]:
    return list_recent(limit=limit)


@mcp.tool
def telemetry_append(source: str, event: str, detail_json: str = "{}") -> dict:
    event_id = append_event(source=source, event=event, detail_json=detail_json)
    return {"id": event_id}


@mcp.tool
def inbox_list(limit: int = 20) -> list[dict]:
    rows = list_inbox(limit=limit)
    for row in rows:
        row["mtime"] = str(row["mtime"])
    return json.loads(json.dumps(rows, ensure_ascii=False))


@mcp.tool
def safety_status() -> dict:
    return get_safety_status()


@mcp.tool
def history(limit: int = 20, agent: str = "") -> list[dict]:
    return list_git_history(limit=limit, agent=agent)


@mcp.tool
def ask(query: str, limit: int = 5, mode: str = "auto") -> list[dict]:
    """mode: fast | auto | deep — same semantics as CLI ``brain ask --mode``."""
    rows = ask_agent(query=query, limit=limit, mode=mode)
    return json.loads(json.dumps(rows, ensure_ascii=False))


@mcp.tool
def who_tool(name: str) -> list[dict]:
    rows = who(name)
    return json.loads(json.dumps(rows, ensure_ascii=False, default=str))


@mcp.tool
def overdue_tool(days: int = 30, channel: str = "") -> list[dict]:
    """When channel is set (e.g. wechat), uses last interaction on that channel per person."""
    ch = channel.strip() or None
    rows = overdue(days=days, channel=ch)
    return json.loads(json.dumps(rows, ensure_ascii=False, default=str))


@mcp.tool
def context_for_meeting_tool(
    name: str,
    limit: int = 5,
    since_days: int = 0,
    output_format: str = "json",
) -> dict | str:
    """output_format: json | md — md returns Markdown text for pasting into notes."""
    payload = context_for_meeting(
        name_or_alias=name,
        limit=limit,
        since_days=since_days if since_days > 0 else None,
    )
    if output_format.strip().lower() == "md":
        return context_for_meeting_markdown(payload)
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


@mcp.tool
def merge_candidates_list_tool(status: str = "pending", limit: int = 50) -> list[dict]:
    """T3 identity merge queue. status: pending | accepted | rejected | all."""
    rows = list_candidates(status=status.strip().lower(), limit=limit)
    return json.loads(json.dumps(rows, ensure_ascii=False, default=str))


@mcp.tool
def merge_candidate_accept_tool(candidate_id: int, kept_person_id: str = "") -> dict:
    """Apply a pending merge_candidates row. Empty kept_person_id keeps lexicographically smaller person_id."""
    kp = kept_person_id.strip() or None
    return accept_candidate(candidate_id, kept_person_id=kp)


@mcp.tool
def merge_candidate_reject_tool(candidate_id: int) -> dict:
    """Reject a pending merge_candidates row without merging."""
    return reject_candidate(candidate_id)


@mcp.tool
def cloud_flush_preview() -> dict:
    """Same as ``brain cloud flush --dry-run``: build prompt stats without spawning cursor-agent."""
    return cloud_flush_run(dry_run=True)


@mcp.tool
def identifiers_repair_preview(kinds: str = "phone") -> dict:
    """Dry-run identifiers repair; kinds: phone, email, wxid, comma list, or all."""
    parsed = parse_identifiers_repair_kinds(kinds)
    if not parsed.get("ok"):
        return parsed
    return run_identifiers_repair(kinds=parsed["kinds"], dry_run=True)


def run_stdio() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()

