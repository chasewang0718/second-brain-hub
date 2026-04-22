"""Render DuckDB persons + interactions into Obsidian-friendly Markdown under 06-people/by-person/."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from brain_core.config import load_paths_config
from brain_memory.structured import ensure_schema, query


_WIN_BAD = set('<>:"/\\|?*\n\r\t')


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _content_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    return Path(load_paths_config()["paths"]["content_root"]).expanduser().resolve()


def _out_dir(content_root: Path) -> Path:
    return (content_root / "06-people" / "by-person").resolve()


def _sanitize_filename_segment(s: str, max_len: int = 72) -> str:
    out: list[str] = []
    for ch in (s or "").strip():
        if ch in _WIN_BAD or ord(ch) < 32:
            out.append("_")
        else:
            out.append(ch)
    seg = "".join(out).strip(" .") or "person"
    if len(seg) > max_len:
        seg = seg[:max_len].rstrip("._ ")
    return seg or "person"


def _markdown_filename(primary_name: str, person_id: str) -> str:
    left = _sanitize_filename_segment(primary_name or "unknown", max_len=56)
    right = _sanitize_filename_segment(person_id.replace(":", "_"), max_len=80)
    return f"{left}__{right}.md"


def _insights_bundle(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest_by_type: dict[str, dict[str, Any]] = {}
    for row in rows:
        it = str(row.get("insight_type") or "").strip().lower()
        if it and it not in latest_by_type:
            latest_by_type[it] = row
    topics: list[str] = []
    commitments: list[str] = []
    warmth: int | None = None
    trow = latest_by_type.get("topics")
    if trow:
        try:
            d = json.loads(str(trow.get("detail_json") or "{}"))
            if isinstance(d, dict):
                topics = [str(x).strip() for x in (d.get("topics") or []) if str(x).strip()]
        except Exception:
            pass
        if not topics:
            body = str(trow.get("body") or "").strip()
            topics = [x.strip() for x in body.split(",") if x.strip()]
    crow = latest_by_type.get("commitments")
    if crow:
        try:
            d = json.loads(str(crow.get("detail_json") or "{}"))
            if isinstance(d, dict):
                commitments = [str(x).strip() for x in (d.get("commitments") or []) if str(x).strip()]
        except Exception:
            pass
        if not commitments:
            body = str(crow.get("body") or "").strip()
            commitments = [x.strip() for x in body.splitlines() if x.strip()]
    wrow = latest_by_type.get("warmth")
    if wrow:
        try:
            d = json.loads(str(wrow.get("detail_json") or "{}"))
            if isinstance(d, dict):
                warmth = int(d.get("warmth") or 0) or None
        except Exception:
            pass
        if warmth is None:
            try:
                warmth = int(str(wrow.get("body") or "").strip())
            except Exception:
                warmth = None
    return {
        "topics": topics[:10],
        "commitments": commitments[:10],
        "warmth": warmth,
        "available": bool(topics or commitments or warmth is not None),
    }


def _fetch_identifiers(person_id: str) -> list[dict[str, Any]]:
    return query(
        """
        SELECT kind, value_normalized, value_original, source_kind, confidence
        FROM person_identifiers
        WHERE person_id = ?
        ORDER BY kind, value_normalized
        """,
        [person_id],
    )


def _fetch_insight_rows(person_id: str) -> list[dict[str, Any]]:
    return query(
        """
        SELECT insight_type, body, detail_json, created_at
        FROM person_insights
        WHERE person_id = ?
        ORDER BY created_at DESC
        LIMIT 20
        """,
        [person_id],
    )


def _fetch_notes(person_id: str, limit: int = 40) -> list[dict[str, Any]]:
    return query(
        """
        SELECT ts_utc, body, source_kind
        FROM person_notes
        WHERE person_id = ?
        ORDER BY ts_utc DESC
        LIMIT ?
        """,
        [person_id, limit],
    )


def _fetch_current_facts(person_id: str) -> list[dict[str, Any]]:
    """Current (valid_to IS NULL) facts ordered by key."""
    return query(
        """
        SELECT id, key, value_json, valid_from, confidence, source_kind, source_interaction_id
        FROM person_facts
        WHERE person_id = ? AND valid_to IS NULL
        ORDER BY key
        """,
        [person_id],
    )


def _fetch_fact_history(person_id: str, limit: int = 200) -> list[dict[str, Any]]:
    return query(
        """
        SELECT id, key, value_json, valid_from, valid_to, confidence, source_kind, source_interaction_id
        FROM person_facts
        WHERE person_id = ?
        ORDER BY key, valid_from DESC, id DESC
        LIMIT ?
        """,
        [person_id, max(1, min(limit, 2000))],
    )


def _fetch_metrics(person_id: str) -> dict[str, Any] | None:
    rows = query(
        """
        SELECT first_seen_utc, last_seen_utc, last_interaction_channel,
               interactions_all, interactions_30d, interactions_90d,
               distinct_channels_30d, dormancy_days, computed_at
        FROM person_metrics
        WHERE person_id = ?
        LIMIT 1
        """,
        [person_id],
    )
    return rows[0] if rows else None


def _format_fact_value(value_json: Any) -> str:
    raw = str(value_json or "null")
    try:
        decoded = json.loads(raw)
    except Exception:
        return raw.replace("|", "\\|")
    if isinstance(decoded, str):
        return decoded.replace("|", "\\|") or "(empty)"
    if decoded is None:
        return "_null_"
    return json.dumps(decoded, ensure_ascii=False).replace("|", "\\|")


def _fetch_open_threads(person_id: str, limit: int = 25) -> list[dict[str, Any]]:
    """Fetch open threads with commitment metadata (Phase A6 Sprint 2).

    Ordering: overdue/today first (soonest-due ascending), then undated
    threads by recency. Closed threads are excluded (the card should
    only remind the user of what's still owed).
    """
    return query(
        """
        SELECT id, summary AS body, status, updated_at,
               due_utc, promised_by, last_mentioned_utc,
               source_interaction_id, source_kind
        FROM open_threads
        WHERE person_id = ? AND lower(coalesce(status, '')) = 'open'
        ORDER BY
          CASE WHEN due_utc IS NULL THEN 1 ELSE 0 END,
          due_utc ASC,
          updated_at DESC
        LIMIT ?
        """,
        [person_id, limit],
    )


def _fetch_interactions(
    person_id: str,
    *,
    limit: int,
    since_days: int | None,
) -> list[dict[str, Any]]:
    lim = max(1, min(limit, 200))
    params: list[Any] = [person_id]
    since_sql = ""
    if since_days is not None and since_days > 0:
        cutoff = _utc_now() - timedelta(days=int(since_days))
        since_sql = " AND ts_utc >= ?"
        params.append(cutoff)
    params.append(lim)
    return query(
        f"""
        SELECT ts_utc, channel, summary, source_path, source_kind
        FROM interactions
        WHERE person_id = ?
          {since_sql}
        ORDER BY ts_utc DESC
        LIMIT ?
        """,
        params,
    )


def _channels_for_person(person_id: str) -> list[str]:
    rows = query(
        """
        SELECT DISTINCT channel
        FROM interactions
        WHERE person_id = ? AND channel IS NOT NULL AND trim(channel) <> ''
        ORDER BY 1
        """,
        [person_id],
    )
    return [str(r["channel"]) for r in rows if r.get("channel")]


def _build_markdown(
    *,
    person_id: str,
    primary_name: str,
    last_seen_utc: Any,
    since_days_used: int | None,
    interaction_limit: int,
    include_graph_hints: bool,
    include_facts_history: bool = False,
) -> str:
    ids = _fetch_identifiers(person_id)
    notes = _fetch_notes(person_id)
    threads = _fetch_open_threads(person_id)
    interactions = _fetch_interactions(
        person_id,
        limit=interaction_limit,
        since_days=since_days_used,
    )
    insights = _insights_bundle(_fetch_insight_rows(person_id))
    channels = _channels_for_person(person_id)
    facts_current = _fetch_current_facts(person_id)
    facts_history = _fetch_fact_history(person_id) if include_facts_history else []
    metrics = _fetch_metrics(person_id)
    try:
        from brain_agents.person_digest import get_current_insights as _get_digest

        digest_bundle = _get_digest(person_id)
    except Exception as _exc:  # pragma: no cover - defensive; never fail rendering
        import logging as _logging

        _logging.getLogger(__name__).warning("person_digest.get_current_insights failed: %s", _exc)
        digest_bundle = {"topics": None, "weekly": None}

    # Phase A6 Sprint 4: relationship tier + cadence status
    current_tier: str | None = None
    tier_suggestion: dict[str, Any] | None = None
    cadence_target: int | None = None
    try:
        from brain_agents.relationship_tier import (
            get_tier as _get_tier,
            get_tier_suggestion as _get_tier_sugg,
            load_cadence_config as _load_cadence,
        )

        current_tier = _get_tier(person_id)
        tier_suggestion = _get_tier_sugg(person_id)
        if current_tier:
            cadence_target = _load_cadence().get(current_tier)
    except Exception as _exc:  # pragma: no cover - defensive
        import logging as _logging

        _logging.getLogger(__name__).warning("relationship_tier lookup failed: %s", _exc)

    graph_block = ""
    if include_graph_hints:
        try:
            from brain_agents.people import _collect_graph_hints

            gh = _collect_graph_hints(person_id, limit=5, auto_freshen=False)
        except Exception as exc:  # pragma: no cover - defensive
            gh = {"status": "skipped", "reason": str(exc)}
        if isinstance(gh, dict) and gh.get("status") == "ok":
            shared = gh.get("shared_identifier") or []
            if shared:
                lines_g = ["", "## 潜在同一人线索 (graph)", "", "| person_id | display_name | kind | value |", "| --- | --- | --- | --- |"]
                for r in shared:
                    pid2 = str(r.get("person_id") or "")
                    nm = str(r.get("display_name") or "").replace("|", "\\|")
                    kind = str(r.get("kind") or "")
                    val = str(r.get("value_normalized") or "").replace("|", "\\|")
                    lines_g.append(f"| `{pid2}` | {nm} | {kind} | `{val}` |")
                graph_block = "\n".join(lines_g)

    fm: dict[str, Any] = {
        "person_id": person_id,
        "primary_name": primary_name,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "since_days_interactions": since_days_used,
        "channels": channels,
    }
    if last_seen_utc is not None:
        fm["last_seen_utc"] = str(last_seen_utc)
    if current_tier:
        fm["relationship_tier"] = current_tier
        if cadence_target is not None:
            fm["cadence_target_days"] = int(cadence_target)

    header = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n"
    banner = (
        "\n<!-- AUTO-GENERATED by `brain people-render`. "
        "Do not hand-edit body: next run overwrites. "
        "Add notes via Caps+D text inbox using `[people-note: "
        + str(primary_name).replace("]", "\\]")
        + "]` syntax. -->\n\n"
    )

    lines: list[str] = [header, banner, f"# {primary_name}", "", f"- **person_id**: `{person_id}`", ""]

    lines += ["## Identifiers", ""]
    if not ids:
        lines.append("(none)")
    else:
        lines += ["| kind | value | source |", "| --- | --- | --- |"]
        for r in ids:
            kind = str(r.get("kind") or "")
            val = str(r.get("value_normalized") or "").replace("|", "\\|")
            sk = str(r.get("source_kind") or "")
            lines.append(f"| {kind} | `{val}` | {sk} |")
    lines.append("")

    if facts_current or include_facts_history:
        lines += ["## Facts", ""]
        if not facts_current:
            lines.append("(no current facts; add via `brain facts add <pid> <key> <value>`)")
        else:
            lines += ["| key | value | confidence | source | since |", "| --- | --- | --- | --- | --- |"]
            for r in facts_current:
                key = str(r.get("key") or "").replace("|", "\\|")
                val = _format_fact_value(r.get("value_json"))
                conf_raw = r.get("confidence")
                try:
                    conf = f"{float(conf_raw):.2f}" if conf_raw is not None else "-"
                except Exception:
                    conf = "-"
                sk = str(r.get("source_kind") or "").replace("|", "\\|")
                vf = str(r.get("valid_from") or "")
                lines.append(f"| {key} | {val} | {conf} | {sk} | {vf} |")
        if include_facts_history and facts_history:
            lines += ["", "### Facts history (latest first)", ""]
            lines += ["| key | value | valid_from | valid_to | source |", "| --- | --- | --- | --- | --- |"]
            for r in facts_history:
                key = str(r.get("key") or "").replace("|", "\\|")
                val = _format_fact_value(r.get("value_json"))
                vf = str(r.get("valid_from") or "")
                vt = str(r.get("valid_to") or "") or "_(current)_"
                sk = str(r.get("source_kind") or "").replace("|", "\\|")
                lines.append(f"| {key} | {val} | {vf} | {vt} | {sk} |")
        lines.append("")

    if metrics is not None:
        lines += ["## Metrics", ""]
        ls = str(metrics.get("last_seen_utc") or "") or "(never)"
        fs = str(metrics.get("first_seen_utc") or "") or "(never)"
        lch = str(metrics.get("last_interaction_channel") or "") or "(unknown)"
        dormancy = metrics.get("dormancy_days")
        dormancy_s = str(dormancy) if dormancy is not None else "_n/a_"
        lines += [
            f"- **interactions**: total **{int(metrics.get('interactions_all') or 0)}** · "
            f"30d {int(metrics.get('interactions_30d') or 0)} · "
            f"90d {int(metrics.get('interactions_90d') or 0)}",
            f"- **first seen**: {fs}",
            f"- **last seen**: {ls} ({lch})",
            f"- **dormancy**: {dormancy_s} days",
            f"- **distinct channels (30d)**: {int(metrics.get('distinct_channels_30d') or 0)}",
            f"- **computed at**: {metrics.get('computed_at')}",
            "",
        ]

    # --- Phase A6 Sprint 4: Relationship Tier + cadence status -------------
    if current_tier or tier_suggestion:
        lines += ["## Relationship Tier", ""]
        if current_tier:
            dormancy_val = (metrics or {}).get("dormancy_days")
            try:
                dormancy_int = int(dormancy_val) if dormancy_val is not None else None
            except (TypeError, ValueError):
                dormancy_int = None

            chip = "—"
            if cadence_target is None:
                chip = "— (no alarm)"
            elif dormancy_int is None:
                chip = "— (no dormancy)"
            elif dormancy_int > int(cadence_target):
                chip = f"\u26a0\ufe0f {dormancy_int - int(cadence_target)}d overdue"
            else:
                chip = f"\u2705 within cadence ({dormancy_int}/{int(cadence_target)}d)"

            lines.append(f"- **current**: `{current_tier}`")
            if cadence_target is not None:
                lines.append(f"- **cadence target**: {int(cadence_target)} days")
            else:
                lines.append("- **cadence target**: _no alarm_")
            lines.append(f"- **status**: {chip}")
            lines.append("")
        if tier_suggestion:
            sugg_tier = str(tier_suggestion.get("suggested_tier") or "").strip() or "?"
            detail = tier_suggestion.get("detail") or {}
            confidence = detail.get("confidence")
            reason = str(detail.get("reason") or "")
            sugg_line = f"- **AI suggestion**: `{sugg_tier}`"
            if isinstance(confidence, (int, float)):
                sugg_line += f" (confidence {float(confidence):.2f})"
            if reason:
                sugg_line += f" — {reason}"
            lines.append(sugg_line)
            lines.append("")

    lines += ["## 近期洞察", ""]
    if not insights.get("available"):
        lines.append("(run `brain people-insights-refresh` to populate)")
    else:
        w = insights.get("warmth")
        if w is not None:
            lines.append(f"- **关系温度 (1–5)**: {w}")
        if insights.get("topics"):
            lines.append(f"- **最近话题**: {', '.join(str(x) for x in insights['topics'])}")
        if insights.get("commitments"):
            lines.append("- **最近承诺**:")
            for c in insights["commitments"]:
                lines.append(f"  - {c}")
    lines.append("")

    lines += ["## Recent interactions", ""]
    if not interactions:
        lines.append("(none in window)")
    else:
        lines += ["| ts_utc | channel | summary |", "| --- | --- | --- |"]
        for r in interactions:
            ts = str(r.get("ts_utc") or "")
            ch = str(r.get("channel") or "")
            summary = str(r.get("summary") or "").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {ts} | {ch} | {summary} |")
    lines.append("")

    lines += ["## Caps+D notes (`person_notes`)", ""]
    if not notes:
        lines.append("(none)")
    else:
        for r in notes:
            ts = str(r.get("ts_utc") or "")
            body = str(r.get("body") or "").strip().replace("\n", "\n> ")
            sk = str(r.get("source_kind") or "")
            lines.append(f"- **{ts}** ({sk})")
            lines.append("")
            lines.append(f"> {body}")
            lines.append("")
    lines.append("")

    lines += ["## Open threads", ""]
    if not threads:
        lines.append("(none)")
    else:
        from brain_agents.open_threads import classify_due

        lines += [
            "| status | due | who owes | body | last seen | source |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for r in threads:
            due = r.get("due_utc")
            bucket = classify_due(due)
            chip = {
                "overdue": "\u26a0\ufe0f overdue",
                "today": "\U0001f525 today",
                "soon": "\u23f3 soon",
                "later": "later",
                "none": "—",
            }.get(bucket, "—")
            due_s = str(due) if due else "_no due_"
            pby = str(r.get("promised_by") or "").strip() or "—"
            body = (
                str(r.get("body") or r.get("summary") or "")
                .replace("|", "\\|")
                .replace("\n", " ")
            )
            last = str(r.get("last_mentioned_utc") or r.get("updated_at") or "")
            sk = str(r.get("source_kind") or "").strip() or "manual"
            lines.append(f"| {chip} | {due_s} | {pby} | {body} | {last} | {sk} |")
    lines.append("")

    # --- Phase A6 Sprint 3: rolling topics + weekly digest ------------------
    # Both insights are rendered when present; absence is silently dropped
    # (unlike "## Open threads" which keeps a "(none)" placeholder, these
    # sections only make sense once person-digest has actually run).
    topics_row = (digest_bundle or {}).get("topics")
    if topics_row:
        topics_list = (topics_row.get("detail") or {}).get("topics") or []
        window_end = topics_row.get("window_end_utc")
        src = topics_row.get("source_kind") or ""
        lines += ["## Topics (30d)", ""]
        if topics_list:
            tags = " · ".join(f"`{t}`" for t in topics_list[:10])
            lines.append(tags)
            lines.append("")
        body = str(topics_row.get("body") or "").strip()
        if body:
            for para in body.split("\n"):
                p = para.strip()
                if p:
                    lines.append(p)
            lines.append("")
        lines.append(f"_window ending {window_end} · source: {src}_")
        lines.append("")

    weekly_row = (digest_bundle or {}).get("weekly")
    if weekly_row:
        window_end = weekly_row.get("window_end_utc")
        window_start = weekly_row.get("window_start_utc")
        src = weekly_row.get("source_kind") or ""
        lines += ["## Weekly Digest", ""]
        body = str(weekly_row.get("body") or "").strip()
        if body:
            for para in body.split("\n"):
                p = para.strip()
                if p:
                    lines.append(p)
            lines.append("")
        else:
            lines += ["(none)", ""]
        lines.append(f"_window: {window_start} → {window_end} · source: {src}_")
        lines.append("")

    lines.append(graph_block)
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _list_person_ids_for_batch(
    *,
    since_days: int,
    channel: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    ch = (channel or "").strip() or None
    lim = max(1, min(limit, 20000))
    if since_days <= 0:
        if ch:
            return query(
                """
                SELECT DISTINCT p.person_id, p.primary_name, p.last_seen_utc
                FROM persons p
                WHERE EXISTS (
                    SELECT 1 FROM interactions i
                    WHERE i.person_id = p.person_id AND lower(trim(i.channel)) = lower(?)
                )
                ORDER BY p.last_seen_utc DESC NULLS LAST
                LIMIT ?
                """,
                [ch, lim],
            )
        return query(
            """
            SELECT person_id, primary_name, last_seen_utc
            FROM persons
            ORDER BY last_seen_utc DESC NULLS LAST
            LIMIT ?
            """,
            [lim],
        )

    cutoff = _utc_now() - timedelta(days=int(since_days))
    if ch:
        return query(
            """
            SELECT DISTINCT p.person_id, p.primary_name, p.last_seen_utc
            FROM persons p
            WHERE EXISTS (
                SELECT 1 FROM interactions i
                WHERE i.person_id = p.person_id
                  AND i.ts_utc >= ?
                  AND lower(trim(i.channel)) = lower(?)
            )
            ORDER BY p.last_seen_utc DESC NULLS LAST
            LIMIT ?
            """,
            [cutoff, ch, lim],
        )
    return query(
        """
        SELECT DISTINCT p.person_id, p.primary_name, p.last_seen_utc
        FROM persons p
        WHERE EXISTS (
            SELECT 1 FROM interactions i
            WHERE i.person_id = p.person_id AND i.ts_utc >= ?
        )
        ORDER BY p.last_seen_utc DESC NULLS LAST
        LIMIT ?
        """,
        [cutoff, lim],
    )


def _write_index(out: Path, entries: list[tuple[str, str]]) -> None:
    """entries: (wikilink_path_without_brackets, display_name)"""
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat()
    lines = [
        "---",
        f"generated_at: {stamp}",
        f"people_count: {len(entries)}",
        "note: auto-generated by brain people-render",
        "---",
        "",
        "# People cards index",
        "",
    ]
    for path, name in sorted(entries, key=lambda x: x[1].lower()):
        safe = name.replace("]", "\\]")
        lines.append(f"- [[{path}|{safe}]]")
    lines.append("")
    (out / "_index.md").write_text("\n".join(lines), encoding="utf-8")


def run_people_render(
    *,
    who: str | None = None,
    person_id: str | None = None,
    all_people: bool = False,
    since_days: int = 90,
    channel: str | None = None,
    limit: int = 500,
    interaction_limit: int = 25,
    interaction_since_days: int | None = None,
    graph_hints: bool = False,
    facts_history: bool = False,
    dry_run: bool = False,
    content_root: Path | None = None,
) -> dict[str, Any]:
    """Render Markdown relationship cards from DuckDB.

    Exactly one selector: ``who``, ``person_id``, or ``all_people``.
    """
    root = _content_root(content_root)
    out = _out_dir(root)
    mode_count = sum([bool(who and who.strip()), bool(person_id and person_id.strip()), all_people])
    if mode_count != 1:
        return {"status": "error", "reason": "specify exactly one of: who, person_id, all_people"}

    ensure_schema()

    if interaction_since_days is not None:
        inter_since = interaction_since_days if interaction_since_days > 0 else None
    elif all_people:
        inter_since = int(since_days) if int(since_days) > 0 else None
    else:
        inter_since = None

    targets: list[dict[str, Any]] = []
    if person_id and person_id.strip():
        row = query(
            "SELECT person_id, primary_name, last_seen_utc FROM persons WHERE person_id = ?",
            [person_id.strip()],
        )
        if not row:
            return {"status": "error", "reason": "person_not_found", "person_id": person_id.strip()}
        targets = row
    elif who and who.strip():
        from brain_agents.people import who as who_fn

        cand = who_fn(who.strip())
        if not cand:
            return {"status": "error", "reason": "no_match", "who": who.strip()}
        cid = cand[0]["id"]
        targets = query(
            "SELECT person_id, primary_name, last_seen_utc FROM persons WHERE person_id = ?",
            [cid],
        )
    else:
        targets = _list_person_ids_for_batch(
            since_days=max(0, int(since_days)),
            channel=channel,
            limit=limit,
        )

    written: list[str] = []
    index_entries: list[tuple[str, str]] = []
    if not targets:
        return {
            "status": "ok",
            "written": [],
            "out_dir": str(out),
            "count": 0,
            "dry_run": dry_run,
            "message": "no persons matched",
        }

    if not dry_run:
        out.mkdir(parents=True, exist_ok=True)

    for t in targets:
        pid = str(t["person_id"])
        pname = str(t.get("primary_name") or pid)
        fn = _markdown_filename(pname, pid)
        rel_obsidian = f"06-people/by-person/{fn.replace('.md', '')}"
        md = _build_markdown(
            person_id=pid,
            primary_name=pname,
            last_seen_utc=t.get("last_seen_utc"),
            since_days_used=inter_since,
            interaction_limit=interaction_limit,
            include_graph_hints=graph_hints and len(targets) == 1,
            include_facts_history=facts_history,
        )
        dest = out / fn
        if not dry_run:
            dest.write_text(md, encoding="utf-8")
        written.append(str(dest))
        index_entries.append((rel_obsidian, pname))

    if not dry_run and all_people and index_entries:
        _write_index(out, index_entries)

    return {
        "status": "ok",
        "out_dir": str(out),
        "written": written,
        "count": len(written),
        "dry_run": dry_run,
        "graph_hints": bool(graph_hints and len(targets) == 1),
    }
