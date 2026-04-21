"""Tests for ``brain_agents.merge_candidates.sync_from_graph``.

We stub the Kuzu side (``_enumerate_shared_identifier_pairs``) so these
tests do not require kuzu to be installed or a graph to be built.
"""

from __future__ import annotations

import pytest

from brain_agents import merge_candidates as mc
from brain_memory.structured import execute, fetch_one, query


# All test person_ids share this prefix so the autouse fixture can
# clean them up without touching real CRM data that happens to live
# in the same DuckDB file during local dev.
_TEST_PID_PREFIX = "pytest_mcsync_"


@pytest.fixture(autouse=True)
def _clean_tables():
    """Keep merge_candidates + merge_log state isolated for each test,
    and scrub any test-seeded persons rows.
    """
    def _scrub():
        # merge_log / merge_candidates rows produced by this test module
        # are anchored on persons whose IDs start with our prefix.
        execute(
            f"DELETE FROM merge_candidates WHERE person_a LIKE '{_TEST_PID_PREFIX}%' "
            f"OR person_b LIKE '{_TEST_PID_PREFIX}%'"
        )
        execute(
            f"DELETE FROM merge_log WHERE kept_person_id LIKE '{_TEST_PID_PREFIX}%' "
            f"OR absorbed_person_id LIKE '{_TEST_PID_PREFIX}%'"
        )
        execute(f"DELETE FROM persons WHERE person_id LIKE '{_TEST_PID_PREFIX}%'")
        # Drop unrelated test-scope rows in merge_candidates / merge_log
        # that the existing tests below create with ad-hoc ids like
        # p_a / p_b / p_c / p_d / p_e / p_f so we don't cross-pollute.
        legacy_ids = ("p_a", "p_b", "p_c", "p_d", "p_e", "p_f")
        placeholders = ",".join(["?"] * len(legacy_ids))
        execute(
            f"DELETE FROM merge_candidates WHERE person_a IN ({placeholders}) "
            f"OR person_b IN ({placeholders})",
            list(legacy_ids) + list(legacy_ids),
        )
        execute(
            f"DELETE FROM merge_log WHERE kept_person_id IN ({placeholders}) "
            f"OR absorbed_person_id IN ({placeholders})",
            list(legacy_ids) + list(legacy_ids),
        )

    _scrub()
    yield
    _scrub()


def test_sync_skipped_when_kuzu_missing(monkeypatch):
    def raise_missing():
        raise RuntimeError("kuzu_missing:ModuleNotFoundError")

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", raise_missing)
    out = mc.sync_from_graph(dry_run=True)
    assert out["status"] == "skipped"
    assert "kuzu_missing" in out["reason"]
    assert out["dry_run"] is True


def test_sync_dry_run_does_not_write(monkeypatch):
    def fake_pairs():
        return [
            {"person_a": "p_a", "person_b": "p_b", "kind": "phone", "value": "8613800138000"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=True)
    assert out["status"] == "ok"
    assert out["proposed"] == 1
    assert out["inserted"] == 0
    assert out["samples"][0]["score"] == pytest.approx(0.95)
    assert out["samples"][0]["reason"].startswith("graph:shared_identifier:phone")

    # nothing actually inserted for our scoped test ids
    rows = query(
        "SELECT COUNT(*) AS c FROM merge_candidates WHERE person_a IN ('p_a', 'p_b') "
        "OR person_b IN ('p_a', 'p_b')"
    )
    assert int(rows[0]["c"]) == 0


def test_sync_apply_inserts_pending_row(monkeypatch):
    def fake_pairs():
        return [
            {"person_a": "p_a", "person_b": "p_b", "kind": "phone", "value": "8613800138000"},
            {"person_a": "p_a", "person_b": "p_b", "kind": "email", "value": "a@example.com"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=False)
    assert out["status"] == "ok"
    assert out["proposed"] == 1  # dedup to one pair
    assert out["inserted"] == 1

    row = fetch_one(
        "SELECT person_a, person_b, status, reason, score, detail_json "
        "FROM merge_candidates ORDER BY id DESC LIMIT 1"
    )
    assert row is not None
    assert row["person_a"] == "p_a"
    assert row["person_b"] == "p_b"
    assert row["status"] == "pending"
    # kinds are sorted alphabetically in reason
    assert "email" in row["reason"] and "phone" in row["reason"]
    # score is the max of phone (0.95) / email (0.92)
    assert float(row["score"]) == pytest.approx(0.95)


def test_sync_skips_pairs_already_in_merge_log(monkeypatch):
    execute(
        "INSERT INTO merge_log (kept_person_id, absorbed_person_id, reason, detail_json) "
        "VALUES ('p_a', 'p_b', 'test', '{}')",
    )

    def fake_pairs():
        return [
            {"person_a": "p_a", "person_b": "p_b", "kind": "phone", "value": "x"},
            {"person_a": "p_c", "person_b": "p_d", "kind": "phone", "value": "y"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=False)
    assert out["proposed"] == 1  # only p_c/p_d remains
    assert out["inserted"] == 1

    row = fetch_one("SELECT person_a, person_b FROM merge_candidates ORDER BY id DESC LIMIT 1")
    assert row["person_a"] == "p_c" and row["person_b"] == "p_d"


def test_sync_skips_pairs_already_in_merge_candidates(monkeypatch):
    execute(
        "INSERT INTO merge_candidates (person_a, person_b, score, reason, status, detail_json) "
        "VALUES ('p_a', 'p_b', 0.9, 'pre-existing', 'rejected', '{}')",
    )

    def fake_pairs():
        return [
            # (a,b) flipped order — _already_handled_pairs must normalize
            {"person_a": "p_b", "person_b": "p_a", "kind": "phone", "value": "z"},
            {"person_a": "p_e", "person_b": "p_f", "kind": "email", "value": "e@x"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    # Note: fake_pairs returns person_a > person_b which wouldn't happen
    # in real Kuzu query, but we normalize in Python anyway.
    out = mc.sync_from_graph(dry_run=False)
    assert out["proposed"] == 1
    assert out["inserted"] == 1

    # exactly two candidates for our scoped ids now:
    # the pre-existing rejected p_a/p_b and the new p_e/p_f
    count = int(
        query(
            "SELECT COUNT(*) AS c FROM merge_candidates WHERE "
            "person_a IN ('p_a','p_b','p_e','p_f') OR "
            "person_b IN ('p_a','p_b','p_e','p_f')"
        )[0]["c"]
    )
    assert count == 2


def test_sync_unknown_kind_gets_default_score(monkeypatch):
    def fake_pairs():
        return [
            {"person_a": "p_a", "person_b": "p_b", "kind": "weird_kind", "value": "v"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)
    out = mc.sync_from_graph(dry_run=True)
    assert out["samples"][0]["score"] == pytest.approx(mc._GRAPH_DEFAULT_SCORE)


# ---------------------------------------------------------------------------
# Auto-apply (threshold) semantics
# ---------------------------------------------------------------------------


def _pid(tag: str) -> str:
    return f"{_TEST_PID_PREFIX}{tag}"


def _seed_two_persons(pa: str, pb: str) -> None:
    """Minimal fixture so merge_persons has actual rows to collapse."""
    for p in (pa, pb):
        execute(
            "INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc) "
            "VALUES (?, ?, '[]', '[]', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING",
            [p, p],
        )


def test_dry_run_previews_bucket_counts(monkeypatch):
    """Dry-run must not write but still split into would_auto_apply /
    would_stay_pending so the weekly log can surface the counts.
    """
    phone_a, phone_b = _pid("phone_a"), _pid("phone_b")
    mail_a, mail_b = _pid("mail_a"), _pid("mail_b")
    wk_a, wk_b = _pid("wk_a"), _pid("wk_b")

    def fake_pairs():
        return [
            {"person_a": phone_a, "person_b": phone_b, "kind": "phone", "value": "1"},
            {"person_a": mail_a, "person_b": mail_b, "kind": "email", "value": "e"},
            {"person_a": wk_a, "person_b": wk_b, "kind": "weird", "value": "w"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=True, auto_apply_min_score=0.95)
    assert out["status"] == "ok"
    assert out["proposed"] == 3
    assert out["would_auto_apply"] == 1
    assert out["would_stay_pending"] == 2
    assert out["auto_apply_min_score"] == pytest.approx(0.95)
    assert out["inserted"] == 0
    assert out["auto_applied"] == 0
    # No merge_candidates row should exist for any of our test pairs.
    count = int(
        query(
            f"SELECT COUNT(*) AS c FROM merge_candidates WHERE person_a LIKE '{_TEST_PID_PREFIX}%'"
        )[0]["c"]
    )
    assert count == 0


def test_apply_auto_merges_above_threshold_keeps_rest_pending(monkeypatch):
    phone_a, phone_b = _pid("aam_phone_a"), _pid("aam_phone_b")
    mail_a, mail_b = _pid("aam_mail_a"), _pid("aam_mail_b")
    _seed_two_persons(phone_a, phone_b)
    _seed_two_persons(mail_a, mail_b)

    def fake_pairs():
        return [
            {"person_a": phone_a, "person_b": phone_b, "kind": "phone", "value": "1"},
            {"person_a": mail_a, "person_b": mail_b, "kind": "email", "value": "e"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=False, auto_apply_min_score=0.95)
    assert out["status"] == "ok"
    assert out["proposed"] == 2
    assert out["inserted"] == 2
    assert out["auto_applied"] == 1
    assert out["would_auto_apply"] == 1
    assert out["would_stay_pending"] == 1
    assert len(out["auto_applied_samples"]) == 1
    sample = out["auto_applied_samples"][0]
    assert sample["person_a"] == phone_a
    assert sample["kept"] and sample["absorbed"]
    assert sample["score"] == pytest.approx(0.95)

    phone_row = fetch_one(
        "SELECT status FROM merge_candidates WHERE person_a = ? AND person_b = ? "
        "ORDER BY id DESC LIMIT 1",
        [phone_a, phone_b],
    )
    assert phone_row is not None
    assert str(phone_row["status"]).lower() == "accepted"
    log_count = int(
        query(
            "SELECT COUNT(*) AS c FROM merge_log WHERE "
            "(kept_person_id = ? AND absorbed_person_id = ?) OR "
            "(kept_person_id = ? AND absorbed_person_id = ?)",
            [phone_a, phone_b, phone_b, phone_a],
        )[0]["c"]
    )
    assert log_count == 1

    mail_row = fetch_one(
        "SELECT status FROM merge_candidates WHERE person_a = ? AND person_b = ? "
        "ORDER BY id DESC LIMIT 1",
        [mail_a, mail_b],
    )
    assert mail_row is not None
    assert str(mail_row["status"]).lower() == "pending"


def test_apply_without_threshold_keeps_everything_pending(monkeypatch):
    """Regression: old behavior (no threshold) must keep every row
    pending even when --apply is set.
    """
    x, y = _pid("nt_x"), _pid("nt_y")
    _seed_two_persons(x, y)

    def fake_pairs():
        return [{"person_a": x, "person_b": y, "kind": "phone", "value": "1"}]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=False)
    assert out["auto_applied"] == 0
    assert out["inserted"] == 1
    assert out["auto_apply_min_score"] is None

    row = fetch_one(
        "SELECT status FROM merge_candidates WHERE person_a = ? AND person_b = ? "
        "ORDER BY id DESC LIMIT 1",
        [x, y],
    )
    assert str(row["status"]).lower() == "pending"


def test_budget_cap_favors_high_confidence(monkeypatch):
    """When the safety cap is smaller than the day's haul, auto-apply
    candidates must be drained before pending-only candidates.
    """
    h1_a, h1_b = _pid("bc_h1_a"), _pid("bc_h1_b")
    l1_a, l1_b = _pid("bc_l1_a"), _pid("bc_l1_b")
    l2_a, l2_b = _pid("bc_l2_a"), _pid("bc_l2_b")
    _seed_two_persons(h1_a, h1_b)

    def fake_pairs():
        return [
            {"person_a": h1_a, "person_b": h1_b, "kind": "phone", "value": "1"},
            {"person_a": l1_a, "person_b": l1_b, "kind": "email", "value": "a"},
            {"person_a": l2_a, "person_b": l2_b, "kind": "email", "value": "b"},
        ]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=False, auto_apply_min_score=0.95, max_inserts=1)
    assert out["inserted"] == 1
    assert out["auto_applied"] == 1

    low_count = int(
        query(
            f"SELECT COUNT(*) AS c FROM merge_candidates WHERE person_a LIKE '{_TEST_PID_PREFIX}bc_l%'"
        )[0]["c"]
    )
    assert low_count == 0


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        (0.0, None),
        (-0.1, None),
        (1.5, None),
        ("not a float", None),
        (0.95, 0.95),
        (1.0, 1.0),
    ],
)
def test_coerce_threshold_accepts_only_valid_range(raw, expected):
    out = mc._coerce_threshold(raw)
    if expected is None:
        assert out is None
    else:
        assert out == pytest.approx(expected)


def test_apply_threshold_out_of_range_is_safe(monkeypatch):
    """A bogus threshold (e.g. 1.5 or -0.1) must not silently auto-
    merge everything. It should behave like "not set".
    """
    x, y = _pid("oor_x"), _pid("oor_y")
    _seed_two_persons(x, y)

    def fake_pairs():
        return [{"person_a": x, "person_b": y, "kind": "phone", "value": "1"}]

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", fake_pairs)

    out = mc.sync_from_graph(dry_run=False, auto_apply_min_score=1.5)
    assert out["auto_applied"] == 0
    assert out["auto_apply_min_score"] is None
