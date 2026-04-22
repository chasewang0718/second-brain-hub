from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _roadmap_path() -> Path:
    return _repo_root() / "architecture" / "ROADMAP.md"


def _v6_gate_json() -> Path:
    content_root = Path(load_paths_config()["paths"]["content_root"])
    return content_root / "08-indexes" / "digests" / "v6-gate-report.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def main() -> int:
    gate = _read_json(_v6_gate_json())
    if not gate:
        print(json.dumps({"status": "skipped", "reason": "missing_gate_report"}, ensure_ascii=False, indent=2))
        return 0
    if not bool(gate.get("v6_ready")):
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "v6_not_ready",
                    "a5_consecutive_days": int(((gate.get("a5") or {}).get("consecutive_days") or 0)),
                    "e2_consecutive_days": int(((gate.get("e2") or {}).get("consecutive_days") or 0)),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    path = _roadmap_path()
    raw = path.read_text(encoding="utf-8")
    now_date = datetime.now(UTC).date().isoformat()
    out = raw
    out = out.replace("status: active", "status: stable-v6")
    out = out.replace("# second-brain-hub 优化路线图 (v5 · 零预算全自主)", "# second-brain-hub 优化路线图 (v6 · 稳定运营态)")
    out = out.replace(f"updated: {raw.split('updated: ')[1].splitlines()[0]}", f"updated: {now_date}")
    marker = f"- {now_date}: v6 gate reached ready=true; roadmap promoted to v6 stable operations."
    if marker not in out:
        out += "\n\n## v6 升级记录\n\n" + marker + "\n"
    if out != raw:
        path.write_text(out, encoding="utf-8")
        print(json.dumps({"status": "ok", "updated": True, "roadmap": str(path)}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({"status": "ok", "updated": False, "roadmap": str(path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

