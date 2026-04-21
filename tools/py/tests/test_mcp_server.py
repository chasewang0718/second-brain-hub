"""Ensure MCP server module imports and exposes expected tools."""

from __future__ import annotations


def test_mcp_server_import_and_fastmcp_instance() -> None:
    from brain_mcp import server

    assert server.mcp is not None
    assert hasattr(server, "health")
    assert callable(getattr(server, "cloud_flush_preview", None))
    assert callable(getattr(server, "identifiers_repair_preview", None))
    assert callable(getattr(server, "cloud_queue_list_tool", None))
    assert callable(getattr(server, "ios_backup_locate_preview", None))
    assert callable(getattr(server, "wechat_sync_preview", None))
    assert callable(getattr(server, "graph_fof_tool", None))
    assert callable(getattr(server, "graph_shared_identifier_tool", None))


def test_graph_tools_skip_gracefully_without_graph_build(tmp_path, monkeypatch) -> None:
    """graph_fof_tool / graph_shared_identifier_tool should return
    ``status=skipped`` (not raise) when the Kuzu graph dir is empty
    or missing, so MCP callers can branch without crashing.
    """
    from brain_agents import graph_query
    from brain_mcp import server

    # Point the lazy default to an empty tmp dir → graph_query._open
    # raises RuntimeError("kuzu_not_built:...") which tools catch.
    # Patch the name actually resolved by graph_query (bound at import
    # time from brain_agents.graph_build.default_kuzu_dir).
    monkeypatch.setattr(graph_query, "default_kuzu_dir", lambda: tmp_path / "kuzu-empty")

    out = server.graph_fof_tool("p_nonexistent", limit=5)
    assert isinstance(out, dict)
    assert out.get("status") == "skipped"

    out2 = server.graph_shared_identifier_tool("p_nonexistent", limit=5)
    assert isinstance(out2, dict)
    assert out2.get("status") == "skipped"
