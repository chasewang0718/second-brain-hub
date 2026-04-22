# WeChat Ingest 策略预设 Runbook

目标：把 helper 会话（`filehelper`）的摄取行为固定成可复用预设，避免每次手输长参数。

## 入口脚本

- `tools/housekeeping/wechat-ingest-preset.ps1`
- 验收清单：`architecture/wechat-ingest-acceptance-checklist.md`

## 预设模式

- `default`
  - 行为：保持原默认（不包含 helper 会话）。
- `helper-no-person`
  - 行为：包含 helper 会话，仅摄取 `filehelper`，但不绑定联系人（`--helper-chat-mode no-person`）。
  - 适用：希望保留记录但避免污染 A5 联系人上下文。
- `helper-link-person`
  - 行为：包含 helper 会话，仅摄取 `filehelper`，并绑定联系人。
  - 适用：明确希望将 helper 内容作为个人互动线索。
- `helper-blacklist`
  - 行为：显式开启 helper 扫描但黑名单 `filehelper`。
  - 适用：需要验证过滤链路/审计日志。

## 常用命令

```powershell
# 1) 默认 dry-run（不含 helper）
powershell -NoProfile -ExecutionPolicy Bypass -File tools/housekeeping/wechat-ingest-preset.ps1 -Mode default

# 2) helper 会话 dry-run（不绑 person，推荐）
powershell -NoProfile -ExecutionPolicy Bypass -File tools/housekeeping/wechat-ingest-preset.ps1 -Mode helper-no-person

# 3) helper 会话 apply（自动先做 ingest-backup-now 快照）
powershell -NoProfile -ExecutionPolicy Bypass -File tools/housekeeping/wechat-ingest-preset.ps1 -Mode helper-no-person -Apply

# 4) apply 门槛控制（preflight would_insert 超过阈值自动中止）
powershell -NoProfile -ExecutionPolicy Bypass -File tools/housekeeping/wechat-ingest-preset.ps1 -Mode helper-no-person -Apply -MaxWouldInsert 50

# 5) 一键流程 + 一键核对（推荐每次 decoder 更新后执行）
powershell -NoProfile -ExecutionPolicy Bypass -File tools/housekeeping/wechat-ingest-preset.ps1 -Mode helper-no-person -Apply -RunPostChecks
```

## 执行后核对

```powershell
# 最近 wechat ingest 事件（看 detail.include_helper_chats / helper_chat_mode / chat_whitelist）
python -m brain_cli.main ingest-log-recent --source wechat --days 2 --limit 5

# 幂等核对（预期 would_insert=0）
python -m brain_cli.main wechat-sync --dry-run --include-helper-chats --chat-whitelist filehelper --helper-chat-mode no-person
```

> `-RunPostChecks` 会自动执行以上核对链（ingest log + 幂等 dry-run + A5 eval + 趋势刷新）。
> 同时会生成关系变化摘要：`08-indexes/digests/relationship-deltas-YYYY-MM-DD.md`。
> 同时会刷新 v6 gate 报告：`08-indexes/digests/v6-gate-report.md`。
> 同时会刷新 WhatsApp 协议 ID 长尾清单：`08-indexes/digests/whatsapp-lid-residue.md`（仅观测，不自动修复）。
> 同时会写入每日 gate 观察日志：`04-journal/YYYY-MM-DD.md` 中追加 `[hub-gate]` 行（用于识别连续天数是否断链）。

## 受控扩量（白名单分批）

当你要从 helper-only 扩到更多聊天时，优先用白名单分批推进：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\housekeeping\wechat-ingest-preset.ps1 `
  -Mode helper-no-person `
  -ExtraWhitelist "20292966501@chatroom" `
  -MaxWouldInsert 100 `
  -Apply
```

- `-ExtraWhitelist` 可重复传入多个会话 ID（每批建议 1~3 个）。
- 仍会经过 preflight dry-run + `MaxWouldInsert` 门限保护。
- 如果 preflight 长期 `would_insert=0`，说明当前 decoder 导出可扩量会话不足；应先刷新 `wechat-decoder` 导出，再继续批次扩量。

## 建议默认

- 日常增量建议使用：`helper-no-person`
- 如果无明确需求，继续用 `default`
- 仅在确认需要“联系人关联”的情况下使用 `helper-link-person`
- 建议保留 preflight（不要 `-SkipPreflightDryRun`），把新增量控制在可审阅阈值内
