"""Local LLM JSON extraction for phones, emails, wxids, names, explicit URLs."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from ollama import Client


def _client() -> Client:
    host = os.getenv("OLLAMA_HOST", "").strip()
    return Client(host=host) if host else Client()


def _default_model() -> str:
    return os.getenv("BRAIN_ENTITY_MODEL", "qwen2.5:14b-instruct").strip()


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


def extract_entities(text: str, *, model: str | None = None) -> dict[str, Any]:
    """
    Returns dict with keys: phones, emails, wxids, person_names, urls (lists of strings).
    On total failure returns empty lists.
    """
    seed = _default_model()
    use_model = (model or seed).strip()
    snippet = text.strip()
    if len(snippet) > 12000:
        snippet = snippet[:12000] + "\n…"

    prompt = (
        "Extract structured contact signals from the note. Reply with ONE JSON object only, no markdown, "
        'with keys: "phones" (array of strings, E.164 or local digits ok), '
        '"emails" (array), "wxids" (WeChat wxid-like ids), '
        '"person_names" (human names explicitly mentioned as contacts), '
        '"urls" (only http/https URLs literally present in the text). '
        "Use empty arrays when none. Do not invent URLs or contacts.\n\nTEXT:\n"
        f"{snippet}"
    )

    def _call() -> str:
        out = _client().generate(model=use_model, prompt=prompt)
        if hasattr(out, "response"):
            return str(getattr(out, "response") or "")
        if isinstance(out, dict):
            return str(out.get("response", ""))
        return str(out)

    raw = _strip_json_fence(_call())
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return _empty_payload()
    except json.JSONDecodeError:
        raw2 = _strip_json_fence(_call())
        try:
            data = json.loads(raw2)
            if not isinstance(data, dict):
                return _empty_payload()
        except json.JSONDecodeError:
            return _empty_payload()

    return {
        "phones": _as_str_list(data.get("phones")),
        "emails": _as_str_list(data.get("emails")),
        "wxids": _as_str_list(data.get("wxids")),
        "person_names": _as_str_list(data.get("person_names")),
        "urls": _as_str_list(data.get("urls")),
    }


def _empty_payload() -> dict[str, Any]:
    return {"phones": [], "emails": [], "wxids": [], "person_names": [], "urls": []}


def _as_str_list(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, str):
        return [val.strip()] if val.strip() else []
    if isinstance(val, list):
        out: list[str] = []
        for x in val:
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    return []
