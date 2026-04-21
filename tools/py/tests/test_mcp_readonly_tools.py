"""Smoke tests for read-only MCP helpers (cloud queue list, ios locate, wechat preview skip)."""

from __future__ import annotations


def test_cloud_queue_list_tool_returns_list() -> None:
    from brain_mcp.server import cloud_queue_list_tool

    rows = cloud_queue_list_tool(limit=5)
    assert isinstance(rows, list)


def test_ios_backup_locate_preview_returns_dict() -> None:
    from brain_mcp.server import ios_backup_locate_preview

    loc = ios_backup_locate_preview()
    assert isinstance(loc, dict)


def test_wechat_sync_preview_skips_missing_decoder() -> None:
    from brain_mcp.server import wechat_sync_preview

    out = wechat_sync_preview(decoder_dir="__brain_nonexistent_decoder_path__")
    assert out["status"] == "skipped"
