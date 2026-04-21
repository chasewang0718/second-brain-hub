"""People linking + `[people-note: …]` extraction after text inbox ingest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from brain_agents.cloud_queue import enqueue
from brain_agents.entity_extract import extract_entities
from brain_agents.identity_resolver import resolve_identifier
from brain_agents.people import who
from brain_memory.structured import execute
from brain_agents.text_inbox import _split_frontmatter


_PEOPLE_NOTE_TAG = re.compile(r"\[people-note:\s*([^\]]+)\]", re.IGNORECASE)


def _merge_frontmatter(path: Path, patch: dict[str, Any]) -> None:
    raw = path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(raw)
    if fm is None:
        fm = {}
    for k, v in patch.items():
        if v is None:
            continue
        fm[k] = v
    blob = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    path.write_text(f"---\n{blob}\n---\n{body}", encoding="utf-8")


def parse_people_note_blocks(body: str) -> list[tuple[str, str]]:
    matches = list(_PEOPLE_NOTE_TAG.finditer(body))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        note_body = body[start:end].strip()
        out.append((name, note_body))
    return out


def _resolve_person_note_name(name: str) -> tuple[str | None, list[str]]:
    rows = who(name)
    ids = [str(r["id"]) for r in rows]
    if len(ids) == 1:
        return ids[0], ids
    return None, ids


def apply_people_postprocess(target_path: Path, raw_text: str) -> dict[str, Any]:
    """Resolve entities + people-notes; update frontmatter; optional cloud_queue."""
    fm, body = _split_frontmatter(raw_text)
    base_body = body if body is not None else raw_text

    summary: dict[str, Any] = {
        "people_notes_written": 0,
        "people_note_queued": 0,
        "linked_person": None,
        "ambiguous": False,
        "cloud_enqueued": False,
    }

    linked_ids: list[str] = []

    # --- [people-note: Name] blocks → person_notes
    for pname, pbody in parse_people_note_blocks(base_body):
        pid, cand = _resolve_person_note_name(pname)
        if pid is not None:
            execute(
                """
                INSERT INTO person_notes (person_id, body, source_kind, detail_json)
                VALUES (?, ?, 'capsd-people-note', ?)
                """,
                [
                    pid,
                    pbody,
                    json.dumps({"source_path": str(target_path), "tag_name": pname}, ensure_ascii=False),
                ],
            )
            summary["people_notes_written"] += 1
            linked_ids.append(pid)
        elif not cand:
            enqueue(
                "capsd-note-hard",
                {
                    "reason": "people-note-unresolved",
                    "name": pname,
                    "path": str(target_path),
                    "body_preview": pbody[:800],
                },
            )
            summary["people_note_queued"] += 1
            summary["cloud_enqueued"] = True
        else:
            enqueue(
                "capsd-note-hard",
                {
                    "reason": "people-note-ambiguous",
                    "name": pname,
                    "candidates": cand,
                    "path": str(target_path),
                    "body_preview": pbody[:800],
                },
            )
            summary["people_note_queued"] += 1
            summary["cloud_enqueued"] = True

    # --- LLM entity extraction → link single person when unambiguous
    extracted = {"phones": [], "emails": [], "wxids": [], "person_names": [], "urls": []}
    if len(base_body.strip()) >= 40:
        try:
            extracted = extract_entities(base_body)
        except Exception:
            pass

    resolved: set[str] = set()
    for phone in extracted.get("phones") or []:
        pid = resolve_identifier("phone", str(phone))
        if pid:
            resolved.add(pid)
    for email in extracted.get("emails") or []:
        pid = resolve_identifier("email", str(email))
        if pid:
            resolved.add(pid)
    for wx in extracted.get("wxids") or []:
        pid = resolve_identifier("wxid", str(wx))
        if pid:
            resolved.add(pid)
    for nm in extracted.get("person_names") or []:
        hit, cand = _resolve_person_note_name(str(nm))
        if hit:
            resolved.add(hit)
        elif len(cand) > 1:
            summary["ambiguous"] = True

    resolved.update(linked_ids)
    uniq = sorted(resolved)

    patch: dict[str, Any] = {}
    if len(uniq) == 1:
        patch["linked_person"] = uniq[0]
        summary["linked_person"] = uniq[0]
    elif len(uniq) > 1:
        patch["linked_person_candidates"] = uniq
        summary["ambiguous"] = True
        enqueue(
            "capsd-note-hard",
            {
                "reason": "inbox-multi-person-signals",
                "path": str(target_path),
                "candidates": uniq,
                "extracted": {k: extracted.get(k) for k in ("phones", "emails", "wxids", "person_names")},
            },
        )
        summary["cloud_enqueued"] = True

    if patch:
        _merge_frontmatter(target_path, patch)

    summary["extracted_preview"] = {
        "phones": (extracted.get("phones") or [])[:5],
        "emails": (extracted.get("emails") or [])[:5],
        "wxids": (extracted.get("wxids") or [])[:5],
        "person_names": (extracted.get("person_names") or [])[:5],
        "urls": (extracted.get("urls") or [])[:5],
    }
    return summary
