"""Manual `brain cloud flush`: spawn cursor-agent with pending cloud_queue summary."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from brain_agents.cloud_queue import TASK_KIND_REGISTRY, list_pending
from brain_core.config import load_paths_config


def flush(*, dry_run: bool = False, agent_cmd: str | None = None) -> dict[str, Any]:
    paths = load_paths_config()["paths"]
    workspace = Path(paths["content_root"]).resolve()

    pending = list_pending(limit=80)
    if not pending:
        return {"status": "empty"}

    lock = workspace / ".brain-autotrigger.lock"
    if lock.exists():
        age_sec = datetime.now().timestamp() - lock.stat().st_mtime
        if age_sec < 15 * 60:
            return {
                "status": "skipped",
                "reason": "lock_recent",
                "lock_age_seconds": round(age_sec, 2),
                "hint": "Another agent run may still be active; remove the lock manually if stale.",
            }

    overview = [
        {"id": x["id"], "task_kind": x["task_kind"], "preview": x.get("payload_preview")}
        for x in pending
    ]
    prompt_lines = [
        "Process pending items from hub structured DB cloud_queue (manual flush).",
        "Tier A workspace root:",
        str(workspace),
        "",
        "Pending tasks (preview truncated):",
        json.dumps(overview, ensure_ascii=False, indent=2),
        "",
        "task_kind reference:",
        json.dumps(TASK_KIND_REGISTRY, ensure_ascii=False, indent=2),
        "",
        "Resolve payloads using stronger models if needed; update Tier A notes when appropriate.",
    ]
    prompt = "\n".join(prompt_lines)

    default_agent = Path(os.environ.get("LOCALAPPDATA", "")) / "cursor-agent" / "agent.cmd"
    bin_path = Path(agent_cmd) if agent_cmd else default_agent
    if not bin_path.exists():
        return {
            "status": "skipped",
            "reason": "cursor_agent_missing",
            "path": str(bin_path),
            "overview": overview,
        }

    if dry_run:
        return {"status": "dry_run", "agent": str(bin_path), "tasks": overview, "prompt_chars": len(prompt)}

    lock.write_text(datetime.now().isoformat(), encoding="utf-8")
    args = [
        str(bin_path),
        "-p",
        "--force",
        "--trust",
        "--workspace",
        str(workspace),
        prompt,
    ]
    try:
        proc = subprocess.run(
            args,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
        )
        log_path = workspace / ".brain-cloud-flush-last.log"
        log_path.write_text(
            f"exit={proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
            encoding="utf-8",
        )
        return {
            "status": "completed",
            "exit_code": proc.returncode,
            "log": str(log_path),
            "tasks_submitted": len(overview),
        }
    finally:
        lock.unlink(missing_ok=True)
