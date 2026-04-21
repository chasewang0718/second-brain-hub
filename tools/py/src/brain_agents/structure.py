"""E1 dry-run structure analyzer and history recorder."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config
from brain_core.telemetry import append_event


def _content_root() -> Path:
    return Path(load_paths_config()["paths"]["content_root"])


def _history_dir() -> Path:
    path = _content_root() / "08-indexes" / "structure-history"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Suggestion:
    kind: str
    target: str
    reason: str
    score: float
    hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {"kind": self.kind, "target": self.target, "reason": self.reason, "score": round(self.score, 2)}
        if self.hint:
            data["hint"] = self.hint
        return data


def _density_hint(directory: Path) -> str:
    child_counts: dict[str, int] = {}
    for path in directory.rglob("*.md"):
        rel = path.relative_to(directory)
        head = rel.parts[0] if rel.parts else "_root"
        child_counts[head] = child_counts.get(head, 0) + 1
    top_children = sorted(child_counts.items(), key=lambda x: x[1], reverse=True)
    if len(top_children) >= 2:
        parts = ", ".join(f"{name}:{count}" for name, count in top_children[:3])
        return f"split by top child folders first ({parts})"

    # If content is mostly flat, suggest splitting by modified month slices.
    month_counts: dict[str, int] = {}
    for path in directory.rglob("*.md"):
        month = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).strftime("%Y-%m")
        month_counts[month] = month_counts.get(month, 0) + 1
    top_months = sorted(month_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    if top_months:
        parts = ", ".join(f"{month}:{count}" for month, count in top_months)
        return f"consider mtime slices or archive split ({parts})"
    return "consider splitting by topic tags extracted from filenames"


def _directory_stats() -> list[tuple[Path, int, float]]:
    rows: list[tuple[Path, int, float]] = []
    now = datetime.now(UTC).timestamp()
    for d in sorted(_content_root().iterdir()):
        if not d.is_dir():
            continue
        md_files = list(d.rglob("*.md"))
        if not md_files:
            continue
        last_mtime = max((f.stat().st_mtime for f in md_files), default=now)
        days_since = (now - last_mtime) / 86400.0
        rows.append((d, len(md_files), days_since))
    return rows


def detect_structure_candidates() -> list[dict[str, Any]]:
    suggestions: list[Suggestion] = []
    for directory, count, stale_days in _directory_stats():
        rel = str(directory.relative_to(_content_root())).replace("\\", "/")
        if count > 40:
            suggestions.append(
                Suggestion(
                    kind="density_split",
                    target=rel,
                    reason=f"{count} markdown files exceed density threshold",
                    score=min(1.0, count / 80.0),
                    hint=_density_hint(directory),
                )
            )
        if count < 3 and stale_days > 90:
            suggestions.append(
                Suggestion(
                    kind="island_archive_candidate",
                    target=rel,
                    reason=f"only {count} files and stale for {int(stale_days)} days",
                    score=min(1.0, stale_days / 365.0),
                )
            )
        if 8 <= count <= 25 and stale_days < 15:
            suggestions.append(
                Suggestion(
                    kind="cluster_link_candidate",
                    target=rel,
                    reason=f"active directory with {count} files likely needs link graph refresh",
                    score=0.55,
                )
            )
    suggestions.sort(key=lambda x: x.score, reverse=True)
    return [item.to_dict() for item in suggestions[:20]]


def structure_history(dry_run: bool = True) -> dict[str, Any]:
    candidates = detect_structure_candidates()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    history_path = _history_dir() / f"{stamp}-structure-dry-run.md"
    lines = [
        "---",
        f"generated_utc: {datetime.now(UTC).isoformat()}",
        f"dry_run: {str(dry_run).lower()}",
        f"candidate_count: {len(candidates)}",
        "---",
        "",
        "# Structure Dry Run Report",
        "",
    ]
    for idx, row in enumerate(candidates, start=1):
        lines.extend(
            [
                f"## {idx}. {row['kind']} · {row['target']}",
                f"- score: {row['score']}",
                f"- reason: {row['reason']}",
                f"- hint: {row.get('hint', 'n/a')}",
                "",
            ]
        )
    history_path.write_text("\n".join(lines), encoding="utf-8")
    append_event(
        source="structure",
        event="dry_run_report",
        detail_json=json.dumps(
            {"dry_run": dry_run, "count": len(candidates), "history_path": str(history_path)}, ensure_ascii=False
        ),
    )
    return {"history_path": str(history_path), "dry_run": dry_run, "candidate_count": len(candidates), "candidates": candidates}

