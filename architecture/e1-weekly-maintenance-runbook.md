---
title: E1 周期维护 runbook
status: active
created: 2026-04-21
authoritative_at: C:\dev-projects\second-brain-hub\architecture\e1-weekly-maintenance-runbook.md
---

# E1 · 周期维护 runbook

> "维护动作跑起来" 不等于 "维护动作稳定跑"。本 runbook 负责把三个低风险、幂等的 `brain` 命令接上 Windows Task Scheduler，让它们每周自动跑一次并留痕。

## 1. 包含什么

| 步骤 | 命令 | 作用 | 目标产物 |
|---|---|---|---|
| 1 | `brain identifiers-repair --kinds all` | 存量 `person_identifiers.value_normalized` 大小写 / 号段重写；冲突写入 T3 `merge_candidates` | DuckDB `merge_candidates.status = pending` 条数可能增加 |
| 2 | `brain cloud flush --dry-run` | 快照当前 `_cursor_queue/` 待办条目数；不触发真正 flush | 日志里一行 count + 条目清单 |
| 3 | `brain graph-build`（可 `-SkipGraph` 跳过） | 从 DuckDB 重建 Kuzu 只读视图（F3 POC） | `<telemetry_logs_dir>/kuzu-graph/brain.kuzu` 被覆盖 |
| 4 | `brain merge-candidates sync-from-graph --dry-run`（同 `-SkipGraph` 旁路） | 扫 Kuzu 的 shared-identifier 对，报告未被 `merge_candidates` / `merge_log` 覆盖的条数（只报数，不写） | 日志里一行 `proposed = N` |
| 5（可选） | `brain merge-candidates sync-from-graph --apply --auto-apply-min-score <X>` | **仅当注册时传 `-AutoApplyMinScore X`（X > 0）时启用**。高置信对（score ≥ X）自动走 `accept_candidate`（合并 + `merge_log` 留痕），低置信仍写 pending 等人工。 | `auto_applied = N`；`merge_log` 新增 N 条；被合并的 person 行消失 |

**不包含的动作**（见下文"为什么不做")

- ❌ 实盘 `cloud flush`（需要人工 `cursor-agent` 介入）
- ❌ 真实 `ios-sync` / `wechat-sync`（依赖外部备份文件 + 隐私口径）
- ❌ 任何带 `--write` / `--apply` 的数据变更

## 2. 文件布局

```
tools/housekeeping/
  brain-weekly-maintenance.ps1              ← 实际任务
  register-brain-weekly-maintenance.ps1     ← Windows Task Scheduler 注册
```

日志写在 `D:\second-brain-assets\_runtime\logs\brain-weekly-maintenance-YYYYMMDD.log`。

## 3. 首次启用

```powershell
# 1) 手动跑一遍, 确认日志正常写
cd C:\dev-projects\second-brain-hub\tools\housekeeping
./register-brain-weekly-maintenance.ps1 -RunNow

# 2) 看日志
Get-Content 'D:\second-brain-assets\_runtime\logs\brain-weekly-maintenance-*.log' -Tail 40

# 3) 如果 OK, 正式注册 (默认: 每周日 23:00)
./register-brain-weekly-maintenance.ps1

# 4) 查看任务
Get-ScheduledTask -TaskName BrainWeeklyMaintenance | Format-List TaskName, State, URI, Triggers
```

## 4. 自检 / 验收

任务跑完后，以下三条都应满足：

1. `Get-ScheduledTaskInfo -TaskName BrainWeeklyMaintenance` 的 `LastTaskResult = 0`
2. `brain-weekly-maintenance-<date>.log` 最后一行是 `=== brain weekly maintenance OK (N steps) ===`
3. `brain graph-stats` 能正常返回节点/边计数（即 Kuzu 视图没被弄坏）

## 5. 关闭 / 更换时间

```powershell
# 改时间 (会覆盖注册):
./register-brain-weekly-maintenance.ps1 -Time 07:30 -DayOfWeek Monday

# 下线:
./register-brain-weekly-maintenance.ps1 -Unregister
```

## 6. 为什么这些步骤"安全到可以常驻"

- `identifiers-repair`：T1/T2 自动合并是"大小写 / 号段"这类无损归一；T3 冲突只写 `merge_candidates`，永远等人工 `brain merge-candidates accept|reject`。
- `cloud flush --dry-run`：只列当前队列，不跑 Cursor-Agent。
- `graph-build`：Kuzu 是只读派生视图；DuckDB 不会被触碰。

三条都不改真相源，失败也只是一行 log。

## 7. 何时升级

| 触发条件 | 下一步 |
|---|---|
| 周 log 经常看到 `cloud flush --dry-run count ≥ 10` | 加一步 manual `cloud flush` 提醒（notification），**不要**让 scheduler 自动 flush |
| Kuzu 图节点 / 边数量稳定后 | 加 `brain graph-stats > ...\brain-weekly-stats.json` 写 history，变化 > 10% 报 journal |
| 出现真实 `iOS/WeChat` 数据源 | 接入 `brain ios-sync` / `brain wechat-sync`，但保持 `--dry-run` 再加一道审阅 |

---

## 变更记录

| 日期 | 说明 |
|---|---|
| 2026-04-21 | 首版；`brain-weekly-maintenance.ps1` + 注册脚本；每周日 23:00；三步（repair / cloud dry-run / graph-build），含 `-SkipGraph` 旁路。 |
| 2026-04-21 | 加 "merge-candidates sync-from-graph --dry-run" 为第 4 步（随 `-SkipGraph` 一起旁路）；真正写入需人工 `brain merge-candidates sync-from-graph --apply`。 |
| 2026-04-21 | 加第 5 步可选自动合并：脚本参数 `-AutoApplyMinScore <X>`（默认 0 = 关闭；推荐 0.95 = 仅 `phone` 级自动合，`email`/`wxid` 的 0.92/0.93 仍压 pending）；通过 `sync_from_graph(auto_apply_min_score=X)` 分桶，高置信走 `accept_candidate` 留 `merge_log` 审计。启用：`./register-brain-weekly-maintenance.ps1 -AutoApplyMinScore 0.95` 重注册。 |
