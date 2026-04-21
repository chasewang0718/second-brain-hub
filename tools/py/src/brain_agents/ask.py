"""A1 minimal ask engine: vector + fulltext fusion."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config

ALIASES: dict[str, list[str]] = {
    "荷兰": ["netherlands", "dutch", "nl"],
    "公证员": ["notary", "notaris", "notariaat", "notarieel"],
    "税": ["tax", "belasting", "btw", "inkomstenbelasting"],
    "发票": ["invoice", "factuur", "proforma"],
    "联系": ["contact", "overdue", "people", "meeting"],
    "谁": ["who", "person", "people"],
    "回顾": ["review", "weekly", "digest"],
    "摘要": ["digest", "summary"],
    "结构": ["structure", "directory", "history", "split"],
    "优化": ["optimize", "improve", "suggestion"],
    "写作": ["write", "draft", "constraints"],
    "约束": ["constraint", "banned", "phrase", "max_chars"],
    "配置": ["config", "yaml", "paths"],
    "读取": ["read", "load", "paths"],
    "检索": ["search", "retrieval", "ask", "hybrid", "rerank"],
    "混合": ["hybrid", "fusion", "rerank"],
    "队列": ["queue", "cursor_queue", "escalation"],
    "兜底": ["fallback", "queue", "cursor_queue"],
    "mcp": ["fastmcp", "brain-mcp", "mcp.json"],
    "paths": ["paths.yaml", "config/paths"],
}


def _content_root() -> Path:
    return Path(load_paths_config()["paths"]["content_root"])


def _intent_extra_terms(query: str) -> list[str]:
    """High-recall English tokens for rg when Chinese query implies a hub/content topic."""
    q = query.lower()
    extra: list[str] = []
    if any(c in query for c in ("谁", "联系", "天")) or "40" in query:
        extra.extend(["overdue", "digest", "06-people", "contact"])
    if "cursor" in q or "兜底" in query or "队列" in query:
        extra.extend(["_cursor_queue", "cursor-delegated", "escalation"])
    if "写作" in query or "banned" in q or "约束" in query:
        extra.extend(["constraints", "writing", "banned", "yaml"])
    if "mcp" in q or "paths" in q or "配置" in query:
        extra.extend(["mcp", "paths", "fastmcp", "config"])
    out: list[str] = []
    for t in extra:
        if t and t not in out:
            out.append(t)
    return out[:12]


def _preview_snippet(text: str, terms: list[str], query: str, max_len: int = 420) -> str:
    """Prefer a snippet around the strongest matched term so previews surface real hits (not just file headers)."""
    plain = text.replace("\r\n", "\n").replace("\r", "\n")
    low = plain.lower()
    ql = query.lower()
    priority: list[str] = []
    if "写作" in query or "banned" in ql or "约束" in query:
        priority.extend(["config", "yaml", "constraints", "banned", "writing-constraints"])
    if "mcp" in ql or "paths" in ql:
        priority.extend(["fastmcp", "mcp", "paths.yaml", "config/paths"])
    ranked = [t for t in priority if t in low and len(t) >= 2]
    ranked.extend(t for t in sorted((t for t in terms if len(t) >= 2), key=len, reverse=True) if t not in ranked)
    for term in ranked:
        pos = low.find(term.lower())
        if pos >= 0:
            start = max(0, pos - 120)
            end = min(len(plain), start + max_len)
            snippet = plain[start:end]
            one_line = " ".join(snippet.replace("\n", " ").split())
            return one_line[:max_len]
    one_line = " ".join(plain.replace("\n", " ").split())
    return one_line[:max_len]


def _intent_path_bonus(query: str, path: Path, base_score: float) -> float:
    """Prefer obviously relevant directories when the query intent matches."""
    s = str(path).replace("\\", "/").lower()
    bonus = 0.0
    if any(c in query for c in ("谁", "联系")) or "overdue" in query.lower():
        if "digest" in s or "06-people" in s or "people" in s:
            bonus += 12.0
    if "cursor" in query.lower() or "兜底" in query:
        if "agents" in s or "cursor" in s or "queue" in s:
            bonus += 10.0
    if "写作" in query or "banned" in query.lower():
        if "workflow" in s or "brain-tools-index" in s or "concept" in s:
            bonus += 8.0
    if "mcp" in query.lower() or "paths" in query.lower():
        if "journal" in s or "workflow" in s or "memory" in s or "agents" in s:
            bonus += 6.0
    return base_score + bonus


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
    for t in _intent_extra_terms(query):
        if t not in terms:
            terms.append(t)
    if not terms:
        return []
    term_weight = {t: max(1, len(t) // 2) for t in terms if t}
    candidates: set[Path] = set()
    root = _content_root()
    for term in terms[:12]:
        try:
            proc = subprocess.run(
                ["rg", "-F", "-l", "--glob", "*.md", term, str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            proc = None
        if proc and proc.returncode in (0, 1):
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line:
                    candidates.add(Path(line))

    # Fallback when rg is unavailable or returns nothing.
    if not candidates:
        candidates = set(root.rglob("*.md"))

    rows: list[dict[str, Any]] = []
    for path in sorted(candidates):
        text = path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
        low = text.lower()
        score = 0.0
        for term, weight in term_weight.items():
            if term in low or term in path.stem.lower():
                score += weight
        ql = query.lower()
        if "mcp" in ql and ("fastmcp" in low or "mcp::" in low or " brain-mcp" in low):
            score += 22.0
        if ("cursor" in ql or "兜底" in query) and ("_cursor_queue" in low or "cursor_queue" in low):
            score += 28.0
        if ("写作" in query or "banned" in ql) and ("config" in low or "yaml" in low):
            score += 12.0
        score = _intent_path_bonus(query, path, score)
        if score <= 0:
            continue
        preview_terms = [t for t in term_weight if t in low or t in path.stem.lower()]
        preview = _preview_snippet(text, preview_terms or terms, query)
        rows.append(
            {
                "path": str(path),
                "title": path.stem,
                "preview": preview,
                "score": float(-score),
                "method": "fulltext",
                "_term_hits": score,
            }
        )
    rows.sort(key=lambda x: (x["_term_hits"], len(x["title"])), reverse=True)
    return rows[:limit]


def ask(query: str, limit: int = 5, mode: str = "auto") -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        return []
    mode = mode.lower().strip()
    if mode not in {"auto", "fast", "deep"}:
        mode = "auto"
    txt = _keyword_hits(query=query, limit=max(limit, 8))

    # Fast mode avoids vector fallback completely for responsive CLI usage.
    if mode == "fast":
        out: list[dict[str, Any]] = []
        for row in txt[:limit]:
            item = dict(row)
            item["method"] = "hybrid"
            item.pop("_term_hits", None)
            out.append(item)
        return out

    # Auto mode: when keyword hits are strong enough, skip heavy vector import.
    if mode == "auto" and len(txt) >= limit and sum(float(item.get("_term_hits", 0.0)) for item in txt[:limit]) >= limit * 2:
        out: list[dict[str, Any]] = []
        for row in txt[:limit]:
            item = dict(row)
            item["method"] = "hybrid"
            item.pop("_term_hits", None)
            out.append(item)
        return out

    from brain_memory.vectors import search as vector_search

    vec = vector_search(query=query, limit=max(limit, 8))
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

