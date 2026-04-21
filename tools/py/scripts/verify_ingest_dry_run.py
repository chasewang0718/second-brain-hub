#!/usr/bin/env python3
"""Local dry-run smoke for multi-source ingestion (no DuckDB writes).

Runs:
  - iOS backup locate (Manifest.db → ChatStorage / AddressBook paths)
  - optional WeChat decoder dry-run sync (when VERIFY_WECHAT_DECODER points at wechat-decoder root)

Usage (from repo tools/py):

  set PYTHONPATH=src
  python scripts/verify_ingest_dry_run.py

  # optional WeChat path override (forward slashes ok):
  set VERIFY_WECHAT_DECODER=C:\\dev-projects\\wechat-decoder
  python scripts/verify_ingest_dry_run.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    repo_py = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_py / "src"))

    from brain_agents.ios_backup_locator import locate_bundle

    report: dict = {}

    report["ios_backup_locate"] = locate_bundle()

    wx_root = os.environ.get("VERIFY_WECHAT_DECODER", "").strip()
    if wx_root:
        root = Path(wx_root).expanduser()
        if root.is_dir():
            from brain_agents.wechat_sync import sync_from_cli

            report["wechat_sync_dry_run"] = sync_from_cli(str(root), dry_run=True)
        else:
            report["wechat_sync_dry_run"] = {"status": "skipped", "reason": "decoder_root_missing", "path": str(root)}
    else:
        report["wechat_sync_dry_run"] = {
            "status": "skipped",
            "reason": "VERIFY_WECHAT_DECODER unset",
            "hint": "Set env VERIFY_WECHAT_DECODER to your wechat-decoder root to include dry-run.",
        }

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
