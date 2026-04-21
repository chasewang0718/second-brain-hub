"""A1 minimal ask engine: vector + fulltext fusion."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config
from brain_memory.vectors import search as vector_search

ALIASES: dict[str, list[str]] = {
    "荷兰": ["netherlands", "dutch", "nl"],
    "公证员": ["notary", "notaris", "notariaat", "notarieel"],
    "税": ["tax", "belasting", "btw", "inkomstenbelasting"],
    "发票": ["invoice", "factuur", "proforma"],
}


def _content_root() -> Path:
    return Path(load_paths_config()["paths"]["content_root"])


def _terms(query: str) -> list[str]:
    items = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", query.lower())
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
        # Exact alias
        for alias in ALIASES.get(item, []):
            if alias not in out:
                out.append(alias)
        # Substring alias (e.g. "荷兰公证员" should trigger 荷兰 + 公证员)
        for key, aliases in ALIASES.items():
            if key in item:
                for alias in aliases:
                    if alias not in out:
                        out.append(alias)
        if re.fullmatch(r"[\u4e00-\u9fff]+", item) and len(item) >= 4:
            for i in range(len(item) - 1):
                bi = item[i : i + 2]
                if bi not in out:
                    out.append(bi)
    return out[:16]


def _keyword_hits(query: str, limit: int) -> list[dict[str, Any]]:
    terms = _terms(query)
    if not terms:
        return []
    term_weight = {t: max(1, len(t) // 2) for t in terms if t}
    rows: list[dict[str, Any]] = []
    for path in sorted(_content_root().rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
        low = text.lower()
        score = 0.0
        for term, weight in term_weight.items():
            if term in low or term in path.stem.lower():
                score += weight
        if score <= 0:
            continue
        rows.append(
            {
                "path": str(path),
                "title": path.stem,
                "preview": text.strip().replace("\r", " ").replace("\n", " ")[:220],
                "score": float(-score),
                "method": "fulltext",
                "_term_hits": score,
            }
        )
    rows.sort(key=lambda x: (x["_term_hits"], len(x["title"])), reverse=True)
    return rows[:limit]


def ask(query: str, limit: int = 5) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        return []
    vec = vector_search(query=query, limit=max(limit, 8))
    txt = _keyword_hits(query=query, limit=max(limit, 8))
    merged: dict[str, dict[str, Any]] = {}
    for row in txt + vec:
        key = row["path"]
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(row)
            merged[key]["_hybrid"] = 0.0
        r = merged[key]
        if row.get("method") == "fulltext":
            r["_hybrid"] += 3.0 + float(row.get("_term_hits", 1))
        else:
            # vector distance lower is better
            dist = float(row.get("score", 1.0))
            r["_hybrid"] += max(0.0, 1.2 - dist)
        r["method"] = "hybrid"
    ranked = sorted(merged.values(), key=lambda x: x["_hybrid"], reverse=True)[:limit]
    for row in ranked:
        row.pop("_hybrid", None)
        row.pop("_term_hits", None)
    return ranked

