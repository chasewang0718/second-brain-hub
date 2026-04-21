# `brain cloud flush` · 运行手册 (C-01)

> Status: 2026-04-21 · 仅本地 PowerShell，零预算

## 目标
把 `cloud_queue` 里本地模型做不了的条目（`capsd-note-hard` / `ambiguous-person-link` / 等）打包成一份 prompt，交给 **cursor-agent** 的订阅额度处理。

## 前置条件

| 依赖 | 检查命令 |
|---|---|
| `cursor-agent` CLI 存在 | `%LOCALAPPDATA%\cursor-agent\agent.cmd` 可执行 |
| DuckDB 正常（schema 已就绪） | `python -m brain_cli.main health` → `ok` |
| 仍然持有 git 兜底 | `python -m brain_cli.main safety-status` → `dirty`/`untracked` 信息符合预期 |

若 `cursor-agent` 路径不同，用 `--agent-cmd <path>` 覆盖。

## 三段式验证

```powershell
cd C:\dev-projects\second-brain-hub\tools\py
$env:PYTHONPATH = "src"

# 1) 看队列。空列表 => status=empty
python -m brain_cli.main cloud queue list

# 2) 造 1 条测试任务（仅当需要真流程联调；否则跳过）
python -c "from brain_agents.cloud_queue import enqueue; print(enqueue('capsd-note-hard', {'note':'smoke flush'}))"

# 3) Dry-run：不 spawn agent，只看 prompt 统计
python -m brain_cli.main cloud flush --dry-run
```

**预期 `--dry-run` 输出字段：**
- `status = dry_run`
- `agent` = cursor-agent 可执行路径
- `tasks` = pending 概览（id / task_kind / preview）
- `prompt_chars` = 生成的 prompt 总长度

## 实跑（会占用 Cursor 订阅额度）

```powershell
python -m brain_cli.main cloud flush
```

- 创建 `.brain-autotrigger.lock`（15 分钟内禁止并发，`status=skipped` + `reason=lock_recent`）
- 将 cursor-agent 的 `stdout/stderr` 写入 `<content_root>/.brain-cloud-flush-last.log`
- 成功返回 `status=completed` + `exit_code=0`

## 验收清单

- [ ] dry-run 与实跑各 1 次，均无异常
- [ ] `.brain-cloud-flush-last.log` 存在且大小 > 0
- [ ] 处理完后 `cloud_queue` 中 `status = done` 的条目有增加（或维持，若 agent 故意留着等人工复核）

## 自动化（CI / 本地 pytest）

在 `tools/py` 下（`PYTHONPATH=src` 已由 `pyproject` 的 pytest 配置注入）：

```powershell
python -m pytest tests/test_cloud_flush.py -q
```

`test_flush_dry_run_includes_tasks_when_queue_non_empty` 会入队一条 `capsd-note-hard` 占位的 pending 行，再跑 `flush(dry_run=True)`。若本机**没有** `cursor-agent`，应得到 `status=skipped` 且 `reason=cursor_agent_missing`，但 `overview` 里仍应含该条任务；若有 agent 可执行，则 `status=dry_run` 且 `prompt_chars` > 0。测后**删除**该测试行，不污染你的待办队列。

MCP 侧可用 `cloud_flush_preview` 做与 `brain cloud flush --dry-run` 等价的只读检查（不 spawn 进程）。

## 故障排查

| 现象 | 说明 / 处置 |
|---|---|
| `cursor_agent_missing` | 用 `--agent-cmd` 指路径；必要时把 `agent.cmd` 所在目录加进 `PATH`，终端新开一个 session |
| `lock_recent` | 看 `.brain-autotrigger.lock` mtime；确实无并发任务时 **手动删除** 该文件 |
| `timeout` | 默认 3600s；如数据量太大，把任务量控制在 ≤ 30 条，或分批 |
| prompt 过长 | `cloud_queue.payload_json` 预览已截断；如需更短，对 `list_pending` 的 `preview` 长度再下调 |

## 不做的事
- 不把 `cloud flush` 接入自动调度（定时任务 / watch）——刻意保留人触发，避免 Cursor 额度意外消耗。
- 不做并发多 agent；一次最多一个。
