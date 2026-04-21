"""A4 provenance: enrich + render tail `## 参考` block for write_draft.

Pure-function tests (no LLM, no ask): we call enrich_provenance /
render_provenance_block directly with synthetic sources, and also
run write_draft with engine=template + monkeypatched ask to verify
the end-to-end wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain_agents import write_assist


def test_classify_source_by_path():
    f = write_assist._classify_source
    assert f(r"D:\sbc\03-projects\inbox-auto-pdf\asset-ml.md") == "pdf"
    assert f(r"D:\sbc\03-projects\inbox-auto-image\asset-shot.md") == "image"
    assert f(r"D:\sbc\03-projects\inbox-auto-audio\asset-memo.md") == "audio"
    assert f(r"D:\sbc\05-contacts\alice.md") == "person-note"
    assert f(r"D:\sbc\04-journal\2026-04-21.md") == "journal"
    assert f(r"D:\sbc\99-misc\note.md") == "note"


def test_enrich_pulls_frontmatter(tmp_path):
    p = tmp_path / "inbox-auto-pdf" / "asset-ml.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "\n".join([
            "---",
            "title: asset-ml",
            "asset_type: pdf",
            "asset_sha256: abc123def456",
            "tags: [asset, pdf]",
            "---",
            "",
            "# ML",
        ]),
        encoding="utf-8",
    )
    enriched = write_assist.enrich_provenance([
        {"path": str(p), "title": "asset-ml", "method": "hybrid"},
    ])
    assert len(enriched) == 1
    e = enriched[0]
    assert e["kind"] == "pdf"
    assert e["asset_sha256"] == "abc123def456"
    assert e["asset_type"] == "pdf"
    assert e["method"] == "hybrid"


def test_render_block_empty():
    assert write_assist.render_provenance_block([]) == ""


def test_render_block_formatting():
    enriched = [
        {"path": "/a.md", "title": "alpha", "method": "hybrid", "kind": "pdf", "asset_sha256": "abc"},
        {"path": "/b.md", "title": "bob", "method": "hybrid", "kind": "person-note", "person_id": "p_123"},
        {"path": "/c.md", "title": "cat", "method": "hybrid", "kind": "note"},
    ]
    block = write_assist.render_provenance_block(enriched)
    assert block.startswith("## 参考")
    assert "[1] pdf · alpha · sha256:abc — `/a.md`" in block
    assert "[2] person-note · bob · person:p_123 — `/b.md`" in block
    assert "[3] note · cat — `/c.md`" in block


def test_write_draft_appends_provenance(monkeypatch, tmp_path):
    # Stub ask() so write_draft doesn't touch the real index
    fake = [
        {"path": str(tmp_path / "a.md"), "title": "a", "preview": "x", "method": "hybrid"},
    ]
    (tmp_path / "a.md").write_text("body", encoding="utf-8")
    monkeypatch.setattr(write_assist, "ask", lambda *a, **kw: fake)
    out = write_assist.write_draft(
        topic="测试话题",
        platform="default",
        reader="reader",
        engine="template",  # avoid Ollama
    )
    assert out["engine"] == "template"
    assert "## 参考" in out["draft"]
    assert out["provenance"][0]["kind"] == "note"
    assert out["provenance"][0]["path"] == str(tmp_path / "a.md")


def test_write_draft_can_skip_provenance(monkeypatch, tmp_path):
    fake = [{"path": str(tmp_path / "a.md"), "title": "a", "preview": "x", "method": "hybrid"}]
    (tmp_path / "a.md").write_text("body", encoding="utf-8")
    monkeypatch.setattr(write_assist, "ask", lambda *a, **kw: fake)
    out = write_assist.write_draft(
        topic="测试话题",
        platform="default",
        reader="reader",
        engine="template",
        include_provenance=False,
    )
    assert "## 参考" not in out["draft"]
    # enriched list is still populated in the return payload
    assert out["provenance"][0]["kind"] == "note"
