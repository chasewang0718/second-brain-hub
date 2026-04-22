from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config


def _digest_dir() -> Path:
    content_root = Path(load_paths_config()["paths"]["content_root"])
    out_dir = content_root / "08-indexes" / "digests"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _to_date(value: str) -> date | None:
    txt = (value or "").strip()
    if not txt:
        return None
    txt = txt.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(txt).astimezone(UTC).date()
    except ValueError:
        return None


def _consecutive_days_from_today(days: set[date], today: date) -> int:
    cur = today
    n = 0
    while cur in days:
        n += 1
        cur = cur - timedelta(days=1)
    return n


def _a5_days(today: date) -> tuple[int, int]:
    dig = _digest_dir()
    eval_rows = _parse_jsonl(dig / "people-eval-history.jsonl")
    delta_rows = _parse_jsonl(dig / "relationship-deltas-history.jsonl")

    eval_green_days = {
        d
        for r in eval_rows
        for d in [_to_date(str(r.get("ts_utc") or ""))]
        if d is not None and int(r.get("failed") or 0) == 0
    }
    delta_days = {
        d
        for r in delta_rows
        for d in [_to_date(str(r.get("ts_utc") or ""))]
        if d is not None
    }
    a5_days = eval_green_days & delta_days
    return _consecutive_days_from_today(a5_days, today), len(a5_days)


def _e2_days(today: date) -> tuple[int, int]:
    dig = _digest_dir()
    daily_days = {d for i in range(0, 30) for d in [today - timedelta(days=i)] if (dig / f"daily-{d.isoformat()}.md").exists()}
    relationship_days = {
        d for i in range(0, 30) for d in [today - timedelta(days=i)] if (dig / f"relationship-alerts-{d.isoformat()}.md").exists()
    }
    # weekly/budget are not daily; treat existence in recent window as base readiness.
    weekly_ok = any((dig / f"weekly-{(today - timedelta(days=i)).year}-W{(today - timedelta(days=i)).isocalendar().week:02d}.md").exists() for i in range(0, 30))
    budget_ok = any((dig / f"budget-{(today - timedelta(days=i)).isoformat()}.md").exists() for i in range(0, 30))

    if not weekly_ok or not budget_ok:
        return 0, 0
    e2_days = daily_days & relationship_days
    return _consecutive_days_from_today(e2_days, today), len(e2_days)


def _kuzu_lock_probe(now: datetime) -> dict[str, Any]:
    """Best-effort scan for recent Kuzu lock errors in runtime logs."""
    logs_dir = Path(load_paths_config()["paths"]["telemetry_logs_dir"])
    keywords_any = ("kuzu", "graph", "lock")
    hard_tokens = (
        "io error",
        "busy",
        "locked",
        "cannot obtain lock",
        "cannot open",
        "single writer",
    )
    cutoff = now - timedelta(hours=24)
    hit_count = 0
    files_scanned = 0
    samples: list[str] = []
    if not logs_dir.exists():
        return {"status": "missing_log_dir", "hours": 24, "hits": 0, "files_scanned": 0, "samples": []}
    for path in sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        except OSError:
            continue
        if mtime < cutoff:
            continue
        files_scanned += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            txt = line.lower()
            if not any(k in txt for k in keywords_any):
                continue
            if any(t in txt for t in hard_tokens):
                hit_count += 1
                if len(samples) < 5:
                    samples.append(f"{path.name}: {line.strip()[:180]}")
    return {
        "status": "ok",
        "hours": 24,
        "hits": hit_count,
        "files_scanned": files_scanned,
        "has_recent_lock_error": hit_count > 0,
        "samples": samples,
    }


def _append_history(dig: Path, row: dict[str, Any]) -> Path:
    path = dig / "v6-gate-history.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _recent_history(path: Path, days: int = 7) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for r in rows:
        d = _to_date(str(r.get("generated_utc") or ""))
        if d is None:
            continue
        dt = datetime.combine(d, datetime.min.time(), tzinfo=UTC)
        if dt >= cutoff:
            out.append(r)
    return out[-days:]


def _spark(values: list[int]) -> str:
    ticks = "▁▂▃▄▅▆▇█"
    if not values:
        return "n/a"
    lo, hi = min(values), max(values)
    if hi == lo:
        idx = 0 if hi <= 0 else min(7, hi)
        return "".join(ticks[idx] for _ in values)
    out = []
    for v in values:
        pos = int((v - lo) * 7 / max(1, (hi - lo)))
        out.append(ticks[max(0, min(7, pos))])
    return "".join(out)


def main() -> int:
    now = datetime.now(UTC)
    today = now.date()
    a5_consecutive, a5_total = _a5_days(today)
    e2_consecutive, e2_total = _e2_days(today)
    kuzu_probe = _kuzu_lock_probe(now)
    a5_pass = a5_consecutive >= 7
    e2_pass = e2_consecutive >= 7
    v6_ready = a5_pass and e2_pass

    out = {
        "status": "ok",
        "generated_utc": now.isoformat(),
        "a5": {"consecutive_days": a5_consecutive, "days_seen": a5_total, "pass": a5_pass},
        "e2": {"consecutive_days": e2_consecutive, "days_seen": e2_total, "pass": e2_pass},
        "kuzu_lock_probe": kuzu_probe,
        "v6_ready": v6_ready,
    }
    dig = _digest_dir()
    history_path = _append_history(
        dig,
        {
            "generated_utc": out["generated_utc"],
            "a5_consecutive_days": a5_consecutive,
            "e2_consecutive_days": e2_consecutive,
            "v6_ready": v6_ready,
        },
    )
    hist = _recent_history(history_path, days=7)
    a5_curve = [int(r.get("a5_consecutive_days") or 0) for r in hist]
    e2_curve = [int(r.get("e2_consecutive_days") or 0) for r in hist]
    ready_curve = [1 if bool(r.get("v6_ready")) else 0 for r in hist]
    md_path = dig / "v6-gate-report.md"
    json_path = dig / "v6-gate-report.json"
    md_lines = [
        "# V6 Gate Report",
        "",
        f"- generated_utc: {out['generated_utc']}",
        f"- a5_consecutive_days: {a5_consecutive} (target: 7)",
        f"- e2_consecutive_days: {e2_consecutive} (target: 7)",
        f"- kuzu_recent_lock_errors_24h: {kuzu_probe.get('hits', 0)}",
        f"- v6_ready: {v6_ready}",
        "",
        "## Runtime Probe",
        (
            "- Kuzu lock probe: no recent lock signals in runtime logs."
            if not kuzu_probe.get("has_recent_lock_error")
            else "- Kuzu lock probe: recent lock-like signals detected; check runtime logs."
        ),
        "",
        "## 7d Trend",
        f"- a5_consecutive_days: {_spark(a5_curve)}",
        f"- e2_consecutive_days: {_spark(e2_curve)}",
        f"- v6_ready: {_spark(ready_curve)}",
        "",
        "## Decision",
        "- Upgrade to v6 now." if v6_ready else "- Keep running daily loop until both A5/E2 reach 7 consecutive days.",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "md_path": str(md_path), "json_path": str(json_path), **out}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
