"""A4 MVP writing assistant with provenance."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from ollama import Client

from brain_agents.ask import ask
from brain_agents.text_inbox import _split_frontmatter


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


# --- A4 provenance ---------------------------------------------------------

_KIND_RULES: tuple[tuple[str, str], ...] = (
    ("/inbox-auto-pdf/", "pdf"),
    ("/inbox-auto-image/", "image"),
    ("/inbox-auto-audio/", "audio"),
    ("/05-contacts/", "person-note"),
    ("/04-journal/", "journal"),
)


def _classify_source(path_str: str) -> str:
    p = "/" + path_str.replace("\\", "/").lower()
    for needle, kind in _KIND_RULES:
        if needle in p:
            return kind
    return "note"


def _read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}
    fm, _ = _split_frontmatter(text)
    return fm or {}


def enrich_provenance(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return sources annotated with {kind, asset_sha256?, asset_type?,
    person_id?, ocr_status?, asr_status?}.
    """
    enriched: list[dict[str, Any]] = []
    for row in sources:
        path_str = str(row.get("path", "") or "")
        item: dict[str, Any] = {
            "path": path_str,
            "title": row.get("title", ""),
            "method": row.get("method", ""),
            "kind": _classify_source(path_str),
        }
        if path_str:
            try:
                p = Path(path_str)
                if p.exists() and p.is_file() and p.suffix.lower() in {".md", ".markdown"}:
                    fm = _read_frontmatter(p)
                    for k in ("asset_sha256", "asset_type", "person_id", "ocr_status", "asr_status"):
                        if k in fm:
                            item[k] = fm[k]
            except Exception:
                pass
        enriched.append(item)
    return enriched


def render_provenance_block(enriched: list[dict[str, Any]]) -> str:
    """Render a `## 参考` tail block from an already-enriched provenance list."""
    if not enriched:
        return ""
    lines = ["## 参考", ""]
    for i, e in enumerate(enriched, 1):
        bits: list[str] = [str(e.get("kind", "note"))]
        title = str(e.get("title", "")).strip()
        if title:
            bits.append(title)
        sha = e.get("asset_sha256")
        if sha:
            bits.append(f"sha256:{sha}")
        person_id = e.get("person_id")
        if person_id:
            bits.append(f"person:{person_id}")
        label = " · ".join(bits)
        path = e.get("path", "")
        lines.append(f"- [{i}] {label} — `{path}`")
    return "\n".join(lines)


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


def _ollama_client() -> Client:
    host = os.getenv("OLLAMA_HOST", "").strip()
    return Client(host=host) if host else Client()


def _apply_constraints(draft: str, max_paragraphs: int, max_chars: int, banned: list[str]) -> str:
    draft = _clean_phrase(draft, banned)
    parts = [p.strip() for p in draft.split("\n\n") if p.strip()]
    if len(parts) > max_paragraphs:
        parts = parts[:max_paragraphs]
    out = "\n\n".join(parts)
    return out[:max_chars]


def _llm_generate(
    topic: str,
    platform: str,
    reader: str,
    sources: list[dict[str, Any]],
    cfg: dict[str, Any],
    style: dict[str, Any],
    max_paragraphs: int,
    max_chars: int,
    banned: list[str],
    extra_instruction: str = "",
) -> str:
    legacy_wm = os.getenv("BRAIN_WRITE_MODEL", "").strip()
    if legacy_wm:
        model = legacy_wm
    else:
        from brain_core.ollama_models import brain_fast_model

        model = brain_fast_model()
    bullets: list[str] = []
    for row in sources[: min(5, len(sources))]:
        prev = str(row.get("preview", ""))[:280]
        bullets.append(f"- {row.get('title', '')}: {prev}")
    block = "\n".join(bullets) if bullets else "(no retrieval hits)"
    opening = style.get("opening", "")
    cta = style.get("cta", "")
    extra = f"\nAdditional constraint:\n{extra_instruction}\n" if extra_instruction.strip() else ""
    prompt = (
        f"You are a writing assistant. Output ONLY the draft body (no markdown title line, no preamble).\n"
        f"Platform: {platform}\nReader: {reader}\nTopic: {topic}\n"
        f"Tone: {cfg.get('tone_default', 'clear')}\n"
        f"Style hints — opening: {opening}; closing: {cta}\n"
        f"Hard limits: at most {max_paragraphs} paragraphs (blank line separated), "
        f"at most {max_chars} characters total.\n"
        f"Use the same primary language as the topic (e.g. Chinese if the topic is Chinese).\n"
        f"Never use these phrases (even partially): {', '.join(repr(b) for b in banned if b)}.\n"
        f"{extra}"
        f"\nReference snippets from the user's notes:\n{block}\n"
    )
    client = _ollama_client()
    out = client.generate(model=model, prompt=prompt)
    if hasattr(out, "response"):
        raw = getattr(out, "response") or ""
    elif isinstance(out, dict):
        raw = str(out.get("response", ""))
    else:
        raw = str(out)
    return raw.strip()


def write_draft(
    topic: str,
    platform: str,
    reader: str,
    source_limit: int = 5,
    engine: str = "llm",
    *,
    include_provenance: bool = True,
) -> dict[str, Any]:
    cfg = _constraints().get("writing", {})
    style = cfg.get("platform_style", {}).get(platform, cfg.get("platform_style", {}).get("default", {}))
    opening = style.get("opening", "state the core idea in one sentence")
    cta = style.get("cta", "end with next step")
    banned = list(cfg.get("banned_phrases", []))
    max_paragraphs = int(cfg.get("max_paragraphs", 4))
    max_chars = int(cfg.get("max_chars", 1200))
    tone = cfg.get("tone_default", "clear, practical, concrete")

    retrieval_query = f"{topic} {reader} {platform}"
    sources = ask(retrieval_query, limit=source_limit, mode="auto")

    engine_l = engine.lower().strip()
    if engine_l not in {"template", "llm"}:
        engine_l = "template"

    draft = ""
    engine_used = engine_l
    fallback_reason = ""
    if engine_l == "llm":
        try:
            draft = _llm_generate(
                topic=topic,
                platform=platform,
                reader=reader,
                sources=sources,
                cfg=cfg,
                style=style,
                max_paragraphs=max_paragraphs,
                max_chars=max_chars,
                banned=banned,
            )
            if not draft.strip():
                raise ValueError("empty_llm_response")
            draft = _apply_constraints(draft, max_paragraphs, max_chars, banned)
            if any(b.lower() in draft.lower() for b in banned if b):
                draft = _llm_generate(
                    topic=topic,
                    platform=platform,
                    reader=reader,
                    sources=sources,
                    cfg=cfg,
                    style=style,
                    max_paragraphs=max_paragraphs,
                    max_chars=max_chars,
                    banned=banned,
                    extra_instruction=(
                        "Rewrite completely: the previous version still contained a banned phrase. "
                        "Avoid clichés and the forbidden phrases listed above."
                    ),
                )
                draft = _apply_constraints(draft, max_paragraphs, max_chars, banned)
        except Exception as exc:
            engine_used = "template"
            fallback_reason = type(exc).__name__
            draft = ""

    if not draft:
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
        draft = _apply_constraints(draft, max_paragraphs, max_chars, banned)

    provenance = enrich_provenance(sources)
    if include_provenance and provenance:
        block = render_provenance_block(provenance)
        if block:
            draft = draft.rstrip() + "\n\n" + block + "\n"
    out: dict[str, Any] = {
        "topic": topic,
        "platform": platform,
        "reader": reader,
        "tone": tone,
        "engine": engine_used,
        "draft": draft,
        "provenance": provenance,
    }
    if engine_l == "llm" and fallback_reason:
        out["engine_fallback"] = fallback_reason
    return out

