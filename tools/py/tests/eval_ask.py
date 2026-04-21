from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml

from brain_agents.ask import ask


def _load_cases(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data.get("cases", []))


def _match_hit(row: dict, expected_any: list[str]) -> bool:
    hay = " ".join(
        [
            str(row.get("path", "")).lower(),
            str(row.get("title", "")).lower(),
            str(row.get("preview", "")).lower(),
        ]
    )
    return any(token.lower() in hay for token in expected_any)


def run_eval(top_k: int = 3) -> dict:
    case_file = Path(__file__).with_name("ask_eval.yaml")
    cases = _load_cases(case_file)
    rows: list[dict] = []
    pass_count = 0
    for case in cases:
        q = case["query"]
        expected = list(case.get("expected_any", []))
        hits = ask(query=q, limit=top_k, mode="auto")
        ok = any(_match_hit(row, expected) for row in hits)
        if ok:
            pass_count += 1
        rows.append(
            {
                "id": case["id"],
                "query": q,
                "passed": ok,
                "top_k": top_k,
                "results": hits,
            }
        )
    ratio = pass_count / len(cases) if cases else 0.0
    return {
        "cases": len(cases),
        "passed": pass_count,
        "topk_hit_ratio": round(ratio, 4),
        "target": 0.8,
        "ok": ratio >= 0.8,
        "details": rows,
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    report = run_eval(top_k=3)
    print(json.dumps(report, ensure_ascii=False, indent=2))
