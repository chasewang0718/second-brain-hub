from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from brain_core.config import load_paths_config
from brain_memory.structured import query


def _digest_dir() -> Path:
    content_root = Path(load_paths_config()["paths"]["content_root"])
    out = content_root / "08-indexes" / "digests"
    out.mkdir(parents=True, exist_ok=True)
    return out


def main() -> int:
    now = datetime.now(UTC)
    rows = query(
        """
        SELECT
          p.person_id,
          p.primary_name,
          MAX(i.ts_utc) AS last_interaction_utc,
          COUNT(*) AS interaction_count
        FROM persons p
        JOIN interactions i ON i.person_id = p.person_id
        WHERE i.source_kind = 'whatsapp_ios'
          AND p.primary_name IS NOT NULL
          AND (
            p.primary_name LIKE '%=%'
            OR p.primary_name LIKE '%@lid%'
            OR length(p.primary_name) > 30
          )
        GROUP BY p.person_id, p.primary_name
        ORDER BY last_interaction_utc DESC
        """
    )
    target = _digest_dir() / "whatsapp-lid-residue.md"
    lines = [
        "# WhatsApp LID Residue",
        "",
        f"- generated_utc: {now.isoformat()}",
        f"- residue_count: {len(rows)}",
        "- note: 该文件仅用于可视化长尾协议 ID，不执行自动修复。",
        "",
        "## Residue Samples",
    ]
    if not rows:
        lines.append("- none")
    else:
        for r in rows:
            last_ts = r.get("last_interaction_utc")
            if hasattr(last_ts, "isoformat"):
                last_ts = last_ts.isoformat()
            lines.append(
                f"- `{r.get('person_id')}` · `{r.get('primary_name')}` · interactions={int(r.get('interaction_count') or 0)} · last={last_ts}"
            )
    target.write_text("\n".join(lines), encoding="utf-8")
    print(str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
