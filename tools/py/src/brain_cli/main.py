"""Minimal Typer CLI for F1.0 bring-up."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import typer
from brain_core.config import load_paths_config, load_runtime_config

app = typer.Typer(help="second-brain-hub Python CLI")

cloud_app = typer.Typer(help="Cloud offload queue (manual brain cloud flush)")
queue_app = typer.Typer(help="Inspect pending cloud_queue rows")
cloud_app.add_typer(queue_app, name="queue")
app.add_typer(cloud_app, name="cloud")

merge_candidates_app = typer.Typer(help="T3 identity merge queue (manual review)")
app.add_typer(merge_candidates_app, name="merge-candidates")

facts_app = typer.Typer(help="Bi-temporal person facts (Phase A6)")
app.add_typer(facts_app, name="facts")

person_metrics_app = typer.Typer(help="Derived person_metrics (Phase A6)")
app.add_typer(person_metrics_app, name="person-metrics")

thread_app = typer.Typer(help="Open threads / commitments (Phase A6 Sprint 2)")
app.add_typer(thread_app, name="thread")

person_digest_app = typer.Typer(help="Rolling topics / weekly digest (Phase A6 Sprint 3)")
app.add_typer(person_digest_app, name="person-digest")

tier_app = typer.Typer(help="Relationship tier + cadence alarm (Phase A6 Sprint 4)")
app.add_typer(tier_app, name="tier")


def _ensure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


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
    from brain_mcp.server import run_stdio

    run_stdio()


@app.command("telemetry-append")
def telemetry_append_cmd(
    source: str = typer.Option(..., help="Event source, e.g. cli/mcp/ahk"),
    event: str = typer.Option(..., help="Event name"),
    detail_json: str = typer.Option("", help="JSON string detail payload"),
    detail_file: str = typer.Option("", help="Path to JSON file payload"),
) -> None:
    from brain_core.telemetry import append_event

    payload = detail_json
    if detail_file:
        payload = Path(detail_file).read_text(encoding="utf-8")
    elif not payload and not sys.stdin.isatty():
        payload = sys.stdin.read()
    if not payload.strip():
        payload = "{}"
    try:
        event_id = append_event(source=source, event=event, detail_json=payload)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(
            f"detail_json is not valid JSON ({exc}); use --detail-file or pipe JSON via stdin to avoid PowerShell escaping issues."
        ) from exc
    typer.echo(f"appended telemetry id={event_id}")


@app.command("telemetry-recent")
def telemetry_recent_cmd(limit: int = typer.Option(10, min=1, max=100)) -> None:
    from brain_core.telemetry import list_recent

    typer.echo(json.dumps(list_recent(limit=limit), ensure_ascii=False, indent=2))


@app.command("inbox-list")
def inbox_list_cmd(limit: int = typer.Option(20, min=1, max=200)) -> None:
    from brain_core.inbox import list_inbox

    typer.echo(json.dumps(list_inbox(limit=limit), ensure_ascii=False, indent=2))


@app.command("safety-status")
def safety_status_cmd() -> None:
    from brain_core.safety import safety_status

    typer.echo(json.dumps(safety_status(), ensure_ascii=False, indent=2))


@app.command("history")
def history_cmd(
    limit: int = typer.Option(20, min=1, max=200),
    agent: str = typer.Option("", help="Filter by agent name in [agent:<name>] prefix"),
) -> None:
    from brain_core.safety import list_history

    typer.echo(json.dumps(list_history(limit=limit, agent=agent), ensure_ascii=False, indent=2))


@app.command("restore")
def restore_cmd(
    to: str = typer.Option("", help="Restore to a specific commit hash"),
    last_clean: bool = typer.Option(False, help="Restore to latest non-agent commit"),
    agent: str = typer.Option("", help="Restore latest contiguous commits for agent at HEAD"),
) -> None:
    from brain_core.safety import restore_agent, restore_last_clean, restore_to

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
    from brain_core.safety import AutoCommitter

    with AutoCommitter(agent=agent, summary=summary, actions=["smoke: touch marker file"]):
        marker = Path(load_paths_config()["paths"]["content_root"]) / "99-inbox" / ".agent-smoke-marker.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"updated by {agent}\n", encoding="utf-8")
    typer.echo("demo auto-commit done")


@app.command("ingest")
def ingest_cmd(limit: int = typer.Option(0, min=0, help="Limit number of markdown files")) -> None:
    from brain_memory.vectors import rebuild_index

    result = rebuild_index(limit=limit)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("search")
def search_cmd(
    query: str = typer.Argument("", help="Semantic query text"),
    query_file: str = typer.Option("", help="Read UTF-8 query text from file"),
    limit: int = typer.Option(5, min=1, max=20),
) -> None:
    from brain_memory.vectors import search as vector_search

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
    mode: str = typer.Option("fast", help="ask mode: fast|auto|deep (default fast for responsive CLI)"),
) -> None:
    from brain_agents.ask import ask as ask_engine

    final_query = query
    if query_file:
        final_query = Path(query_file).read_text(encoding="utf-8")
    elif not final_query and not sys.stdin.isatty():
        final_query = sys.stdin.read()
    final_query = final_query.strip()
    if not final_query:
        raise typer.BadParameter("query is required (arg, --query-file, or stdin)")
    if mode.lower().strip() not in {"auto", "fast", "deep"}:
        raise typer.BadParameter("mode must be one of: auto, fast, deep")
    typer.echo(json.dumps(ask_engine(query=final_query, limit=limit, mode=mode), ensure_ascii=False, indent=2))


@app.command("watch")
def watch_cmd() -> None:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
    from brain_memory.vectors import delete_markdown, upsert_markdown

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
    from brain_memory.memory import Memory

    typer.echo(json.dumps(Memory().bootstrap(), ensure_ascii=False, indent=2))


@app.command("text-inbox-ingest")
def text_inbox_ingest_cmd(input_file: str = typer.Argument(..., help="Path to source markdown/text file")) -> None:
    from brain_agents.text_inbox import ingest_file as text_ingest_file

    result = text_ingest_file(input_file)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("pdf-inbox-ingest")
def pdf_inbox_ingest_cmd(
    limit: int = typer.Option(1, min=1, max=100, help="How many PDF files to process"),
    paths: list[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="Explicit PDF path to ingest (repeatable). External files are copied into pdf_inbox_dir before processing.",
    ),
    no_copy: bool = typer.Option(
        False,
        "--no-copy",
        help="When using --path, process the file in place instead of copying it into pdf_inbox_dir.",
    ),
) -> None:
    from brain_agents.file_inbox import ingest_pdf_inbox, ingest_pdf_paths

    if paths:
        result = ingest_pdf_paths(paths, copy_into_inbox=not no_copy)
    else:
        result = ingest_pdf_inbox(limit=limit)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("image-inbox-ingest")
def image_inbox_ingest_cmd(
    limit: int = typer.Option(1, min=1, max=100, help="How many image files to process"),
    paths: list[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="Explicit image path to ingest (repeatable). External files are copied into image_inbox_dir before processing.",
    ),
    no_copy: bool = typer.Option(
        False,
        "--no-copy",
        help="When using --path, process the file in place instead of copying it into image_inbox_dir.",
    ),
) -> None:
    from brain_agents.image_inbox import ingest_image_inbox, ingest_image_paths

    if paths:
        result = ingest_image_paths(paths, copy_into_inbox=not no_copy)
    else:
        result = ingest_image_inbox(limit=limit)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("graph-build")
def graph_build_cmd() -> None:
    from brain_agents.graph_build import build_graph

    try:
        stats = build_graph()
    except RuntimeError as exc:
        typer.echo(json.dumps({"status": "skipped", "reason": str(exc)}, ensure_ascii=False))
        raise typer.Exit(1)
    typer.echo(json.dumps({"status": "ok", **stats}, ensure_ascii=False, indent=2, default=str))


@app.command("graph-rebuild-if-stale")
def graph_rebuild_if_stale_cmd(
    max_age_hours: float = typer.Option(
        0.0,
        "--max-age-hours",
        min=0.0,
        help="Force rebuild when Kuzu is older than this, even if DuckDB hasn't changed. 0 disables the wall-clock check.",
    ),
    force: bool = typer.Option(False, "--force", help="Rebuild even if the view is fresh"),
) -> None:
    """Rebuild Kuzu only when DuckDB is newer (or the view is missing /
    forced / older than ``--max-age-hours``). Cheap ``fresh`` path is a
    few ms of mtime stat calls; real rebuild takes several seconds.
    """
    from brain_agents.graph_build import rebuild_if_stale

    max_s = int(max_age_hours * 3600) if max_age_hours > 0 else None
    out = rebuild_if_stale(max_age_seconds=max_s, force=force)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("graph-staleness")
def graph_staleness_cmd(
    max_age_hours: float = typer.Option(0.0, "--max-age-hours", min=0.0),
) -> None:
    """Return only the staleness diagnostic (no rebuild). Useful for
    monitoring / Task Scheduler pre-checks.
    """
    from brain_agents.graph_build import graph_staleness

    max_s = int(max_age_hours * 3600) if max_age_hours > 0 else None
    typer.echo(json.dumps(graph_staleness(max_age_seconds=max_s), ensure_ascii=False, indent=2, default=str))


@app.command("graph-fof")
def graph_fof_cmd(
    person_id: str = typer.Argument(..., help="Anchor person_id"),
    limit: int = typer.Option(10, min=1, max=200),
) -> None:
    from brain_agents.graph_query import fof

    try:
        out = fof(person_id, limit=limit)
    except RuntimeError as exc:
        typer.echo(json.dumps({"status": "skipped", "reason": str(exc)}, ensure_ascii=False))
        raise typer.Exit(1)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("graph-shared-identifier")
def graph_shared_identifier_cmd(
    person_id: str = typer.Argument(..., help="Anchor person_id"),
    limit: int = typer.Option(20, min=1, max=200),
) -> None:
    from brain_agents.graph_query import shared_identifier

    try:
        out = shared_identifier(person_id, limit=limit)
    except RuntimeError as exc:
        typer.echo(json.dumps({"status": "skipped", "reason": str(exc)}, ensure_ascii=False))
        raise typer.Exit(1)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("graph-stats")
def graph_stats_cmd() -> None:
    from brain_agents.graph_query import stats as graph_stats

    try:
        out = graph_stats()
    except RuntimeError as exc:
        typer.echo(json.dumps({"status": "skipped", "reason": str(exc)}, ensure_ascii=False))
        raise typer.Exit(1)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("audio-inbox-ingest")
def audio_inbox_ingest_cmd(
    limit: int = typer.Option(1, min=1, max=100, help="How many audio files to process"),
    paths: list[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="Explicit audio path to ingest (repeatable). External files are copied into audio_inbox_dir before processing.",
    ),
    no_copy: bool = typer.Option(
        False,
        "--no-copy",
        help="When using --path, process the file in place instead of copying it into audio_inbox_dir.",
    ),
) -> None:
    from brain_agents.audio_inbox import ingest_audio_inbox, ingest_audio_paths

    if paths:
        result = ingest_audio_paths(paths, copy_into_inbox=not no_copy)
    else:
        result = ingest_audio_inbox(limit=limit)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("write")
def write_cmd(
    topic: str = typer.Option(..., help="Writing topic"),
    platform: str = typer.Option("default", help="Target platform, e.g. xiaohongshu/linkedin"),
    reader: str = typer.Option("general reader", help="Target reader persona"),
    source_limit: int = typer.Option(5, "--source-limit", "--limit", min=1, max=20),
    engine: str = typer.Option(
        "llm",
        "--engine",
        help="llm (default; Ollama, BRAIN_WRITE_MODEL, OLLAMA_HOST) or template",
    ),
) -> None:
    from brain_agents.write_assist import write_draft

    result = write_draft(
        topic=topic,
        platform=platform,
        reader=reader,
        source_limit=source_limit,
        engine=engine,
    )
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("people-seed-demo")
def people_seed_demo_cmd() -> None:
    from brain_agents.people import seed_demo_people_data

    typer.echo(json.dumps(seed_demo_people_data(), ensure_ascii=False, indent=2))


@app.command("identifiers-repair")
def identifiers_repair_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; no DuckDB writes"),
    kinds: str = typer.Option(
        "phone",
        "--kinds",
        help="Comma-separated: phone, email, wxid, or all (default: phone). Email includes gmail_addr.",
    ),
) -> None:
    from brain_agents.identity_resolver import parse_identifiers_repair_kinds, run_identifiers_repair

    parsed = parse_identifiers_repair_kinds(kinds)
    if not parsed.get("ok"):
        typer.echo(json.dumps({"status": "error", **{k: v for k, v in parsed.items() if k != "ok"}}, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)
    rep = run_identifiers_repair(kinds=parsed["kinds"], dry_run=dry_run)
    if rep.get("status") == "error":
        raise typer.Exit(code=1)
    typer.echo(json.dumps(rep, ensure_ascii=False, indent=2, default=str))


@app.command("who")
def who_cmd(name: str = typer.Argument(..., help="Name or alias")) -> None:
    from brain_agents.people import who

    typer.echo(json.dumps(who(name), ensure_ascii=False, indent=2, default=str))


@app.command("overdue")
def overdue_cmd(
    days: int = typer.Option(30, min=1, max=365),
    channel: str = typer.Option("", "--channel", "-c", help="Filter by last interaction on this channel (e.g. wechat)"),
) -> None:
    from brain_agents.people import overdue

    ch = channel.strip() or None
    typer.echo(json.dumps(overdue(days=days, channel=ch), ensure_ascii=False, indent=2, default=str))


@app.command("context-for-meeting")
def context_for_meeting_cmd(
    name: str = typer.Argument(..., help="Name or alias"),
    limit: int = typer.Option(5, min=1, max=20),
    since_days: int = typer.Option(0, "--since-days", min=0, max=3650, help="Only interactions newer than N days (0 = all)"),
    fmt: str = typer.Option("json", "--format", "-f", help="json or md"),
) -> None:
    from brain_agents.people import context_for_meeting, context_for_meeting_markdown

    payload = context_for_meeting(
        name_or_alias=name,
        limit=limit,
        since_days=since_days if since_days > 0 else None,
    )
    if fmt.strip().lower() == "md":
        typer.echo(context_for_meeting_markdown(payload))
        return
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("people-render")
def people_render_cmd(
    who: str = typer.Option("", "--who", help="Primary name or alias (first match)"),
    person_id: str = typer.Option("", "--person-id", help="Render exactly this person_id"),
    all_people: bool = typer.Option(False, "--all", help="Render cards for many persons into 06-people/by-person/"),
    since_days: int = typer.Option(
        90,
        "--since-days",
        min=0,
        max=3650,
        help="With --all: only persons with an interaction on or after now-N days (0 = no time filter)",
    ),
    channel: str = typer.Option("", "--channel", "-c", help="With --all: optional channel filter (e.g. wechat, whatsapp)"),
    limit: int = typer.Option(500, "--limit", min=1, max=20000, help="Max persons when using --all"),
    interaction_limit: int = typer.Option(25, "--interaction-limit", min=1, max=200),
    interaction_since_days: int = typer.Option(
        0,
        "--interaction-since-days",
        min=0,
        max=3650,
        help="Limit interaction rows to this window (0 = use defaults: unlimited for --who/--person-id; match --since-days for --all)",
    ),
    graph_hints: bool = typer.Option(False, "--graph-hints", help="Include Kuzu shared-identifier section (single person only)"),
    facts_history: bool = typer.Option(False, "--facts-history", help="Expand person_facts history table below current facts"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report only; do not write files"),
) -> None:
    from brain_agents.people_render import run_people_render

    modes = sum([bool(who.strip()), bool(person_id.strip()), all_people])
    if modes != 1:
        typer.echo(
            json.dumps(
                {"status": "error", "reason": "specify exactly one of: --who, --person-id, --all"},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1)
    isd = interaction_since_days if interaction_since_days > 0 else None
    out = run_people_render(
        who=who.strip() or None,
        person_id=person_id.strip() or None,
        all_people=all_people,
        since_days=since_days,
        channel=channel.strip() or None,
        limit=limit,
        interaction_limit=interaction_limit,
        interaction_since_days=isd,
        graph_hints=graph_hints,
        facts_history=facts_history,
        dry_run=dry_run,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("people-insights-refresh")
def people_insights_refresh_cmd(
    person_id: str = typer.Option("", "--person-id", help="Refresh one specific person_id"),
    name: str = typer.Option("", "--name", help="Refresh by name/alias (may match multiple people)"),
    limit: int = typer.Option(50, "--limit", min=5, max=200, help="Recent interactions per person"),
    since_days: int = typer.Option(90, "--since-days", min=1, max=3650, help="Only interactions within N days"),
) -> None:
    from brain_agents.people_insights import refresh_people_insights

    out = refresh_people_insights(
        person_id=person_id or None,
        name=name or None,
        limit=limit,
        since_days=since_days,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@merge_candidates_app.command("list")
def merge_candidates_list_cmd(
    status: str = typer.Option("pending", "--status", help="pending | accepted | rejected | all"),
    limit: int = typer.Option(50, min=1, max=500),
) -> None:
    from brain_agents.merge_candidates import list_candidates

    rows = list_candidates(status=status.strip().lower(), limit=limit)
    typer.echo(json.dumps(rows, ensure_ascii=False, indent=2, default=str))


@merge_candidates_app.command("accept")
def merge_candidates_accept_cmd(
    candidate_id: int = typer.Argument(..., help="merge_candidates.id"),
    keep: str = typer.Option("", "--keep", help="person_id to retain (default: lexicographically smaller of the pair)"),
) -> None:
    from brain_agents.merge_candidates import accept_candidate

    kp = keep.strip() or None
    typer.echo(json.dumps(accept_candidate(candidate_id, kept_person_id=kp), ensure_ascii=False, indent=2, default=str))


@merge_candidates_app.command("reject")
def merge_candidates_reject_cmd(candidate_id: int = typer.Argument(..., help="merge_candidates.id")) -> None:
    from brain_agents.merge_candidates import reject_candidate

    typer.echo(json.dumps(reject_candidate(candidate_id), ensure_ascii=False, indent=2, default=str))


@facts_app.command("add")
def facts_add_cmd(
    person_id: str = typer.Argument(..., help="Target person_id"),
    key: str = typer.Argument(..., help="Fact key, e.g. residence / role / employer"),
    value: str = typer.Argument("", help="String value (JSON-encoded on write). Omit when using --value-json."),
    value_json: str = typer.Option("", "--value-json", help="Raw JSON payload (takes precedence over positional value)"),
    confidence: float = typer.Option(1.0, "--confidence", min=0.0, max=1.0),
    source_kind: str = typer.Option("manual", "--source-kind", help="manual | capsd | wechat | derived | ..."),
    source_interaction_id: int = typer.Option(0, "--source-interaction-id", min=0),
    valid_from: str = typer.Option(
        "",
        "--valid-from",
        help="ISO datetime for valid_from (default = now UTC). Use to backfill history, e.g. '2024-01-15T00:00:00'",
    ),
    force: bool = typer.Option(False, "--force", help="Write even if the current fact is identical"),
) -> None:
    from datetime import datetime as _dt

    from brain_agents.person_facts import add_fact

    vj = value_json.strip() or None
    val: Any = None if vj else value

    vf_dt = None
    if valid_from.strip():
        try:
            vf_dt = _dt.fromisoformat(valid_from.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            typer.echo(json.dumps({"status": "error", "reason": f"bad --valid-from: {exc}"}, ensure_ascii=False, indent=2))
            raise typer.Exit(code=1) from exc

    out = add_fact(
        person_id=person_id,
        key=key,
        value=val,
        value_json=vj,
        confidence=confidence,
        source_kind=source_kind,
        source_interaction_id=source_interaction_id or None,
        valid_from=vf_dt,
        force=force,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@facts_app.command("list")
def facts_list_cmd(
    person_id: str = typer.Argument(..., help="Target person_id"),
    at: str = typer.Option("", "--at", help="ISO UTC datetime for bi-temporal query (empty = currently valid)"),
    history: bool = typer.Option(False, "--history", help="Return full history (overrides --at)"),
    key: str = typer.Option("", "--key", help="Filter by fact key"),
) -> None:
    from datetime import datetime as _dt

    from brain_agents.person_facts import list_facts

    at_dt = None
    if at.strip():
        try:
            at_dt = _dt.fromisoformat(at.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            typer.echo(json.dumps({"status": "error", "reason": f"bad --at: {exc}"}, ensure_ascii=False, indent=2))
            raise typer.Exit(code=1) from exc
    rows = list_facts(
        person_id,
        at=at_dt,
        include_history=history,
        key=(key.strip() or None),
    )
    typer.echo(json.dumps(rows, ensure_ascii=False, indent=2, default=str))


@facts_app.command("invalidate")
def facts_invalidate_cmd(
    fact_id: int = typer.Argument(..., help="person_facts.id to close"),
    reason: str = typer.Option("", "--reason", help="Advisory note (not persisted)"),
) -> None:
    from brain_agents.person_facts import invalidate_fact

    typer.echo(json.dumps(invalidate_fact(fact_id, reason=reason), ensure_ascii=False, indent=2, default=str))


@person_metrics_app.command("recompute")
def person_metrics_recompute_cmd(
    person_id: str = typer.Option("", "--person-id", help="Recompute for a single person"),
    all_flag: bool = typer.Option(False, "--all", help="Recompute for every person with interactions"),
    no_remove_orphans: bool = typer.Option(
        False,
        "--no-remove-orphans",
        help="(with --all) keep rows whose person_id no longer appears in interactions",
    ),
) -> None:
    from brain_agents.person_metrics import recompute_all, recompute_one

    pid = person_id.strip()
    if all_flag and pid:
        typer.echo(json.dumps({"status": "error", "reason": "use --all OR --person-id, not both"}, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)
    if not all_flag and not pid:
        typer.echo(json.dumps({"status": "error", "reason": "specify --all or --person-id"}, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)
    if all_flag:
        out = recompute_all(remove_orphans=not no_remove_orphans)
    else:
        out = recompute_one(pid)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@person_metrics_app.command("show")
def person_metrics_show_cmd(person_id: str = typer.Argument(..., help="Target person_id")) -> None:
    from brain_agents.person_metrics import get_metrics

    out = get_metrics(person_id)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


# --- Phase A6 Sprint 2 · open threads / commitments --------------------------


@thread_app.command("add")
def thread_add_cmd(
    person_id: str = typer.Argument(..., help="Target person_id"),
    body: str = typer.Argument(..., help="Commitment text (e.g. '下周三寄书')"),
    due: str = typer.Option("", "--due", help="ISO datetime or date ('2026-05-01' = end of day UTC)"),
    promised_by: str = typer.Option("", "--promised-by", help="self | other (who owes the action)"),
    source_kind: str = typer.Option("manual", "--source-kind", help="manual | llm_extracted | wechat | ..."),
    source_interaction_id: int = typer.Option(0, "--source-interaction-id", min=0),
    force: bool = typer.Option(False, "--force", help="Bypass body_hash dedupe for LLM-sourced writes"),
) -> None:
    """Record a commitment ("open thread") for a person."""
    from brain_agents.open_threads import add_thread

    out = add_thread(
        person_id=person_id,
        body=body,
        due_utc=(due.strip() or None),
        promised_by=(promised_by.strip() or None),
        source_kind=source_kind,
        source_interaction_id=source_interaction_id or None,
        force=force,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@thread_app.command("close")
def thread_close_cmd(
    thread_id: int = typer.Argument(..., help="open_threads.id"),
    status: str = typer.Option("done", "--status", help="done | dropped"),
    reason: str = typer.Option("", "--reason", help="Advisory note (not persisted)"),
) -> None:
    from brain_agents.open_threads import close_thread

    out = close_thread(thread_id, status=status, reason=reason)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@thread_app.command("reopen")
def thread_reopen_cmd(thread_id: int = typer.Argument(..., help="open_threads.id")) -> None:
    from brain_agents.open_threads import reopen_thread

    typer.echo(json.dumps(reopen_thread(thread_id), ensure_ascii=False, indent=2, default=str))


@thread_app.command("update-due")
def thread_update_due_cmd(
    thread_id: int = typer.Argument(..., help="open_threads.id"),
    due: str = typer.Option(
        "",
        "--due",
        help="New ISO datetime/date, or '' to clear",
    ),
) -> None:
    from brain_agents.open_threads import update_due

    out = update_due(thread_id, due_utc=(due.strip() or None))
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@thread_app.command("list")
def thread_list_cmd(
    person_id: str = typer.Option("", "--person-id"),
    status: str = typer.Option("open", "--status", help="open | done | dropped | all"),
    limit: int = typer.Option(50, "--limit", min=1, max=1000),
) -> None:
    from brain_agents.open_threads import list_threads

    s = status.strip().lower()
    rows = list_threads(
        person_id=(person_id.strip() or None),
        status=None if s in {"all", ""} else s,
        limit=limit,
    )
    typer.echo(json.dumps(rows, ensure_ascii=False, indent=2, default=str))


@app.command("threads-scan")
def threads_scan_cmd(
    since_days: int = typer.Option(14, "--since-days", min=1, max=365),
    person_id: str = typer.Option("", "--person-id", help="Scope to a single person"),
    per_person_limit: int = typer.Option(30, "--per-person-limit", min=1, max=200),
    max_persons: int = typer.Option(50, "--max-persons", min=1, max=5000),
    min_confidence: float = typer.Option(0.6, "--min-confidence", min=0.0, max=1.0),
    apply: bool = typer.Option(False, "--apply", help="Write accepted candidates (default: dry-run)"),
) -> None:
    """LLM-extract commitments from recent interactions (dry-run by default).

    Candidates with ``confidence >= --min-confidence`` are written on
    ``--apply``; duplicates (same person + body) are deduped via body_hash.
    """
    from brain_agents.commitment_extract import scan_commitments

    out = scan_commitments(
        since_days=since_days,
        person_id=(person_id.strip() or None),
        per_person_limit=per_person_limit,
        max_persons=max_persons,
        min_confidence=min_confidence,
        apply=apply,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@person_digest_app.command("rebuild")
def person_digest_rebuild_cmd(
    person_id: str = typer.Option("", "--person-id", help="Target a single person_id"),
    all_people: bool = typer.Option(False, "--all", help="Scan all recently-active persons"),
    insight_type: str = typer.Option(
        "both",
        "--insight-type",
        help="both | topics | weekly",
    ),
    topics_days: int = typer.Option(30, "--topics-days", min=1, max=365),
    weekly_days: int = typer.Option(7, "--weekly-days", min=1, max=60),
    interaction_limit: int = typer.Option(40, "--interaction-limit", min=5, max=500),
    max_persons: int = typer.Option(200, "--max-persons", min=1, max=5000),
    min_interactions_30d: int = typer.Option(1, "--min-interactions-30d", min=1, max=1000),
) -> None:
    """Rebuild rolling topics + weekly digest insights.

    Idempotent: each rebuild inserts a new row and points the previous row's
    ``superseded_by`` at it. "Current" = ``superseded_by IS NULL``.
    """
    from brain_agents.person_digest import (
        INSIGHT_TOPICS,
        INSIGHT_WEEKLY,
        rebuild_all,
        rebuild_one,
    )

    t = insight_type.strip().lower()
    if t == "both":
        types = [INSIGHT_TOPICS, INSIGHT_WEEKLY]
    elif t == "topics":
        types = [INSIGHT_TOPICS]
    elif t == "weekly":
        types = [INSIGHT_WEEKLY]
    else:
        typer.echo(json.dumps({"status": "error", "reason": f"bad --insight-type: {insight_type!r}"}, indent=2))
        raise typer.Exit(code=1)

    if all_people:
        out = rebuild_all(
            insight_types=types,
            topics_days=topics_days,
            weekly_days=weekly_days,
            interaction_limit=interaction_limit,
            max_persons=max_persons,
            min_interactions_30d=min_interactions_30d,
        )
    elif person_id.strip():
        out = rebuild_one(
            person_id.strip(),
            insight_types=types,
            topics_days=topics_days,
            weekly_days=weekly_days,
            interaction_limit=interaction_limit,
        )
    else:
        typer.echo(json.dumps({"status": "error", "reason": "need --person-id or --all"}, indent=2))
        raise typer.Exit(code=1)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@person_digest_app.command("show")
def person_digest_show_cmd(person_id: str = typer.Argument(..., help="Target person_id")) -> None:
    from brain_agents.person_digest import get_current_insights

    typer.echo(json.dumps(get_current_insights(person_id), ensure_ascii=False, indent=2, default=str))


@tier_app.command("set")
def tier_set_cmd(
    person_id: str = typer.Argument(..., help="Target person_id"),
    tier: str = typer.Argument(..., help="inner | close | working | acquaintance | dormant"),
    note: str = typer.Option("", "--note", help="Optional human note (stored alongside)"),
    source_kind: str = typer.Option("manual", "--source", help="source_kind on the fact row"),
) -> None:
    from brain_agents.relationship_tier import ALLOWED_TIERS, set_tier

    try:
        out = set_tier(person_id, tier, note=note, source_kind=source_kind)
    except ValueError as exc:
        typer.echo(
            json.dumps(
                {"status": "error", "reason": str(exc), "allowed": list(ALLOWED_TIERS)},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=1)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@tier_app.command("get")
def tier_get_cmd(person_id: str = typer.Argument(..., help="Target person_id")) -> None:
    from brain_agents.relationship_tier import get_tier, get_tier_suggestion

    current = get_tier(person_id)
    suggestion = get_tier_suggestion(person_id)
    typer.echo(
        json.dumps(
            {"person_id": person_id, "current_tier": current, "suggestion": suggestion},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


@tier_app.command("list")
def tier_list_cmd(
    tier: str = typer.Option("", "--tier", help="Filter by tier (optional)"),
    include_history: bool = typer.Option(False, "--history", help="Include historical rows"),
) -> None:
    from brain_agents.relationship_tier import list_tiers

    rows = list_tiers(tier=tier or None, include_history=include_history)
    typer.echo(json.dumps({"count": len(rows), "rows": rows}, ensure_ascii=False, indent=2, default=str))


@tier_app.command("suggest")
def tier_suggest_cmd(
    person_id: str = typer.Option("", "--person-id", help="Target a single person_id"),
    all_people: bool = typer.Option(False, "--all", help="Scan all persons with metrics"),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Write the suggestion to person_facts when NO human fact exists (never overwrites)",
    ),
    max_persons: int = typer.Option(2000, "--max-persons", min=1, max=20000),
    min_interactions_all: int = typer.Option(1, "--min-interactions-all", min=0, max=10000),
) -> None:
    from brain_agents.relationship_tier import suggest_tier, suggest_tier_all

    if all_people:
        out = suggest_tier_all(
            min_interactions_all=min_interactions_all,
            max_persons=max_persons,
            apply_as_fact=apply,
        )
    elif person_id.strip():
        out = suggest_tier(person_id.strip(), apply_as_fact=apply)
    else:
        typer.echo(json.dumps({"status": "error", "reason": "need --person-id or --all"}, indent=2))
        raise typer.Exit(code=1)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@tier_app.command("overdue")
def tier_overdue_cmd(
    tier: str = typer.Option("", "--tier", help="Filter to one tier (optional)"),
) -> None:
    from brain_agents.relationship_tier import list_overdue_by_tier, load_cadence_config

    tiers = [tier.strip().lower()] if tier.strip() else None
    cadence = load_cadence_config()
    out = list_overdue_by_tier(tiers=tiers, cadence=cadence)
    total = sum(len(v) for v in out.values())
    typer.echo(
        json.dumps(
            {
                "cadence": cadence,
                "total_overdue": total,
                "by_tier": {k: len(v) for k, v in out.items()},
                "rows": out,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


@app.command("due")
def due_cmd(
    within: int = typer.Option(7, "--within", min=0, max=365, help="Days ahead to include"),
    person_id: str = typer.Option("", "--person-id"),
    overdue_only: bool = typer.Option(False, "--overdue-only", help="Only rows already past due"),
    include_overdue: bool = typer.Option(True, "--include-overdue/--no-overdue"),
    limit: int = typer.Option(100, "--limit", min=1, max=1000),
) -> None:
    """Show open commitments due within N days (includes overdue by default)."""
    from datetime import timedelta as _td

    from brain_agents.open_threads import _utc_now, list_due

    rows = list_due(
        within_days=0 if overdue_only else within,
        include_overdue=True if overdue_only else include_overdue,
        person_id=(person_id.strip() or None),
        limit=limit,
    )
    if overdue_only:
        now = _utc_now()
        rows = [r for r in rows if r.get("due_utc") and r["due_utc"] < now - _td(seconds=0)]
    typer.echo(json.dumps(rows, ensure_ascii=False, indent=2, default=str))


@merge_candidates_app.command("enqueue-manual")
def merge_candidates_enqueue_manual_cmd(
    person_a: str = typer.Argument(..., help="First person_id"),
    person_b: str = typer.Argument(..., help="Second person_id (must differ from person_a)"),
    reason: str = typer.Option(..., "--reason", help="Free-text reason (stored as 'manual:<reason>')"),
    score: float = typer.Option(1.0, "--score", min=0.0, max=1.0, help="Confidence score in [0,1]"),
    auto_apply: bool = typer.Option(False, "--auto-apply", help="Immediately merge after enqueue"),
) -> None:
    """Queue a manual (person_a, person_b) merge candidate (B-ING-1.6).

    Use this when human judgment identifies duplicates that
    ``sync-from-graph`` can't surface (the pair shares no normalized
    identifier). The pair is canonicalized (A,B == B,A), deduped against
    existing ``merge_candidates`` / ``merge_log``, and optionally
    auto-applied.
    """
    from brain_agents.merge_candidates import enqueue_manual_candidate

    out = enqueue_manual_candidate(
        person_a,
        person_b,
        reason=reason,
        score=score,
        auto_apply=auto_apply,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@merge_candidates_app.command("sync-from-graph")
def merge_candidates_sync_from_graph_cmd(
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview proposals (default) or insert pending rows"),
    max_inserts: int = typer.Option(500, min=1, max=5000, help="Safety cap on --apply writes"),
    auto_apply_min_score: float = typer.Option(
        0.0,
        "--auto-apply-min-score",
        min=0.0,
        max=1.0,
        help=(
            "When --apply is also set, proposed pairs with score >= this threshold "
            "are auto-merged through accept_candidate (immediate merge_persons + "
            "merge_log entry). Default 0.0 = opt-out (all inserts stay pending). "
            "Recommended 0.95 = auto-merge only phone-level matches; stronger than "
            "email/wxid (which score 0.92-0.93 and stay pending)."
        ),
    ),
) -> None:
    """Scan the Kuzu graph for cross-person shared identifiers and
    enqueue any pair not yet captured by merge_candidates or merge_log.

    With ``--auto-apply-min-score 0.95`` (and ``--apply``), high-
    confidence pairs merge immediately; the rest stay pending for
    human review via ``brain merge-candidates accept/reject``.
    Skips gracefully if the graph is not built.
    """
    from brain_agents.merge_candidates import sync_from_graph

    # 0.0 is the typer default meaning "not set"; pass None to keep
    # the Python side single-source-of-truth on what counts as opt-in.
    threshold: float | None = auto_apply_min_score if auto_apply_min_score > 0 else None
    out = sync_from_graph(
        dry_run=dry_run,
        max_inserts=max_inserts,
        auto_apply_min_score=threshold,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@merge_candidates_app.command("enqueue-stale-for-cloud")
def merge_candidates_enqueue_stale_for_cloud_cmd(
    apply: bool = typer.Option(False, "--apply", help="Actually enqueue cloud_queue rows"),
) -> None:
    """Queue ``merge-t3-review`` tasks for pending merge_candidates older than ``cloud_queue.merge_t3_pending_days``."""
    from brain_agents.merge_candidates import enqueue_stale_merge_candidates_for_cloud

    out = enqueue_stale_merge_candidates_for_cloud(dry_run=not apply)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("structure-history")
def structure_history_cmd(dry_run: bool = typer.Option(True, help="Run dry-run only (recommended)")) -> None:
    from brain_agents.structure import structure_history

    typer.echo(json.dumps(structure_history(dry_run=dry_run), ensure_ascii=False, indent=2))


@app.command("daily-digest")
def daily_digest_cmd() -> None:
    from brain_agents.digest import generate_daily_digest

    typer.echo(json.dumps(generate_daily_digest(), ensure_ascii=False, indent=2))


@app.command("weekly-review")
def weekly_review_cmd() -> None:
    from brain_agents.digest import generate_weekly_review

    typer.echo(json.dumps(generate_weekly_review(), ensure_ascii=False, indent=2))


@app.command("relationship-alerts")
def relationship_alerts_cmd(days: int = typer.Option(45, min=1, max=365)) -> None:
    from brain_agents.digest import generate_relationship_alerts

    typer.echo(json.dumps(generate_relationship_alerts(days=days), ensure_ascii=False, indent=2))


@app.command("budget-tracker")
def budget_tracker_cmd() -> None:
    from brain_agents.digest import generate_budget_tracker

    typer.echo(json.dumps(generate_budget_tracker(), ensure_ascii=False, indent=2))


@app.command("ollama-smoke")
def ollama_smoke_cmd() -> None:
    from brain_agents.ollama_smoke import run_smoke

    typer.echo(json.dumps(run_smoke(), ensure_ascii=False, indent=2))


@queue_app.command("list")
def cloud_queue_list_cmd(limit: int = typer.Option(50, min=1, max=500)) -> None:
    from brain_agents.cloud_queue import list_pending

    typer.echo(json.dumps(list_pending(limit=limit), ensure_ascii=False, indent=2, default=str))


@queue_app.command("show")
def cloud_queue_show_cmd(queue_id: int = typer.Argument(..., help="cloud_queue.id")) -> None:
    from brain_agents.cloud_queue import show

    row = show(queue_id)
    typer.echo(json.dumps(row or {}, ensure_ascii=False, indent=2, default=str))


@queue_app.command("drop")
def cloud_queue_drop_cmd(queue_id: int = typer.Argument(..., help="cloud_queue.id")) -> None:
    from brain_agents.cloud_queue import drop

    typer.echo(json.dumps(drop(queue_id), ensure_ascii=False, indent=2))


@app.command("wechat-sync")
def wechat_sync_cmd(
    decoder_dir: str = typer.Option(
        r"C:\dev-projects\wechat-decoder",
        "--decoder-dir",
        help="Root of wechat-decoder (expects artifacts/chat_*.json; searches for contact SQLite)",
    ),
    contact_db: str = typer.Option(
        "",
        "--contact-db",
        help="Optional explicit path to decrypted SQLite with `contact` table",
    ),
    since: str = typer.Option(
        "",
        "--since",
        help="Only import chat messages with ts >= this ISO-8601 timestamp",
    ),
    include_helper_chats: bool = typer.Option(
        False,
        "--include-helper-chats",
        help="Include chat_filehelper / chat_file_transfer_assistant exports",
    ),
    chat_whitelist: str = typer.Option(
        "",
        "--chat-whitelist",
        help="Comma-separated conversations to ingest (e.g. filehelper,20292966501@chatroom)",
    ),
    chat_blacklist: str = typer.Option(
        "",
        "--chat-blacklist",
        help="Comma-separated conversations to skip",
    ),
    helper_chat_mode: str = typer.Option(
        "link-person",
        "--helper-chat-mode",
        help="link-person or no-person (helper chats only)",
    ),
    group_chats: str = typer.Option(
        "bind_sender",
        "--group-chats",
        help="bind_sender (default)=import @chatroom lines under sender's person when wxid/alias resolves; skip=ignore group JSON files",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; no DuckDB writes"),
) -> None:
    from brain_agents.wechat_sync import sync_from_cli

    gc = group_chats.strip().lower()
    if gc not in ("skip", "bind_sender"):
        typer.echo(json.dumps({"status": "error", "reason": "group_chats must be skip or bind_sender"}, indent=2))
        raise typer.Exit(code=1)
    typer.echo(
        json.dumps(
            sync_from_cli(
                decoder_dir,
                contact_db=contact_db,
                since=since,
                include_helper_chats=include_helper_chats,
                chat_whitelist=chat_whitelist,
                chat_blacklist=chat_blacklist,
                helper_chat_mode=helper_chat_mode,
                group_chat_mode=gc,
                dry_run=dry_run,
            ),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


@app.command("gmail-ingest-takeout")
def gmail_ingest_takeout_cmd(
    path: str = typer.Argument(..., help="Path to one .mbox file or a directory containing Takeout *.mbox exports"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Count only; no DuckDB writes"),
    limit: int = typer.Option(0, "--limit", min=0, help="Max messages to ingest (0 = unlimited)"),
    since: str = typer.Option("", "--since", help="Only messages with parsed Date >= this ISO-8601 instant"),
) -> None:
    from pathlib import Path

    from brain_agents.gmail_takeout_ingest import ingest_takeout_mbox

    root = Path(path).expanduser()
    since_dt = None
    if since.strip():
        from datetime import datetime, timezone

        s = since.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        since_dt = datetime.fromisoformat(s)
        if since_dt.tzinfo is not None:
            since_dt = since_dt.astimezone(timezone.utc).replace(tzinfo=None)
    out = ingest_takeout_mbox(root, dry_run=dry_run, limit=limit, since=since_dt)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("wechat-prune-groups")
def wechat_prune_groups_cmd(
    apply: bool = typer.Option(False, "--apply", help="Execute deletes (default is dry-run only)"),
    no_prune_contacts: bool = typer.Option(
        False,
        "--no-prune-contacts",
        help="Keep persons that only exist as @chatroom handles (still delete group interactions)",
    ),
) -> None:
    from brain_agents.wechat_sync import prune_wechat_group_artifacts

    out = prune_wechat_group_artifacts(dry_run=not apply, prune_chatroom_contacts=not no_prune_contacts)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    if not apply:
        itd = int(out.get("interactions_to_delete") or 0)
        pdel = int(out.get("persons_to_delete") or 0)
        if itd or pdel:
            typer.echo("Re-run with --apply to execute.", err=True)


@app.command("backup-ios-locate")
def backup_ios_locate_cmd(
    backup_root: str = typer.Option(
        "",
        "--backup-root",
        help="Optional explicit iPhone backup UDID folder (contains Manifest.db)",
    ),
) -> None:
    from pathlib import Path

    from brain_agents.ios_backup_locator import locate_bundle

    parent = Path(backup_root).resolve() if backup_root.strip() else None
    typer.echo(
        json.dumps(
            locate_bundle(backup_udid_dir=parent),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


@app.command("contacts-ingest-ios")
def contacts_ingest_ios_cmd(
    db_path: str = typer.Option("", "--db", help="AddressBook.sqlitedb (auto-locate when omitted)"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    snapshot_ref: str = typer.Option(
        "",
        "--snapshot-ref",
        help="Explicit snapshot .duckdb path to attribute (overrides auto-pick)",
    ),
    snapshot_max_age_minutes: int = typer.Option(
        120,
        "--snapshot-max-age-minutes",
        min=0,
        help="Auto-pick window for latest ingest-backup-now snapshot (0 = no cap)",
    ),
) -> None:
    from pathlib import Path

    from brain_agents.contacts_ingest_ios import ingest_address_book_sqlite
    from brain_agents.ingest_backup import _short_descriptor, latest_snapshot, list_snapshots
    from brain_agents.ios_backup_locator import find_addressbook_sqlitedb

    p = Path(db_path) if db_path.strip() else None
    if p is None or not p.is_file():
        hit = find_addressbook_sqlitedb()
        sel = hit.get("selected")
        if not sel:
            typer.echo(json.dumps({"status": "error", "reason": "missing_db", "hint": hit}, ensure_ascii=False, indent=2))
            raise typer.Exit(code=1)
        p = Path(sel)

    backup_desc: dict | None = None
    if snapshot_ref.strip():
        ref = snapshot_ref.strip()
        for s in list_snapshots(limit=200):
            if str(s.get("snapshot") or "") == ref:
                backup_desc = _short_descriptor(s)
                break
    elif not dry_run:
        desc = latest_snapshot(
            label_prefix="ios-addressbook",
            max_age_minutes=snapshot_max_age_minutes,
        )
        if desc is None:
            desc = latest_snapshot(max_age_minutes=snapshot_max_age_minutes)
        if desc is not None:
            backup_desc = _short_descriptor(desc)

    typer.echo(
        json.dumps(
            ingest_address_book_sqlite(p, dry_run=dry_run, backup_descriptor=backup_desc),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


@app.command("whatsapp-ingest-ios")
def whatsapp_ingest_ios_cmd(
    db_path: str = typer.Option("", "--db", help="ChatStorage.sqlite (auto-locate when omitted)"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    limit: int = typer.Option(0, "--limit", min=0, help="Max messages to import (0 = all)"),
    snapshot_ref: str = typer.Option(
        "",
        "--snapshot-ref",
        help="Explicit snapshot .duckdb path to attribute (overrides auto-pick)",
    ),
    snapshot_max_age_minutes: int = typer.Option(
        120,
        "--snapshot-max-age-minutes",
        min=0,
        help="Auto-pick window for latest ingest-backup-now snapshot (0 = no cap)",
    ),
) -> None:
    from pathlib import Path

    from brain_agents.ingest_backup import _short_descriptor, latest_snapshot, list_snapshots
    from brain_agents.ios_backup_locator import find_chatstorage_sqlite
    from brain_agents.whatsapp_ingest_ios import ingest_chatstorage_sqlite

    p = Path(db_path) if db_path.strip() else None
    if p is None or not p.is_file():
        hit = find_chatstorage_sqlite()
        sel = hit.get("selected")
        if not sel:
            typer.echo(json.dumps({"status": "error", "reason": "missing_db", "hint": hit}, ensure_ascii=False, indent=2))
            raise typer.Exit(code=1)
        p = Path(sel)

    backup_desc: dict | None = None
    if snapshot_ref.strip():
        ref = snapshot_ref.strip()
        for s in list_snapshots(limit=200):
            if str(s.get("snapshot") or "") == ref:
                backup_desc = _short_descriptor(s)
                break
    elif not dry_run:
        desc = latest_snapshot(
            label_prefix="whatsapp",
            max_age_minutes=snapshot_max_age_minutes,
        )
        if desc is None:
            desc = latest_snapshot(max_age_minutes=snapshot_max_age_minutes)
        if desc is not None:
            backup_desc = _short_descriptor(desc)

    lim = None if limit <= 0 else limit
    typer.echo(
        json.dumps(
            ingest_chatstorage_sqlite(p, dry_run=dry_run, limit=lim, backup_descriptor=backup_desc),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


@app.command("ingest-backup-now")
def ingest_backup_now_cmd(
    label: str = typer.Option("manual", "--label", help="Short label appended to the snapshot filename"),
) -> None:
    """B-ING-0 · Snapshot brain-telemetry.duckdb before a real ingest.

    Copies the live DuckDB file to _backup/telemetry/<ts>-<label>.duckdb
    with an sha256 sidecar and an append-only pointer-log.jsonl index.
    Always run this before the FIRST apply of a new source.
    """
    from brain_agents.ingest_backup import snapshot_duckdb

    out = snapshot_duckdb(label=label)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("asset-dedup")
def asset_dedup_cmd(
    assets_root: str = typer.Option("", "--assets-root", help="Override paths.assets_root"),
    min_kb: int = typer.Option(10, "--min-kb", min=0, help="Skip files smaller than this"),
    include_inbox: bool = typer.Option(False, "--include-inbox", help="Do NOT skip 99-inbox/ (default skips it)"),
    no_write: bool = typer.Option(False, "--no-write", help="Skip writing the MD/TSV reports"),
) -> None:
    """B1 · Two-pass SHA256 dedup scanner (Python port of
    tools/asset/brain-asset-dedup.ps1). Read-only; writes reports
    to ``<assets_root>/_migration/dedup-YYYY-MM-DD.{md,tsv}``.
    """
    from pathlib import Path as _P

    from brain_agents.asset_dedup import run

    out = run(
        assets_root=_P(assets_root) if assets_root.strip() else None,
        min_kb=min_kb,
        include_inbox=include_inbox,
        write_reports=not no_write,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("asset-stats")
def asset_stats_cmd(
    assets_root: str = typer.Option("", "--assets-root", help="Override paths.assets_root"),
    content_root: str = typer.Option("", "--content-root", help="Override paths.content_root"),
    no_write: bool = typer.Option(False, "--no-write", help="Skip writing the Markdown report"),
) -> None:
    """B1 · Pure-metadata scan of brain-assets (Python port of
    tools/asset/brain-asset-stats.ps1). Writes a MD report to
    04-journal/brain-assets-stats-YYYY-MM-DD.md by default.
    """
    from pathlib import Path as _P

    from brain_agents.asset_stats import run

    out = run(
        assets_root=_P(assets_root) if assets_root.strip() else None,
        content_root=_P(content_root) if content_root.strip() else None,
        write_report=not no_write,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("asset-scan")
def asset_scan_cmd(
    source: str = typer.Option(..., "--source", help="Source directory to scan (e.g. D:\\BaiduSyncdisk)"),
    job_name: str = typer.Option("", "--job", help="Job label for the manifest filename (default: job-<ts>)"),
    assets_root: str = typer.Option("", "--assets-root", help="Override paths.assets_root"),
) -> None:
    """B3 · Stage-1 scanner (Python port of
    tools/asset/brain-asset-migrate.ps1, scan half). Walks ``--source``,
    runs the classification rules, writes
    ``<assets_root>/_migration/<job>-manifest.tsv``. Zero token,
    zero file writes outside the manifest. Review the TSV, then run
    ``brain asset-migrate-execute``.
    """
    from pathlib import Path as _P

    from brain_agents.asset_migrate import run_scan

    out = run_scan(
        source=_P(source),
        job_name=job_name or None,
        assets_root=_P(assets_root) if assets_root.strip() else None,
    )
    if out.get("status") == "ok":
        out = {
            "status": out["status"],
            "source": out["source"],
            "job_name": out["job_name"],
            "manifest_path": out.get("manifest_path"),
            "total": out["total"],
            "excluded": out["excluded"],
            "rows": len(out["rows"]),
            "counts": out["counts"],
            "sizes_mb": {k: round(v / (1024 * 1024), 1) for k, v in out["sizes"].items()},
        }
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("asset-migrate-execute")
def asset_migrate_execute_cmd(
    manifest_path: str = typer.Option("", "--manifest-path", help="Specific manifest TSV (default: latest under _migration/)"),
    assets_root: str = typer.Option("", "--assets-root", help="Override paths.assets_root"),
    brain_root: str = typer.Option("", "--brain-root", help="Override paths.content_root (for text files going to 99-inbox)"),
) -> None:
    """B3 · Stage-3 executor (Python port of
    tools/asset/brain-asset-migrate.ps1, execute half). Reads a
    manifest, copies each row's source to its destination (mtime
    preserved), renames-on-collision using the source's mtime, and
    writes a sibling ``*-execute.log``. Source files are **never**
    deleted (``trash-candidate`` rows are logged only).
    """
    from pathlib import Path as _P

    from brain_agents.asset_migrate import run_execute

    out = run_execute(
        manifest_path=_P(manifest_path) if manifest_path.strip() else None,
        assets_root=_P(assets_root) if assets_root.strip() else None,
        brain_root=_P(brain_root) if brain_root.strip() else None,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("asset-parity-diff")
def asset_parity_diff_cmd(
    a_path: str = typer.Option(..., "--a", help="First manifest TSV (conventionally the PS -DryRun output)"),
    b_path: str = typer.Option(..., "--b", help="Second manifest TSV (conventionally brain asset-scan output)"),
    output: str = typer.Option("", "--output", help="Write a Markdown parity report to this path"),
) -> None:
    """E2 · Diff two asset-migrate manifests.

    Used during the 3-week parity window after B3/B4 to confirm
    ``brain asset-scan`` (Python) agrees with
    ``brain-asset-migrate.ps1 -DryRun`` (PowerShell) before
    deleting the PS scripts. Pure read-only on both inputs.

    Join key is ``source_path`` (case-insensitive, slash-normalized).
    Mismatch dimensions: rule / action / target_dir.
    """
    from brain_agents.asset_migrate_parity import run

    out = run(a_path=a_path, b_path=b_path, output_path=output or None)
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("asset-source-cleanup")
def asset_source_cleanup_cmd(
    manifest_path: str = typer.Option("", "--manifest-path", help="Specific manifest TSV (default: latest under _migration/)"),
    execute_log_path: str = typer.Option("", "--execute-log", help="Specific <job>-execute.log (default: sibling of manifest)"),
    assets_root: str = typer.Option("", "--assets-root", help="Override paths.assets_root"),
    brain_root: str = typer.Option("", "--brain-root", help="Override paths.content_root"),
    source_root: str = typer.Option("", "--source-root", help="Root to sweep for empty dirs after deletion (e.g. D:\\BaiduSyncdisk). Skipped when omitted."),
    apply: bool = typer.Option(False, "--apply", help="Actually delete source files. Default is DRY-RUN (safer than PS)."),
    no_delete_empty_dirs: bool = typer.Option(False, "--no-delete-empty-dirs", help="Skip the post-deletion empty-dir sweep"),
) -> None:
    """B4 · Stage-4 source cleanup (Python port of
    tools/asset/brain-asset-source-cleanup.ps1). Reads a manifest's
    sibling ``<job>-execute.log`` (falls back to manifest rows), runs
    src-exists + dst-exists + size-match safety gates, then (when
    ``--apply``) deletes source files. Writes ``<job>-cleanup.log``.

    Default is **DRY-RUN** (PS defaulted to real delete). Use
    ``--apply`` to actually delete. Always pair with a recent
    ``brain ingest-backup-now`` if anything indexed by DuckDB
    points at the source paths.
    """
    from pathlib import Path as _P

    from brain_agents.asset_source_cleanup import run

    out = run(
        manifest_path=_P(manifest_path) if manifest_path.strip() else None,
        execute_log_path=_P(execute_log_path) if execute_log_path.strip() else None,
        assets_root=_P(assets_root) if assets_root.strip() else None,
        brain_root=_P(brain_root) if brain_root.strip() else None,
        source_root=_P(source_root) if source_root.strip() else None,
        apply=apply,
        delete_empty_dirs=not no_delete_empty_dirs,
    )
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2, default=str))


@app.command("ingest-log-recent")
def ingest_log_recent_cmd(
    days: int = typer.Option(7, "--days", min=1, max=90),
    source: str = typer.Option("", "--source", help="Filter: ios_addressbook | whatsapp_ios | wechat"),
    limit: int = typer.Option(50, "--limit", min=1, max=1000),
) -> None:
    """B-ING-0 · Tail the structured ingest event log (JSONL)."""
    from brain_agents.ingest_log import list_recent_events

    rows = list_recent_events(days=days, source=source or None, limit=limit)
    typer.echo(json.dumps({"count": len(rows), "events": rows}, ensure_ascii=False, indent=2, default=str))


@cloud_app.command("flush")
def cloud_flush_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print plan without spawning cursor-agent"),
    agent_cmd: str = typer.Option("", "--agent-cmd", help="Override path to cursor-agent/agent.cmd"),
) -> None:
    from brain_agents.cloud_flush import flush

    typer.echo(
        json.dumps(
            flush(dry_run=dry_run, agent_cmd=agent_cmd or None),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


def main() -> None:
    _ensure_utf8_stdout()
    # Subcommands emit JSON or single-line text on stdout for scripts. Any shell profile banner
    # printed before Python starts is outside this module; avoid extra stdout noise here.
    app()


if __name__ == "__main__":
    main()
