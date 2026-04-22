from __future__ import annotations

import json
from pathlib import Path

import yaml

from brain_agents import text_inbox


def _load_cases(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data.get("cases", []))


def run_eval() -> dict:
    case_file = Path(__file__).with_name("text_inbox_eval.yaml")
    cases = _load_cases(case_file)
    rows: list[dict] = []
    passed = 0

    for case in cases:
        cid = str(case.get("id"))
        text = str(case.get("text", ""))
        expect = dict(case.get("expect", {}))

        pii_hits = text_inbox.detect_pii(text)
        route, confidence = text_inbox.classify_route(text)
        status = "blocked" if pii_hits else "archived"
        effective_route = "tier_c_candidate" if pii_hits else route

        ok = True
        if expect.get("status") and status != expect["status"]:
            ok = False
        if expect.get("route") and effective_route != expect["route"]:
            ok = False
        pii_contains = expect.get("pii_contains")
        if pii_contains and pii_contains not in pii_hits:
            ok = False

        if ok:
            passed += 1
        rows.append(
            {
                "id": cid,
                "passed": ok,
                "status": status,
                "route": effective_route,
                "confidence": round(float(confidence), 4),
                "pii_hits": pii_hits,
                "expected": expect,
            }
        )

    total = len(cases)
    ratio = (passed / total) if total else 0.0
    return {
        "cases": total,
        "passed": passed,
        "pass_ratio": round(ratio, 4),
        "target": 1.0,
        "ok": ratio >= 1.0,
        "details": rows,
    }


if __name__ == "__main__":
    report = run_eval()
    print(json.dumps(report, ensure_ascii=False, indent=2))
