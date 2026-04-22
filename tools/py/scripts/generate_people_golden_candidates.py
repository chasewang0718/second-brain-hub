from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml

from brain_memory.structured import query


def _is_readable_name(name: str) -> bool:
    v = name.strip()
    if not v or len(v) > 40:
        return False
    if "==" in v or "=" in v:
        return False
    if "/" in v or "+" in v:
        return False
    if re.search(r"[+/=]{2,}", v):
        return False
    if re.fullmatch(r"[A-Z0-9/+=]+", v):
        return False
    if len(v) > 8 and not re.search(r"[a-z\u4e00-\u9fff]", v):
        return False
    # Reject likely encoded payloads with long alnum runs and almost no spacing.
    if len(v) >= 16 and re.fullmatch(r"[A-Za-z0-9+/=]+", v):
        return False
    # Keep names with letters/CJK and limited punctuation.
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", v):
        return False
    bad_ratio = sum(1 for ch in v if not (ch.isalnum() or ch.isspace() or ch in "-_.&@")) / max(1, len(v))
    return bad_ratio < 0.2


def _candidate_names(limit: int = 12) -> list[str]:
    rows = query(
        """
        SELECT p.primary_name AS name, COUNT(i.id) AS interaction_count, MAX(p.last_seen_utc) AS last_seen_utc
        FROM persons p
        LEFT JOIN interactions i ON i.person_id = p.person_id
        WHERE p.primary_name IS NOT NULL AND trim(p.primary_name) <> ''
        GROUP BY 1
        ORDER BY interaction_count DESC, last_seen_utc DESC
        LIMIT 500
        """,
    )
    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not _is_readable_name(name):
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
        if len(names) >= max(1, int(limit)):
            break
    return names


def _build_cases(names: list[str]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for i, name in enumerate(names, start=1):
        slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_") or f"name_{i}"
        slug = slug[:24]
        cases.append(
            {
                "id": f"golden_who_{i}_{slug}",
                "type": "who",
                "input": {"name": name},
                "expect": {"min_results": 1},
            }
        )
        cases.append(
            {
                "id": f"golden_context_{i}_{slug}",
                "type": "context",
                "input": {"name": name, "since_days": 3650, "limit": 5},
                "expect": {
                    "require_contact": True,
                    "require_keys": ["contact", "recent_interactions", "graph_hints"],
                    "graph_hints_status_in": ["ok", "skipped"],
                },
            }
        )
    return cases


def main() -> int:
    out = Path(__file__).resolve().parents[1] / "tests" / "people_eval_golden_candidates.yaml"
    names = _candidate_names(limit=12)
    payload = {
        "version": 1,
        "description": "Auto-generated candidate cases for people_eval_golden.yaml (review before use)",
        "generated_candidates": len(names),
        "cases": _build_cases(names),
    }
    out.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"wrote {out}")
    print("review candidates, then copy selected cases into tools/py/tests/people_eval_golden.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
