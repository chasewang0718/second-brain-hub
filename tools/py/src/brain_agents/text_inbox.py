"""A2 MVP text-inbox pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config

PII_RULES: dict[str, str] = {
    "bsn_like": r"\b\d{9}\b",
    "iban_like": r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b",
    "email": r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
    "phone_like": r"\b(?:\+?\d[\d\s-]{8,}\d)\b",
}

ROUTE_KEYWORDS: dict[str, list[str]] = {
    "01-concepts/inbox-auto": ["concept", "principle", "framework", "定义", "原理"],
    "03-projects/inbox-auto": ["project", "roadmap", "milestone", "todo", "需求"],
    "04-journal": ["today", "journal", "reflection", "复盘", "感受"],
}


def _content_root() -> Path:
    return Path(load_paths_config()["paths"]["content_root"])


def _slug(text: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return base[:60] or "inbox-note"


def _read_text(input_path: str) -> str:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")
    return path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")


def detect_pii(text: str) -> list[str]:
    hits: list[str] = []
    for name, pattern in PII_RULES.items():
        if re.search(pattern, text):
            hits.append(name)
    return hits


def classify_route(text: str) -> tuple[str, float]:
    low = text.lower()
    best_route = "99-inbox/_draft"
    best_score = 0
    for route, keywords in ROUTE_KEYWORDS.items():
        score = sum(1 for key in keywords if key.lower() in low)
        if score > best_score:
            best_score = score
            best_route = route
    confidence = min(0.95, 0.45 + 0.15 * best_score)
    if best_score == 0:
        confidence = 0.35
    return best_route, confidence


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
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "inbox note")
    file_name = _slug(first_line) + ".md"
    target = _content_root() / route / file_name
    target.parent.mkdir(parents=True, exist_ok=True)

    labels = ["inbox-auto"]
    if confidence < 0.7:
        labels.append("low-confidence")
        target = _content_root() / "99-inbox" / "_draft" / file_name
        target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text(text, encoding="utf-8")
    result = TextIngestResult(
        source_path=input_path,
        target_path=str(target),
        route=route if confidence >= 0.7 else "99-inbox/_draft",
        confidence=confidence,
        labels=labels,
        pii_hits=[],
        status="archived",
    )
    return result.to_dict()

