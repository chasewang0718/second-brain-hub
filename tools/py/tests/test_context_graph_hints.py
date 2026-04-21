"""F3 integration: context_for_meeting merges Kuzu shared-identifier
hints into both the JSON payload and the Markdown render.

Uses monkeypatching rather than a real Kuzu build so the tests remain
cheap and run even on machines without kuzu installed.
"""

from __future__ import annotations

from brain_agents import people


def _monkeypatch_shared_identifier(monkeypatch, rows):
    """Replace the lazy import target inside ``_collect_graph_hints``."""

    def fake_shared_identifier(person_id, *, limit=5, kuzu_dir=None):
        return {"anchor": person_id, "count": len(rows), "results": rows, "elapsed_ms": 3.14}

    # module is imported lazily inside _collect_graph_hints; inject
    # via sys.modules so the function's dynamic import picks it up.
    import sys
    import types

    fake_mod = types.ModuleType("brain_agents.graph_query")
    fake_mod.shared_identifier = fake_shared_identifier  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "brain_agents.graph_query", fake_mod)


def test_graph_hints_skipped_when_module_raises(monkeypatch):
    import sys
    import types

    def raise_on_query(pid, *, limit=5, kuzu_dir=None):
        raise RuntimeError("kuzu_not_built:/tmp/x")

    fake_mod = types.ModuleType("brain_agents.graph_query")
    fake_mod.shared_identifier = raise_on_query  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "brain_agents.graph_query", fake_mod)

    out = people._collect_graph_hints("p_nonexistent")
    assert out["status"] == "skipped"
    assert "kuzu_not_built" in out["reason"]


def test_graph_hints_ok_path(monkeypatch):
    rows = [
        {"person_id": "p_bob", "display_name": "Bob", "kind": "phone", "value_normalized": "8613800138000"},
    ]
    _monkeypatch_shared_identifier(monkeypatch, rows)

    out = people._collect_graph_hints("p_alice")
    assert out["status"] == "ok"
    assert out["shared_identifier"] == rows
    assert isinstance(out["elapsed_ms"], float)


def test_context_for_meeting_markdown_contains_shared_identifier_section(monkeypatch):
    rows = [
        {"person_id": "p_bob", "display_name": "Bob", "kind": "phone", "value_normalized": "8613800138000"},
    ]
    _monkeypatch_shared_identifier(monkeypatch, rows)

    people.seed_demo_people_data()
    payload = people.context_for_meeting("Alice", limit=3, since_days=365)
    assert payload.get("contact") is not None
    assert payload["graph_hints"]["status"] == "ok"
    md = people.context_for_meeting_markdown(payload)
    assert "潜在同一人线索" in md
    assert "p_bob" in md
    assert "8613800138000" in md


def test_context_for_meeting_markdown_hides_section_when_skipped(monkeypatch):
    import sys
    import types

    def fake_fail(pid, *, limit=5, kuzu_dir=None):
        raise RuntimeError("kuzu_missing:ModuleNotFoundError")

    fake_mod = types.ModuleType("brain_agents.graph_query")
    fake_mod.shared_identifier = fake_fail  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "brain_agents.graph_query", fake_mod)

    people.seed_demo_people_data()
    payload = people.context_for_meeting("Alice", limit=3, since_days=365)
    assert payload["graph_hints"]["status"] == "skipped"
    md = people.context_for_meeting_markdown(payload)
    assert "潜在同一人线索" not in md  # section hidden when no hits


def test_include_graph_hints_false_skips_call(monkeypatch):
    called = {"n": 0}
    import sys
    import types

    def bump(pid, *, limit=5, kuzu_dir=None):
        called["n"] += 1
        return {"results": [], "elapsed_ms": 0.0}

    fake_mod = types.ModuleType("brain_agents.graph_query")
    fake_mod.shared_identifier = bump  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "brain_agents.graph_query", fake_mod)

    people.seed_demo_people_data()
    payload = people.context_for_meeting("Alice", include_graph_hints=False)
    assert payload["graph_hints"] is None
    assert called["n"] == 0
