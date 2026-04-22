"""Derived per-person metrics recomputed from interactions (Phase A6 Sprint 1).

This is an overwrite-style derived table: every call to ``recompute_all()``
nukes and rebuilds rows for every ``person_id`` with at least one row in
``interactions``. Because the source of truth is ``interactions``, this
table can be dropped at any time and re-materialised at low cost (one
full scan of interactions per rebuild).

Fields (match ``person_metrics`` schema in brain_memory.structured):

- ``first_seen_utc`` / ``last_seen_utc`` — min/max ``ts_utc``
- ``last_interaction_channel`` — channel of the most recent interaction
- ``interactions_all`` / ``_30d`` / ``_90d`` — counts over rolling windows
- ``distinct_channels_30d`` — distinct non-empty channels in the last 30d
- ``dormancy_days`` — whole days since ``last_seen_utc``; NULL if never seen
- ``computed_at`` — wall-clock timestamp of this recompute
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from brain_memory.structured import ensure_schema, execute, fetch_one, query, transaction


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _dormancy_days(last_seen: Any, now: datetime) -> int | None:
    if last_seen is None:
        return None
    if isinstance(last_seen, datetime):
        ls = last_seen.replace(tzinfo=None) if last_seen.tzinfo else last_seen
    else:
        try:
            ls = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None
    delta = now - ls
    return max(0, int(delta.total_seconds() // 86400))


def _aggregate_rows(person_id: str | None, now: datetime) -> list[dict[str, Any]]:
    cutoff_30 = now - timedelta(days=30)
    cutoff_90 = now - timedelta(days=90)
    where_pid = ""
    params: list[Any] = []
    if person_id:
        where_pid = " AND person_id = ?"
        params.append(person_id)
    params.extend([cutoff_30, cutoff_90, cutoff_30])
    sql = f"""
        WITH base AS (
            SELECT person_id, ts_utc,
                   COALESCE(NULLIF(trim(channel), ''), NULL) AS channel_norm
            FROM interactions
            WHERE person_id IS NOT NULL
              AND trim(person_id) <> ''{where_pid}
        ),
        agg AS (
            SELECT
                person_id,
                min(ts_utc) AS first_seen_utc,
                max(ts_utc) AS last_seen_utc,
                count(*) AS interactions_all,
                sum(CASE WHEN ts_utc >= ? THEN 1 ELSE 0 END) AS interactions_30d,
                sum(CASE WHEN ts_utc >= ? THEN 1 ELSE 0 END) AS interactions_90d,
                count(DISTINCT CASE WHEN ts_utc >= ? THEN lower(channel_norm) END) AS distinct_channels_30d
            FROM base
            GROUP BY person_id
        ),
        last_ch AS (
            SELECT person_id, channel_norm AS last_channel FROM (
                SELECT person_id, channel_norm,
                       row_number() OVER (PARTITION BY person_id ORDER BY ts_utc DESC, channel_norm) AS rn
                FROM base
            ) t WHERE rn = 1
        )
        SELECT
            a.person_id,
            a.first_seen_utc,
            a.last_seen_utc,
            COALESCE(lc.last_channel, '') AS last_interaction_channel,
            a.interactions_all,
            a.interactions_30d,
            a.interactions_90d,
            a.distinct_channels_30d
        FROM agg a
        LEFT JOIN last_ch lc ON lc.person_id = a.person_id
    """
    return query(sql, params)


def _upsert_rows(conn: Any, rows: list[dict[str, Any]], *, now: datetime) -> int:
    updated = 0
    for r in rows:
        pid = str(r["person_id"])
        dormancy = _dormancy_days(r.get("last_seen_utc"), now)
        conn.execute("DELETE FROM person_metrics WHERE person_id = ?", [pid])
        conn.execute(
            """
            INSERT INTO person_metrics (
                person_id, first_seen_utc, last_seen_utc,
                last_interaction_channel,
                interactions_all, interactions_30d, interactions_90d,
                distinct_channels_30d, dormancy_days, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                pid,
                r.get("first_seen_utc"),
                r.get("last_seen_utc"),
                str(r.get("last_interaction_channel") or ""),
                int(r.get("interactions_all") or 0),
                int(r.get("interactions_30d") or 0),
                int(r.get("interactions_90d") or 0),
                int(r.get("distinct_channels_30d") or 0),
                dormancy,
                now,
            ],
        )
        updated += 1
    return updated


def recompute_one(person_id: str) -> dict[str, Any]:
    pid = (person_id or "").strip()
    if not pid:
        return {"status": "error", "reason": "missing person_id"}
    ensure_schema()
    now = _utc_now()
    rows = _aggregate_rows(pid, now)
    if not rows:
        with transaction() as conn:
            conn.execute("DELETE FROM person_metrics WHERE person_id = ?", [pid])
        return {
            "status": "ok",
            "person_id": pid,
            "updated": 0,
            "cleared": 1,
            "reason": "no_interactions",
            "computed_at": str(now),
        }
    with transaction() as conn:
        _upsert_rows(conn, rows, now=now)
    row = fetch_one("SELECT * FROM person_metrics WHERE person_id = ?", [pid])
    return {
        "status": "ok",
        "person_id": pid,
        "updated": 1,
        "metrics": row,
        "computed_at": str(now),
    }


def recompute_all(*, remove_orphans: bool = True) -> dict[str, Any]:
    """Rebuild person_metrics for every person with at least one interaction.

    When ``remove_orphans=True`` (default), also DELETE rows in
    ``person_metrics`` whose person_id no longer appears in ``interactions``
    (e.g. after a merge absorbed them).
    """
    ensure_schema()
    now = _utc_now()
    rows = _aggregate_rows(None, now)
    with transaction() as conn:
        updated = _upsert_rows(conn, rows, now=now)
        removed = 0
        if remove_orphans:
            res = conn.execute(
                """
                DELETE FROM person_metrics
                WHERE person_id NOT IN (
                    SELECT DISTINCT person_id FROM interactions
                    WHERE person_id IS NOT NULL AND trim(person_id) <> ''
                )
                """
            )
            # DuckDB returns affected rows via rowcount on some builds; fall back to a probe.
            try:
                removed = int(res.rowcount or 0)  # type: ignore[attr-defined]
            except Exception:
                removed = 0
    total = fetch_one("SELECT count(*) AS n FROM person_metrics")
    return {
        "status": "ok",
        "updated": updated,
        "removed_orphans": removed,
        "total_rows": int((total or {}).get("n") or 0),
        "computed_at": str(now),
    }


def get_metrics(person_id: str) -> dict[str, Any] | None:
    pid = (person_id or "").strip()
    if not pid:
        return None
    ensure_schema()
    return fetch_one("SELECT * FROM person_metrics WHERE person_id = ?", [pid])
