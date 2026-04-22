# WeChat Ingest Acceptance Checklist

用于每次执行 `wechat-ingest-preset.ps1`（尤其是 `-Apply`）前后快速验收。

## 执行前

- [ ] 选择预设模式：`default` / `helper-no-person` / `helper-link-person` / `helper-blacklist`
- [ ] 确认 `DecoderDir` 指向当前 `wechat-decoder` 导出目录
- [ ] 确认 `MaxWouldInsert` 合理（默认 `200`）

## 预检（preflight dry-run）

- [ ] `preflight` 成功输出可解析 JSON
- [ ] 记录 `would_insert` 总数
- [ ] `would_insert <= MaxWouldInsert`（否则中止 apply）
- [ ] 会话过滤与模式符合预期（看 `_agg.chat_whitelist/chat_blacklist/helper_chat_mode`）

## apply（若执行）

- [ ] 自动生成 DuckDB 快照（`ingest-backup-now --label wechat-<mode>-<ts>`）
- [ ] apply 返回 `status=ok`
- [ ] `ingest-log-recent --source wechat` 有对应 apply 事件

## 执行后核对

- [ ] 复跑同模式 dry-run，关键会话 `would_insert=0`（幂等）
- [ ] `eval_people.py` 仍通过（当前基线 35/35）
- [ ] `eval_people_trend.py` 与 `eval_people_trend_summary.py` 已刷新

## 常用命令

```powershell
# 推荐：helper 会话保留但不挂 person（默认先 preflight）
powershell -NoProfile -ExecutionPolicy Bypass -File tools/housekeeping/wechat-ingest-preset.ps1 -Mode helper-no-person

# apply（会自动 preflight + 快照 + apply）
powershell -NoProfile -ExecutionPolicy Bypass -File tools/housekeeping/wechat-ingest-preset.ps1 -Mode helper-no-person -Apply

# 严格门槛：最多允许 50 条新增
powershell -NoProfile -ExecutionPolicy Bypass -File tools/housekeeping/wechat-ingest-preset.ps1 -Mode helper-no-person -Apply -MaxWouldInsert 50

# 一键执行+核对（推荐）
powershell -NoProfile -ExecutionPolicy Bypass -File tools/housekeeping/wechat-ingest-preset.ps1 -Mode helper-no-person -Apply -RunPostChecks
```
