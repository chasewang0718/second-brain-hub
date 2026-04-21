"""FastMCP F1.0 stub tools: health, echo, paths."""

from __future__ import annotations

import json

from fastmcp import FastMCP

from brain_agents.ask import ask as ask_agent
from brain_agents.people import context_for_meeting, overdue, who
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
def overdue_tool(days: int = 30) -> list[dict]:
    rows = overdue(days=days)
    return json.loads(json.dumps(rows, ensure_ascii=False, default=str))


@mcp.tool
def context_for_meeting_tool(name: str, limit: int = 5) -> dict:
    rows = context_for_meeting(name_or_alias=name, limit=limit)
    return json.loads(json.dumps(rows, ensure_ascii=False, default=str))


def run_stdio() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()

