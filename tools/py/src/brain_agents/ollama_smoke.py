"""Local Ollama smoke test for people-insight readiness."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ollama import Client

from brain_core.config import load_paths_config


def _digest_dir() -> Path:
    content_root = Path(load_paths_config()["paths"]["content_root"])
    out = content_root / "08-indexes" / "digests"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _client() -> Client:
    host = os.getenv("OLLAMA_HOST", "").strip()
    return Client(host=host) if host else Client()


def _prompts() -> list[tuple[str, str]]:
    return [
        (
            "extract_people",
            "从下面这段聊天中提取人名，返回 JSON: {\"people\":[...]}。\n聊天：明天跟 Hammond 和 Lucy 开会，晚上我再给老王发资料。",
        ),
        (
            "extract_commitments",
            "从下面内容提取承诺事项，返回 JSON: {\"commitments\":[...]}。\n内容：我答应周五前把合同发给你，下周一提醒我联系财务。",
        ),
        (
            "extract_topics",
            "从下面内容提取话题标签，返回 JSON: {\"topics\":[...]}。\n内容：今天聊了 iOS 通讯录导入、微信增量同步、v6 gate 连续达标。",
        ),
    ]


def run_smoke() -> dict[str, Any]:
    from brain_core.ollama_models import brain_fast_model, brain_heavy_model

    now = datetime.now(UTC)
    cli = _client()
    fast_m = os.getenv("BRAIN_OLLAMA_SMOKE_FAST", "").strip() or brain_fast_model()
    heavy_m = os.getenv("BRAIN_OLLAMA_SMOKE_HEAVY", "").strip() or brain_heavy_model()
    legacy = os.getenv("BRAIN_OLLAMA_SMOKE_MODEL", "").strip()
    if legacy:
        fast_m = legacy
        heavy_m = legacy

    model_results: list[dict[str, Any]] = []
    status = "ok"
    reason = ""

    def _ping(model: str, tag: str) -> dict[str, Any]:
        prompt = (
            _prompts()[0][1]
            + '\nReply with ONE JSON object only, no markdown fence, keys as specified above.'
        )
        out = cli.generate(model=model, prompt=prompt)
        if hasattr(out, "response"):
            txt = str(getattr(out, "response") or "").strip()
        elif isinstance(out, dict):
            txt = str(out.get("response", "")).strip()
        else:
            txt = str(out).strip()
        preview = txt[:800]
        try:
            parsed = json.loads(preview.lstrip())
            json_ok = isinstance(parsed, dict)
        except Exception:
            json_ok = False
        return {"tag": tag, "model": model, "json_ok": json_ok, "preview": preview}

    try:
        model_results.append(_ping(fast_m, "fast"))
        if fast_m != heavy_m:
            model_results.append(_ping(heavy_m, "heavy"))
    except Exception as exc:
        status = "skipped"
        reason = f"{type(exc).__name__}: {exc}"

    ok_count = sum(1 for r in model_results if r.get("json_ok"))
    target = _digest_dir() / f"ollama-smoke-{now.date().isoformat()}.md"
    lines = [
        "# Ollama Smoke",
        "",
        f"- generated_utc: {now.isoformat()}",
        f"- status: {status}",
        f"- fast_model: {fast_m}",
        f"- heavy_model: {heavy_m}",
        f"- cases_per_model: 1 (extract_people)",
        f"- cases_json_ok: {ok_count}",
    ]
    if reason:
        lines.append(f"- reason: {reason}")
    lines.extend(["", "## Models"])
    for r in model_results:
        lines.append(f"### {r.get('tag')}: `{r.get('model')}` json_ok={r.get('json_ok')}")
        lines.extend(["```", (r.get("preview") or "")[:1200], "```", ""])

    target.write_text("\n".join(lines), encoding="utf-8")

    return {
        "status": status,
        "path": str(target),
        "fast_model": fast_m,
        "heavy_model": heavy_m,
        "models_tested": model_results,
        "cases_json_ok": ok_count,
        "reason": reason,
    }
