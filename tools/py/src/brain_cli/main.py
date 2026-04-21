"""Minimal Typer CLI for F1.0 bring-up."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from brain_core.config import load_paths_config, load_runtime_config

app = typer.Typer(help="second-brain-hub Python CLI")

cloud_app = typer.Typer(help="Cloud offload queue (manual brain cloud flush)")
queue_app = typer.Typer(help="Inspect pending cloud_queue rows")
cloud_app.add_typer(queue_app, name="queue")
app.add_typer(cloud_app, name="cloud")

merge_candidates_app = typer.Typer(help="T3 identity merge queue (manual review)")
app.add_typer(merge_candidates_app, name="merge-candidates")


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


@merge_candidates_app.command("sync-from-graph")
def merge_candidates_sync_from_graph_cmd(
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview proposals (default) or insert pending rows"),
    max_inserts: int = typer.Option(500, min=1, max=5000, help="Safety cap on --apply writes"),
) -> None:
    """Scan the Kuzu graph for cross-person shared identifiers and
    enqueue any pair not yet captured by merge_candidates or merge_log.
    Skips gracefully if the graph is not built.
    """
    from brain_agents.merge_candidates import sync_from_graph

    out = sync_from_graph(dry_run=dry_run, max_inserts=max_inserts)
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
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; no DuckDB writes"),
) -> None:
    from brain_agents.wechat_sync import sync_from_cli

    typer.echo(
        json.dumps(
            sync_from_cli(decoder_dir, contact_db=contact_db, since=since, dry_run=dry_run),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


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
) -> None:
    from pathlib import Path

    from brain_agents.contacts_ingest_ios import ingest_address_book_sqlite
    from brain_agents.ios_backup_locator import find_addressbook_sqlitedb

    p = Path(db_path) if db_path.strip() else None
    if p is None or not p.is_file():
        hit = find_addressbook_sqlitedb()
        sel = hit.get("selected")
        if not sel:
            typer.echo(json.dumps({"status": "error", "reason": "missing_db", "hint": hit}, ensure_ascii=False, indent=2))
            raise typer.Exit(code=1)
        p = Path(sel)
    typer.echo(json.dumps(ingest_address_book_sqlite(p, dry_run=dry_run), ensure_ascii=False, indent=2, default=str))


@app.command("whatsapp-ingest-ios")
def whatsapp_ingest_ios_cmd(
    db_path: str = typer.Option("", "--db", help="ChatStorage.sqlite (auto-locate when omitted)"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    limit: int = typer.Option(0, "--limit", min=0, help="Max messages to import (0 = all)"),
) -> None:
    from pathlib import Path

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
    lim = None if limit <= 0 else limit
    typer.echo(json.dumps(ingest_chatstorage_sqlite(p, dry_run=dry_run, limit=lim), ensure_ascii=False, indent=2, default=str))


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
