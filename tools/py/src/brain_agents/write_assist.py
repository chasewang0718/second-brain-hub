"""A4 MVP writing assistant with provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from brain_agents.ask import ask
from brain_core.config import load_paths_config


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _constraints() -> dict[str, Any]:
    path = _repo_root() / "config" / "writing-constraints.yaml"
    if not path.exists():
        return {"writing": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"writing": {}}
    return data


def _clean_phrase(text: str, banned: list[str]) -> str:
    out = text
    for phrase in banned:
        out = out.replace(phrase, "")
        out = out.replace(phrase.title(), "")
    return out


def write_draft(topic: str, platform: str, reader: str, source_limit: int = 5) -> dict[str, Any]:
    cfg = _constraints().get("writing", {})
    style = cfg.get("platform_style", {}).get(platform, cfg.get("platform_style", {}).get("default", {}))
    opening = style.get("opening", "state the core idea in one sentence")
    cta = style.get("cta", "end with next step")
    banned = list(cfg.get("banned_phrases", []))
    max_paragraphs = int(cfg.get("max_paragraphs", 4))
    max_chars = int(cfg.get("max_chars", 1200))
    tone = cfg.get("tone_default", "clear, practical, concrete")

    retrieval_query = f"{topic} {reader} {platform}"
    sources = ask(retrieval_query, limit=source_limit)

    lead = f"{topic} matters to {reader} because it directly affects real decisions."
    body_points = [
        f"One practical approach: {opening}.",
        "Use one small experiment first, measure result, then scale.",
        "Keep the language plain and avoid abstract jargon.",
    ]
    if sources:
        body_points.append(f"Reference prior notes from {Path(sources[0]['path']).name} to keep consistency.")
    body_points.append(f"Final move: {cta}.")

    paragraphs = [lead] + body_points[: max(0, max_paragraphs - 1)]
    draft = "\n\n".join(paragraphs)
    draft = _clean_phrase(draft, banned)[:max_chars]

    provenance = [
        {"path": row.get("path", ""), "title": row.get("title", ""), "method": row.get("method", "")}
        for row in sources
    ]
    return {
        "topic": topic,
        "platform": platform,
        "reader": reader,
        "tone": tone,
        "draft": draft,
        "provenance": provenance,
    }

