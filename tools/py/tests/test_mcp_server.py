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
