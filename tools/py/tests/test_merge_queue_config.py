"""B-ING-2: merge_queue config loader.

Verifies that the graph kind scores, default score, and auto-apply min
score are sourced from ``config/thresholds.yaml → merge_queue`` and that
callers can still override the threshold per-invocation.

Uses ``monkeypatch`` to swap out ``load_thresholds_config`` inside the
lazy loader, so these tests never depend on the actual YAML on disk.
"""

from __future__ import annotations

from typing import Any

import pytest

from brain_agents import merge_candidates as mc


@pytest.fixture
def _clear_cache():
    """merge_queue config is @lru_cache(maxsize=1). Clear before/after
    each test so monkeypatched configs take effect and don't leak.
    """
    mc._load_merge_queue_config.cache_clear()
    yield
    mc._load_merge_queue_config.cache_clear()


def _install_cfg(monkeypatch: pytest.MonkeyPatch, cfg: dict[str, Any]) -> None:
    def fake_loader() -> dict[str, Any]:
        return cfg

    monkeypatch.setattr("brain_core.config.load_thresholds_config", fake_loader)


def test_config_loader_reads_merge_queue_block(monkeypatch, _clear_cache):
    _install_cfg(
        monkeypatch,
        {
            "merge_queue": {
                "graph_kind_scores": {
                    "phone": 0.97,
                    "email": 0.80,
                },
                "graph_default_score": 0.55,
                "auto_apply_min_score": 0.90,
            }
        },
    )

    out = mc._load_merge_queue_config()
    assert out["graph_kind_scores"]["phone"] == pytest.approx(0.97)
    assert out["graph_kind_scores"]["email"] == pytest.approx(0.80)
    assert out["graph_default_score"] == pytest.approx(0.55)
    assert out["auto_apply_min_score"] == pytest.approx(0.90)


def test_config_loader_falls_back_when_yaml_missing(monkeypatch, _clear_cache):
    _install_cfg(monkeypatch, {})

    out = mc._load_merge_queue_config()
    assert out["graph_kind_scores"]["phone"] == pytest.approx(0.95)
    assert out["graph_kind_scores"]["email"] == pytest.approx(0.92)
    assert out["graph_kind_scores"]["wxid"] == pytest.approx(0.93)
    assert out["graph_default_score"] == pytest.approx(0.6)
    assert out["auto_apply_min_score"] is None


def test_config_loader_falls_back_on_malformed_values(monkeypatch, _clear_cache):
    _install_cfg(
        monkeypatch,
        {
            "merge_queue": {
                "graph_kind_scores": {"phone": "not-a-number"},
                "graph_default_score": "nope",
                "auto_apply_min_score": "garbage",
            }
        },
    )

    out = mc._load_merge_queue_config()
    assert out["graph_kind_scores"]["phone"] == pytest.approx(0.95)
    assert out["graph_default_score"] == pytest.approx(0.6)
    assert out["auto_apply_min_score"] is None


def test_config_loader_rejects_out_of_range_auto_apply(monkeypatch, _clear_cache):
    for bad in (0.0, -0.5, 1.5, 2):
        _install_cfg(
            monkeypatch,
            {"merge_queue": {"auto_apply_min_score": bad}},
        )
        mc._load_merge_queue_config.cache_clear()
        out = mc._load_merge_queue_config()
        assert out["auto_apply_min_score"] is None, f"bad={bad} should disable"


def test_caller_override_wins_over_yaml_default(monkeypatch, _clear_cache):
    """Even if the YAML ships with auto_apply disabled (0.0 / None),
    a caller passing an explicit threshold must still be respected.
    """
    _install_cfg(monkeypatch, {"merge_queue": {"auto_apply_min_score": 0.0}})

    def empty_pairs():
        return []

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", empty_pairs)

    out = mc.sync_from_graph(dry_run=True, auto_apply_min_score=0.88)
    assert out["auto_apply_min_score"] == pytest.approx(0.88)


def test_caller_none_picks_up_yaml_default(monkeypatch, _clear_cache):
    """When caller passes None (or omits), the YAML's auto_apply_min_score
    is used. This is the cron path: no flag → inherit config.
    """
    _install_cfg(monkeypatch, {"merge_queue": {"auto_apply_min_score": 0.91}})

    def empty_pairs():
        return []

    monkeypatch.setattr(mc, "_enumerate_shared_identifier_pairs", empty_pairs)

    out = mc.sync_from_graph(dry_run=True)
    assert out["auto_apply_min_score"] == pytest.approx(0.91)


def test_backcompat_module_aliases_exist():
    """Back-compat: ``_GRAPH_KIND_SCORES`` and ``_GRAPH_DEFAULT_SCORE``
    remain importable so any external consumer isn't broken.
    """
    assert isinstance(mc._GRAPH_KIND_SCORES, dict)
    assert "phone" in mc._GRAPH_KIND_SCORES
    assert isinstance(mc._GRAPH_DEFAULT_SCORE, float)
