"""A2 MVP text-inbox pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from brain_core.config import load_paths_config, load_thresholds_config

# Fallbacks if thresholds.yaml omits keys (same values as config/thresholds.yaml defaults).
_FALLBACK_ROUTE_KEYWORDS: dict[str, list[str]] = {
    "01-concepts/inbox-auto": ["concept", "principle", "framework", "定义", "原理"],
    "03-projects/inbox-auto": ["project", "roadmap", "milestone", "todo", "需求"],
    "04-journal": ["today", "journal", "reflection", "复盘", "感受"],
}
_FALLBACK_PII: dict[str, str] = {
    "bsn_like": r"\b\d{9}\b",
    "iban_like": r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b",
    "email": r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
    "phone_like": r"\b(?:\+?\d[\d\s-]{8,}\d)\b",
}


def _text_inbox_cfg() -> dict[str, Any]:
    root = load_thresholds_config()
    ti = root.get("text_inbox")
    if not isinstance(ti, dict):
        ti = {}
    conf = ti.get("confidence")
    if not isinstance(conf, dict):
        conf = {}
    paths = ti.get("paths")
    if not isinstance(paths, dict):
        paths = {}
    fn = ti.get("filename")
    if not isinstance(fn, dict):
        fn = {}
    rk = ti.get("route_keywords")
    if not isinstance(rk, dict) or not rk:
        rk = dict(_FALLBACK_ROUTE_KEYWORDS)
    else:
        rk = {str(k): [str(x) for x in v] if isinstance(v, list) else [] for k, v in rk.items()}
    pii = ti.get("pii_patterns")
    if not isinstance(pii, dict) or not pii:
        pii = dict(_FALLBACK_PII)
    else:
        pii = {str(k): str(v) for k, v in pii.items()}
    fm = ti.get("frontmatter_routing")
    if not isinstance(fm, dict):
        fm = {}
    return {
        "confidence": {
            "promote_min": float(conf.get("promote_min", 0.7)),
            "empty_keyword_score": float(conf.get("empty_keyword_score", 0.35)),
            "base": float(conf.get("base", 0.45)),
            "per_keyword_hit": float(conf.get("per_keyword_hit", 0.15)),
            "cap": float(conf.get("cap", 0.95)),
        },
        "paths": {
            "draft_route": str(paths.get("draft_route", "99-inbox/_draft")),
            "default_unclassified_route": str(
                paths.get("default_unclassified_route", "99-inbox/_draft")
            ),
        },
        "filename": {
            "slug_max_length": int(fn.get("slug_max_length", 60)),
            "first_line_fallback": str(fn.get("first_line_fallback", "inbox note")),
            "prefer_frontmatter_title": bool(fn.get("prefer_frontmatter_title", False)),
            "frontmatter_title_keys": [
                str(x) for x in fn.get("frontmatter_title_keys", ["title", "subject"])
            ]
            if isinstance(fn.get("frontmatter_title_keys"), list)
            else ["title", "subject"],
        },
        "route_keywords": rk,
        "pii_patterns": pii,
        "frontmatter_routing": {"enabled": bool(fm.get("enabled", False))},
    }


def _content_root() -> Path:
    return Path(load_paths_config()["paths"]["content_root"])


def _slug(text: str, max_len: int) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    cap = max(1, max_len)
    return base[:cap] or "inbox-note"


def _read_text(input_path: str) -> str:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")
    return path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")


def _split_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """If file starts with YAML frontmatter, return (parsed dict, body after closing ---)."""
    t = text.lstrip("\ufeff")
    if not t.startswith("---"):
        return None, text
    lines = t.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    i = 1
    chunk: list[str] = []
    while i < len(lines):
        if lines[i].strip() == "---":
            i += 1
            break
        chunk.append(lines[i])
        i += 1
    else:
        return None, text
    blob = "\n".join(chunk)
    try:
        data = yaml.safe_load(blob) if blob.strip() else {}
    except yaml.YAMLError:
        return None, text
    if not isinstance(data, dict):
        return None, text
    rest = "\n".join(lines[i:])
    return data, rest


def _aux_from_frontmatter(fm: dict[str, Any]) -> str:
    parts: list[str] = []
    tags = fm.get("tags")
    if isinstance(tags, list):
        parts.append(" ".join(str(x) for x in tags))
    elif isinstance(tags, str):
        parts.append(tags)
    t = fm.get("title")
    if isinstance(t, str):
        parts.append(t)
    return " ".join(parts)


def detect_pii(text: str) -> list[str]:
    cfg = _text_inbox_cfg()
    hits: list[str] = []
    for name, pattern in cfg["pii_patterns"].items():
        if re.search(pattern, text):
            hits.append(name)
    return hits


def classify_route(text: str) -> tuple[str, float]:
    cfg = _text_inbox_cfg()
    c = cfg["confidence"]
    default_route = cfg["paths"]["default_unclassified_route"]
    low = text.lower()
    fm, _rest = _split_frontmatter(text)
    fm_enabled = cfg["frontmatter_routing"]["enabled"]
    aux_l = ""
    if fm_enabled and fm:
        aux_l = _aux_from_frontmatter(fm).lower()

    best_route = default_route
    best_score = 0
    for route, keywords in cfg["route_keywords"].items():
        score = sum(1 for key in keywords if key.lower() in low)
        if fm_enabled and aux_l:
            score += sum(
                1
                for key in keywords
                if key.lower() in aux_l and key.lower() not in low
            )
        if score > best_score:
            best_score = score
            best_route = route
    confidence = min(c["cap"], c["base"] + c["per_keyword_hit"] * best_score)
    if best_score == 0:
        confidence = c["empty_keyword_score"]
    return best_route, confidence


def _slug_source_line(text: str) -> str:
    fn = _text_inbox_cfg()["filename"]
    if fn["prefer_frontmatter_title"]:
        fm, after = _split_frontmatter(text)
        if fm:
            for key in fn["frontmatter_title_keys"]:
                v = fm.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return next(
            (line.strip() for line in after.splitlines() if line.strip()),
            fn["first_line_fallback"],
        )
    return next(
        (line.strip() for line in text.splitlines() if line.strip()),
        fn["first_line_fallback"],
    )


@dataclass
class TextIngestResult:
    source_path: str
    target_path: str
    route: str
    confidence: float
    labels: list[str]
    pii_hits: list[str]
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "target_path": self.target_path,
            "route": self.route,
            "confidence": round(self.confidence, 2),
            "labels": self.labels,
            "pii_hits": self.pii_hits,
            "status": self.status,
        }


def ingest_file(input_path: str) -> dict[str, Any]:
    text = _read_text(input_path)
    cfg = _text_inbox_cfg()
    promote_min = cfg["confidence"]["promote_min"]
    draft_route = cfg["paths"]["draft_route"]
    slug_max = cfg["filename"]["slug_max_length"]

    pii_hits = detect_pii(text)
    if pii_hits:
        result = TextIngestResult(
            source_path=input_path,
            target_path="",
            route="tier_c_candidate",
            confidence=1.0,
            labels=["tier_c_candidate", "pii_detected"],
            pii_hits=pii_hits,
            status="blocked",
        )
        return result.to_dict()

    route, confidence = classify_route(text)
    first_line = _slug_source_line(text)
    file_name = _slug(first_line, slug_max) + ".md"
    target = _content_root().joinpath(*route.split("/")) / file_name
    target.parent.mkdir(parents=True, exist_ok=True)

    labels = ["inbox-auto"]
    if confidence < promote_min:
        labels.append("low-confidence")
        target = _content_root().joinpath(*draft_route.split("/")) / file_name
        target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text(text, encoding="utf-8")
    result = TextIngestResult(
        source_path=input_path,
        target_path=str(target),
        route=route if confidence >= promote_min else draft_route,
        confidence=confidence,
        labels=labels,
        pii_hits=[],
        status="archived",
    )
    data = result.to_dict()
    if result.status == "archived":
        from brain_agents.inbox_people import apply_people_postprocess

        data["people"] = apply_people_postprocess(Path(result.target_path), text)
    return data
