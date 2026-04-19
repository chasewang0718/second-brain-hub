# tools/

**执行层代码**. PS1 (Windows) + AHK (全局热键) + (未来) Python.

## 子目录

| 子目录 | 内容 |
|---|---|
| `ollama-pipeline/` | 本地 PDF 分类流水线 (worker + QA + apply + orchestrator) |
| `asset/` | 二进制资产管理 (dedup, migrate, stats, source-cleanup 等) |
| `health/` | 健康体检 + 周报 |
| `housekeeping/` | nightly push, staging dispose |
| `ahk/` | 全局热键 (Caps+D 等) |
| `dispatcher/` | **通用任务派发器** (读 `config/task-router.yaml`, 选 local/cloud) |
| `escalation/` | 兜底队列的消化器 |
| `mcp-server/` | (预留) MCP server wrapper, 对外暴露工具 |
| `lib/` | 共享库: yaml 读取, Ollama 调用封装, 日志, git helper |

## 约定

- 所有脚本**必须**: (1) 有 `-WhatIf` / `-DryRun` 开关  (2) 写 telemetry 日志  (3) 错误码规范
- 路径**不得硬编码**, 从 `config/paths.yaml` 读
- 新脚本注册到 `install.ps1` (自动加到 PS profile)
- 命名: `brain-<domain>-<verb>.ps1`, 热键函数 `g<action>`
