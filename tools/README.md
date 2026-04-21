# tools/

**执行层代码**. PS1 (Windows) + AHK (全局热键) + (未来) Python.

## 子目录

| 子目录 | 内容 |
|---|---|
| `py/` | **Python 实现层**（主流）: `brain_cli`, `brain_agents`, `brain_memory`, `brain_mcp` |
| `ps/` | 小量 PowerShell 入口脚本（例如 Caps+D 分发器 `brain-caps-d-dispatch.ps1`） |
| `ahk/` | 全局热键 (Caps+D 等) |
| `asset/` | 二进制资产管理 (dedup, migrate, stats, source-cleanup) — 老 PS, 待逐条迁 Python |
| `health/` | 健康体检 + 周报 (老 PS, 待替换为 `brain health`) |
| `housekeeping/` | nightly push, 周维护任务 (`brain-weekly-maintenance.ps1` 等) |
| `watchdog/` | 通用通知库 `notify.ps1`（供未来 watchdog 复用） |
| `dispatcher/` | 通用任务派发器 (预留) |
| `escalation/` | 兜底队列的消化器 |
| `mcp-server/` | MCP server wrapper，对外暴露工具（主实现在 `py/src/brain_mcp/`） |
| `one-off/` | 一次性脚本 |

> 2026-04-21 清理（对应 ROADMAP "Phase A3 收尾 · 弃用 PS 脚本"）：
> 已删除 `ollama-pipeline/` 整目录、`lib/`（config-loader / telemetry / wait-for-batch）、
> `feedback/harvest-feedback.ps1`、`watchdog/pdf-production-watchdog.ps1`。
> 这些都已被 `tools/py/` 下的 `brain_agents/file_inbox.py` / `image_inbox.py` /
> `audio_inbox.py` / `cloud_queue.py` 覆盖。

## 约定

- 新脚本首选 Python（`tools/py/src/brain_*/`），PS 只留"胶水入口"（Caps+D 分发器、Task Scheduler 注册等）。
- 所有脚本**必须**: (1) 有 `--dry-run` / `-WhatIf` 开关  (2) 写 telemetry 日志  (3) 错误码规范
- 路径**不得硬编码**, 从 `config/paths.yaml` 读
- 命名: Python 入口在 `brain_cli/main.py` 里加 `@app.command(...)`；PS 保持 `brain-<domain>-<verb>.ps1`
