"""Integration tests for identifiers repair (email/wxid lowercase + dry-run purity)."""

from __future__ import annotations

import uuid

from brain_agents.identity_resolver import run_identifiers_repair
from brain_memory.structured import execute, fetch_one, query


def test_email_repair_fixes_mixed_case_normalized_value() -> None:
    pid = f"p_{uuid.uuid4().hex[:12]}"
    execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES (?, 'Repair Test Person', '[]', '[]', CURRENT_TIMESTAMP)
        """,
        [pid],
    )
    execute(
        """
        INSERT INTO person_identifiers (person_id, kind, value_normalized, value_original, confidence, source_kind)
        VALUES (?, 'email', 'OldMixed@Example.COM', 'OldMixed@Example.COM', 1.0, 'test')
        """,
        [pid],
    )

    rep = run_identifiers_repair(kinds={"email"}, dry_run=False)
    assert rep["status"] == "ok"
    assert rep["results"]["email"]["updated"] >= 1

    row = fetch_one(
        "SELECT value_normalized FROM person_identifiers WHERE person_id = ? AND lower(kind) = 'email'",
        [pid],
    )
    assert row and row["value_normalized"] == "oldmixed@example.com"

    execute("DELETE FROM person_identifiers WHERE person_id = ?", [pid])
    execute("DELETE FROM persons WHERE person_id = ?", [pid])


# --- B-ING-1.10: dry-run must not write merge_candidates + pair-level dedupe.


def _seed_collision_pair(
    pa: str,
    pb: str,
    a_canonical: str,
    b_legacy: str,
    kind: str = "email",
) -> None:
    """Seed a cross-person collision: A already canonical, B still stale.

    Repair will re-normalize B, spot that the new normalized form matches A's
    existing ``value_normalized``, and enqueue a merge_candidate (without
    actually merging — that's T2's job).
    """
    execute(
        "INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc) "
        "VALUES (?, 'T Repair 1.10', '[]', '[]', CURRENT_TIMESTAMP)",
        [pa],
    )
    execute(
        "INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc) "
        "VALUES (?, 'T Repair 1.10', '[]', '[]', CURRENT_TIMESTAMP)",
        [pb],
    )
    execute(
        "INSERT INTO person_identifiers (person_id, kind, value_normalized, value_original, confidence, source_kind) "
        "VALUES (?, ?, ?, ?, 1.0, 'test')",
        [pa, kind, a_canonical, a_canonical],
    )
    execute(
        "INSERT INTO person_identifiers (person_id, kind, value_normalized, value_original, confidence, source_kind) "
        "VALUES (?, ?, ?, ?, 1.0, 'test')",
        [pb, kind, b_legacy, b_legacy],
    )


def _cleanup(pids: list[str]) -> None:
    for p in pids:
        execute("DELETE FROM person_identifiers WHERE person_id = ?", [p])
        execute("DELETE FROM persons WHERE person_id = ?", [p])
    execute(
        "DELETE FROM merge_candidates WHERE person_a IN ({}) OR person_b IN ({})".format(
            ",".join(["?"] * len(pids)), ",".join(["?"] * len(pids))
        ),
        pids + pids,
    )


def test_repair_dry_run_does_not_write_merge_candidates() -> None:
    pa = f"p_{uuid.uuid4().hex[:12]}"
    pb = f"p_{uuid.uuid4().hex[:12]}"
    _seed_collision_pair(pa, pb, "dryrun110@example.com", "DRYrun110@Example.COM")

    before = query(
        "SELECT id FROM merge_candidates WHERE person_a IN (?, ?) OR person_b IN (?, ?)",
        [pa, pb, pa, pb],
    )
    rep = run_identifiers_repair(kinds={"email"}, dry_run=True)
    after = query(
        "SELECT id FROM merge_candidates WHERE person_a IN (?, ?) OR person_b IN (?, ?)",
        [pa, pb, pa, pb],
    )

    try:
        assert rep["status"] == "dry_run"
        # would-enqueue accounting still reports the pair
        assert rep["results"]["email"]["merge_candidates"] == 1
        # but the DB must not have grown
        assert len(before) == len(after), f"dry-run wrote merge_candidates: {len(before)} -> {len(after)}"
    finally:
        _cleanup([pa, pb])


def test_repair_pair_dedupe_multiple_rows_same_pair() -> None:
    # person B has 3 distinct uppercase emails — all three lowercase to "shared110@…"
    # which is exactly person A's already-canonical value. Before B-ING-1.10, three
    # separate (A,B) rows would be inserted. After 1.10 there's only one.
    pa = f"p_{uuid.uuid4().hex[:12]}"
    pb = f"p_{uuid.uuid4().hex[:12]}"
    execute(
        "INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc) "
        "VALUES (?, 'T 1.10 PairA', '[]', '[]', CURRENT_TIMESTAMP)",
        [pa],
    )
    execute(
        "INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc) "
        "VALUES (?, 'T 1.10 PairB', '[]', '[]', CURRENT_TIMESTAMP)",
        [pb],
    )
    # A is already canonical — it's the "target" the rest should fold into.
    execute(
        "INSERT INTO person_identifiers (person_id, kind, value_normalized, value_original, confidence, source_kind) "
        "VALUES (?, 'email', 'shared110@example.com', 'shared110@example.com', 1.0, 'test')",
        [pa],
    )
    # B has three uppercase twins; all three will lowercase to A's canonical form.
    for raw in ["Shared110@Example.com", "ShAred110@Example.com", "SHARED110@example.com"]:
        execute(
            "INSERT INTO person_identifiers (person_id, kind, value_normalized, value_original, confidence, source_kind) "
            "VALUES (?, 'email', ?, ?, 1.0, 'test')",
            [pb, raw, raw],
        )

    try:
        rep = run_identifiers_repair(kinds={"email"}, dry_run=False)
        assert rep["status"] == "ok"
        rows = query(
            "SELECT id FROM merge_candidates WHERE (person_a = ? AND person_b = ?) OR (person_a = ? AND person_b = ?)",
            [*sorted([pa, pb]), *sorted([pa, pb])[::-1]],
        )
        assert len(rows) == 1, f"expected 1 merge_candidate for the pair, got {len(rows)}"
        assert rep["results"]["email"]["merge_candidates"] == 1
        assert rep["results"]["email"]["merge_candidate_collisions"] >= 3
        assert rep["results"]["email"]["merge_candidate_skipped_existing"] >= 2
    finally:
        _cleanup([pa, pb])


def test_repair_pair_dedupe_second_run_is_noop() -> None:
    pa = f"p_{uuid.uuid4().hex[:12]}"
    pb = f"p_{uuid.uuid4().hex[:12]}"
    _seed_collision_pair(pa, pb, "rerun110@ex.com", "Rerun110@EX.com")

    try:
        rep1 = run_identifiers_repair(kinds={"email"}, dry_run=False)
        rep2 = run_identifiers_repair(kinds={"email"}, dry_run=False)

        # first run enqueues once, second run sees existing pair and skips
        assert rep1["results"]["email"]["merge_candidates"] == 1
        assert rep2["results"]["email"]["merge_candidates"] == 0
        assert rep2["results"]["email"]["merge_candidate_skipped_existing"] >= 1

        rows = query(
            "SELECT id FROM merge_candidates WHERE (person_a = ? AND person_b = ?) OR (person_a = ? AND person_b = ?)",
            [*sorted([pa, pb]), *sorted([pa, pb])[::-1]],
        )
        assert len(rows) == 1
    finally:
        _cleanup([pa, pb])


def test_wxid_repair_fixes_case() -> None:
    pid = f"p_{uuid.uuid4().hex[:12]}"
    execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES (?, 'Wx Repair', '[]', '[]', CURRENT_TIMESTAMP)
        """,
        [pid],
    )
    execute(
        """
        INSERT INTO person_identifiers (person_id, kind, value_normalized, value_original, confidence, source_kind)
        VALUES (?, 'wxid', 'WxId_ForceCase', 'WxId_ForceCase', 1.0, 'test')
        """,
        [pid],
    )

    rep = run_identifiers_repair(kinds={"wxid"}, dry_run=False)
    assert rep["status"] == "ok"
    assert rep["results"]["wxid"]["updated"] >= 1

    row = fetch_one(
        "SELECT value_normalized FROM person_identifiers WHERE person_id = ? AND lower(kind) = 'wxid'",
        [pid],
    )
    assert row and row["value_normalized"] == "wxid_forcecase"

    execute("DELETE FROM person_identifiers WHERE person_id = ?", [pid])
    execute("DELETE FROM persons WHERE person_id = ?", [pid])
