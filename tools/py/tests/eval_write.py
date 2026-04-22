from __future__ import annotations

import json
from pathlib import Path

import yaml

from brain_agents import write_assist


def _load_cases(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data.get("cases", []))


def _banned_phrases() -> list[str]:
    root = Path(__file__).resolve().parents[3]
    cfg = yaml.safe_load((root / "config" / "writing-constraints.yaml").read_text(encoding="utf-8"))
    writing = (cfg or {}).get("writing") or {}
    out = writing.get("banned_phrases") or []
    return [str(x) for x in out]


def run_eval() -> dict:
    case_file = Path(__file__).with_name("write_eval.yaml")
    cases = _load_cases(case_file)
    banned = _banned_phrases()
    details: list[dict] = []
    passed = 0

    for case in cases:
        out = write_assist.write_draft(
            topic=str(case["topic"]),
            platform=str(case["platform"]),
            reader=str(case["reader"]),
            engine="template",
            include_provenance=True,
        )
        draft = str(out.get("draft", ""))
        body = draft.split("## 参考", 1)[0]
        paras = [p for p in body.split("\n\n") if p.strip()]
        lower = draft.lower()
        hit_banned = [p for p in banned if p.lower() in lower]

        ok = True
        if out.get("engine") != "template":
            ok = False
        if "## 参考" not in draft:
            ok = False
        if len(paras) > 4:
            ok = False
        if hit_banned:
            ok = False
        if not out.get("provenance"):
            ok = False

        if ok:
            passed += 1
        details.append(
            {
                "id": case["id"],
                "passed": ok,
                "engine": out.get("engine"),
                "paragraphs": len(paras),
                "has_provenance_block": "## 参考" in draft,
                "banned_hits": hit_banned,
                "provenance_count": len(out.get("provenance", [])),
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
        "details": details,
    }


if __name__ == "__main__":
    print(json.dumps(run_eval(), ensure_ascii=False, indent=2))
