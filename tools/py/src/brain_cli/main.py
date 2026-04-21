"""Minimal Typer CLI for F1.0 bring-up."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from brain_core.config import load_paths_config, load_runtime_config
from brain_core.inbox import list_inbox
from brain_core.safety import (
    AutoCommitter,
    list_history,
    restore_agent,
    restore_last_clean,
    restore_to,
    safety_status,
)
from brain_core.telemetry import append_event, list_recent
from brain_agents.text_inbox import ingest_file as text_ingest_file
from brain_agents.file_inbox import ingest_pdf_inbox
from brain_agents.people import context_for_meeting, overdue, seed_demo_people_data, who
from brain_agents.digest import generate_daily_digest, generate_weekly_review
from brain_agents.structure import structure_history
from brain_agents.write_assist import write_draft
from brain_memory.vectors import (
    delete_markdown,
    rebuild_index,
    search as vector_search,
    upsert_markdown,
)
from brain_memory.memory import Memory
from brain_mcp.server import run_stdio

app = typer.Typer(help="second-brain-hub Python CLI")


@app.command("health")
def health_cmd() -> None:
    typer.echo("ok")


@app.command("paths")
def paths_cmd() -> None:
    typer.echo(json.dumps(load_paths_config(), ensure_ascii=False, indent=2))


@app.command("config")
def config_cmd() -> None:
    typer.echo(json.dumps(load_runtime_config(), ensure_ascii=False, indent=2))


@app.command("mcp-stdio")
def mcp_stdio_cmd() -> None:
    run_stdio()


@app.command("telemetry-append")
def telemetry_append_cmd(
    source: str = typer.Option(..., help="Event source, e.g. cli/mcp/ahk"),
    event: str = typer.Option(..., help="Event name"),
    detail_json: str = typer.Option("", help="JSON string detail payload"),
    detail_file: str = typer.Option("", help="Path to JSON file payload"),
) -> None:
    payload = detail_json
    if detail_file:
        payload = Path(detail_file).read_text(encoding="utf-8")
    elif not payload and not sys.stdin.isatty():
        payload = sys.stdin.read()
    if not payload.strip():
        payload = "{}"
    event_id = append_event(source=source, event=event, detail_json=payload)
    typer.echo(f"appended telemetry id={event_id}")


@app.command("telemetry-recent")
def telemetry_recent_cmd(limit: int = typer.Option(10, min=1, max=100)) -> None:
    typer.echo(json.dumps(list_recent(limit=limit), ensure_ascii=False, indent=2))


@app.command("inbox-list")
def inbox_list_cmd(limit: int = typer.Option(20, min=1, max=200)) -> None:
    typer.echo(json.dumps(list_inbox(limit=limit), ensure_ascii=False, indent=2))


@app.command("safety-status")
def safety_status_cmd() -> None:
    typer.echo(json.dumps(safety_status(), ensure_ascii=False, indent=2))


@app.command("history")
def history_cmd(
    limit: int = typer.Option(20, min=1, max=200),
    agent: str = typer.Option("", help="Filter by agent name in [agent:<name>] prefix"),
) -> None:
    typer.echo(json.dumps(list_history(limit=limit, agent=agent), ensure_ascii=False, indent=2))


@app.command("restore")
def restore_cmd(
    to: str = typer.Option("", help="Restore to a specific commit hash"),
    last_clean: bool = typer.Option(False, help="Restore to latest non-agent commit"),
    agent: str = typer.Option("", help="Restore latest contiguous commits for agent at HEAD"),
) -> None:
    mode_count = sum(1 for item in [bool(to), last_clean, bool(agent)] if item)
    if mode_count != 1:
        raise typer.BadParameter("Exactly one mode required: --to or --last-clean or --agent")
    if to:
        result = restore_to(to)
    elif last_clean:
        result = restore_last_clean()
    else:
        result = restore_agent(agent)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("agent-demo-commit")
def agent_demo_commit_cmd(
    agent: str = typer.Option("cursor", help="Agent name"),
    summary: str = typer.Option("demo write", help="Commit summary"),
) -> None:
    """Small helper for smoke tests of auto-commit behavior."""
    with AutoCommitter(agent=agent, summary=summary, actions=["smoke: touch marker file"]):
        marker = Path(load_paths_config()["paths"]["content_root"]) / "99-inbox" / ".agent-smoke-marker.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"updated by {agent}\n", encoding="utf-8")
    typer.echo("demo auto-commit done")


@app.command("ingest")
def ingest_cmd(limit: int = typer.Option(0, min=0, help="Limit number of markdown files")) -> None:
    result = rebuild_index(limit=limit)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("search")
def search_cmd(
    query: str = typer.Argument("", help="Semantic query text"),
    query_file: str = typer.Option("", help="Read UTF-8 query text from file"),
    limit: int = typer.Option(5, min=1, max=20),
) -> None:
    final_query = query
    if query_file:
        final_query = Path(query_file).read_text(encoding="utf-8")
    elif not final_query and not sys.stdin.isatty():
        final_query = sys.stdin.read()
    final_query = final_query.strip()
    if not final_query:
        raise typer.BadParameter("query is required (arg, --query-file, or stdin)")
    typer.echo(json.dumps(vector_search(query=final_query, limit=limit), ensure_ascii=False, indent=2))


@app.command("ask")
def ask_cmd(
    query: str = typer.Argument("", help="Ask query"),
    query_file: str = typer.Option("", help="Read UTF-8 query text from file"),
    limit: int = typer.Option(5, min=1, max=20),
) -> None:
    final_query = query
    if query_file:
        final_query = Path(query_file).read_text(encoding="utf-8")
    elif not final_query and not sys.stdin.isatty():
        final_query = sys.stdin.read()
    final_query = final_query.strip()
    if not final_query:
        raise typer.BadParameter("query is required (arg, --query-file, or stdin)")
    typer.echo(json.dumps(Memory().ask(query=final_query, limit=limit), ensure_ascii=False, indent=2))


class _MarkdownIndexHandler(FileSystemEventHandler):
    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event, deleted=False)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event, deleted=False)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._handle(event, deleted=True)

    def _handle(self, event: FileSystemEvent, deleted: bool) -> None:
        if event.is_directory:
            return
        src_path = str(event.src_path)
        if not src_path.lower().endswith(".md"):
            return
        if "\\.git\\" in src_path.lower():
            return
        result = delete_markdown(src_path) if deleted else upsert_markdown(src_path)
        typer.echo(json.dumps(result, ensure_ascii=False))


@app.command("watch")
def watch_cmd() -> None:
    content_root = Path(load_paths_config()["paths"]["content_root"])
    observer = Observer()
    handler = _MarkdownIndexHandler()
    observer.schedule(handler, str(content_root), recursive=True)
    observer.start()
    typer.echo(f"watching markdown changes under {content_root}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


@app.command("memory-bootstrap")
def memory_bootstrap_cmd() -> None:
    typer.echo(json.dumps(Memory().bootstrap(), ensure_ascii=False, indent=2))


@app.command("text-inbox-ingest")
def text_inbox_ingest_cmd(input_file: str = typer.Argument(..., help="Path to source markdown/text file")) -> None:
    result = text_ingest_file(input_file)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("pdf-inbox-ingest")
def pdf_inbox_ingest_cmd(limit: int = typer.Option(1, min=1, max=100, help="How many PDF files to process")) -> None:
    result = ingest_pdf_inbox(limit=limit)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("write")
def write_cmd(
    topic: str = typer.Option(..., help="Writing topic"),
    platform: str = typer.Option("default", help="Target platform, e.g. xiaohongshu/linkedin"),
    reader: str = typer.Option("general reader", help="Target reader persona"),
    source_limit: int = typer.Option(5, min=1, max=20),
) -> None:
    result = write_draft(topic=topic, platform=platform, reader=reader, source_limit=source_limit)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("people-seed-demo")
def people_seed_demo_cmd() -> None:
    typer.echo(json.dumps(seed_demo_people_data(), ensure_ascii=False, indent=2))


@app.command("who")
def who_cmd(name: str = typer.Argument(..., help="Name or alias")) -> None:
    typer.echo(json.dumps(who(name), ensure_ascii=False, indent=2, default=str))


@app.command("overdue")
def overdue_cmd(days: int = typer.Option(30, min=1, max=365)) -> None:
    typer.echo(json.dumps(overdue(days=days), ensure_ascii=False, indent=2, default=str))


@app.command("context-for-meeting")
def context_for_meeting_cmd(name: str = typer.Argument(..., help="Name or alias"), limit: int = typer.Option(5, min=1, max=20)) -> None:
    typer.echo(
        json.dumps(
            context_for_meeting(name_or_alias=name, limit=limit),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


@app.command("structure-history")
def structure_history_cmd(dry_run: bool = typer.Option(True, help="Run dry-run only (recommended)")) -> None:
    typer.echo(json.dumps(structure_history(dry_run=dry_run), ensure_ascii=False, indent=2))


@app.command("daily-digest")
def daily_digest_cmd() -> None:
    typer.echo(json.dumps(generate_daily_digest(), ensure_ascii=False, indent=2))


@app.command("weekly-review")
def weekly_review_cmd() -> None:
    typer.echo(json.dumps(generate_weekly_review(), ensure_ascii=False, indent=2))


def main() -> None:
    app()

