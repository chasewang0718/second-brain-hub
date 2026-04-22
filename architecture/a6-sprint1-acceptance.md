---
title: Phase A6 Sprint 1 · 验收报告
status: done
sprint: A6-S1
date: 2026-04-22
---

# A6 Sprint 1 · `person_facts` + `person_metrics`

把 `06-people` 从"堆积的聊天摘要"升级为"可随时间回放的人物档案"的第一块砖：事实层 (bi-temporal) + 指标层 (派生)。不动 A5 既有数据，只加新表。

## 交付清单

| 层 | 路径 | 说明 |
|---|---|---|
| Schema | `tools/py/src/brain_memory/structured.py` | `_ensure_v2_tables` 尾部加 `person_facts` / `person_metrics`；`ensure_schema` 记录 `_brain_migrations v3` |
| Agent | `tools/py/src/brain_agents/person_facts.py` | `add_fact` / `invalidate_fact` / `list_facts(at?, include_history?)` / `get_fact` / `decode_value`；所有写入走 `transaction()` |
| Agent | `tools/py/src/brain_agents/person_metrics.py` | `recompute_one` / `recompute_all(remove_orphans=True)` / `get_metrics`；单次扫 `interactions` 用 CTE 聚合 |
| CLI | `tools/py/src/brain_cli/main.py` | `brain facts add|list|invalidate` + `brain person-metrics recompute|show`；所有子命令 stdout 纯 JSON |
| Render | `tools/py/src/brain_agents/people_render.py` | 在卡 `## Identifiers` 后注入 `## Facts` + `## Metrics`；空数据不渲染头；新增 `--facts-history` |
| Tests | `tools/py/tests/test_person_facts.py`（11）+ `test_person_metrics.py`（7）+ 扩展 `test_people_render.py`（+3） | 21 个新 case，全库 **273/273 passed**（39 秒） |
| Docs | `architecture/ROADMAP.md` + 本文件 | Phase A6 正文 + 变更日志追两条 |

## 表结构

### `person_facts`（bi-temporal，事实层真相源）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT PK | 自增 |
| `person_id` | VARCHAR | FK-like，不强制外键（兼容 merge 留下的 orphan） |
| `key` | VARCHAR | 事实键，如 `residence` / `role` / `relationship_tier` |
| `value_json` | VARCHAR | **永远 JSON 编码**（字符串也 `json.dumps` 一次）；解码用 `decode_value` |
| `valid_from` | TIMESTAMP | 事实开始生效的时间 |
| `valid_to` | TIMESTAMP NULL | **NULL = 当前事实**；同 key 新写入会把旧记录的 `valid_to` 置为 now |
| `confidence` | DOUBLE | 0.0–1.0，默认 1.0 |
| `source_kind` | VARCHAR | `manual` / `capsd` / `wechat` / `derived` / ... |
| `source_interaction_id` | BIGINT NULL | 指向 `interactions.id` 做审计 |
| `created_at` | TIMESTAMP | 插入墙钟（transaction_time） |

**幂等语义**：`add_fact` 默认对"值/置信/来源都相同的当前事实"跳过写入（`status=noop`）；`--force` 会照写一条新记录。

**时点查询**：`list_facts(person_id, at=<datetime>)` 返回该时点生效事实集（`valid_from <= at AND (valid_to IS NULL OR valid_to > at)`）。

### `person_metrics`（派生，覆盖式）

| 列 | 说明 |
|---|---|
| `person_id` PK | |
| `first_seen_utc` / `last_seen_utc` | min/max `interactions.ts_utc` |
| `last_interaction_channel` | 最近一条互动的 channel |
| `interactions_all` / `_30d` / `_90d` | 计数 |
| `distinct_channels_30d` | 去重非空 channel 数 |
| `dormancy_days` | now − last_seen，向下取整 |
| `computed_at` | recompute 墙钟 |

**重建语义**：`recompute_all()` 一次 CTE 扫全 `interactions`，对每个 `person_id` `DELETE` + `INSERT`；`remove_orphans=True` 额外删除 `interactions` 里已无身影的 `person_id`（merge absorbed）。**任意时刻 DROP + recompute 都安全**。

## 生产回填验收

```
brain ingest-backup-now --label a6-sprint1-pre-apply
→ D:\second-brain-assets\_backup\telemetry\20260422-184830-a6-sprint1-pre-apply.duckdb
  sha256 e8137d681b92ebbcca402f2bfcddcfb41ee621018243a5b7c70262b0e682fe7b
  bytes  49 295 360

brain person-metrics recompute --all
→ status=ok updated=656 total_rows=656 computed_at=2026-04-22 18:48:36

brain facts add p_8168e6185835 relationship_tier inner --source-kind manual
→ inserted_id=1 closed_id=null

brain person-metrics show p_8168e6185835
→ interactions_all=424 / 30d=147 / 90d=274
  last_seen_utc=2026-04-20 13:57:36 (wechat) dormancy_days=2

brain people-render --person-id p_8168e6185835
→ D:\second-brain-content\06-people\by-person\田果__p_8168e6185835.md
  卡内新增 ## Facts / ## Metrics 两节
```

## 已知边界 / 下个 sprint 接入点

- `add_fact` 的 `force=False` 语义只比对 `value_json + confidence + source_kind` 三列；如果之后想用 `source_interaction_id` 变化强制落盘，传 `--force`。
- `recompute_all` 的 `remove_orphans` 在 DuckDB 上 `rowcount` 返回 `-1`（不是 bug，DuckDB DELETE 游标 API 限制）；若之后要精确计数再换 `SELECT count(*)` 前后差。
- `person_metrics.dormancy_days` 仅用 `last_seen_utc`；Sprint 2 会配 `relationship_tier` × `cadence_target_days` 推出"是否逾期"判定。
- Facts 目前只在 `people-render` 卡里露头；Sprint 3 `person-digest` 会把 Facts 作为 system prompt 一部分喂给本地 LLM 生成 weekly digest。

## 命令速查（可复制）

```
brain facts add <pid> <key> <value>       # 新事实；同 key 旧记录自动关闭
brain facts add <pid> <key> --value-json '{"city":"杭州"}'
brain facts list <pid>                     # 当前事实
brain facts list <pid> --at 2026-01-01T00:00:00  # 时点查询
brain facts list <pid> --history           # 全历史
brain facts invalidate <fact_id>           # 关闭事实（不删）

brain person-metrics recompute --all
brain person-metrics recompute --person-id <pid>
brain person-metrics show <pid>

brain people-render --person-id <pid> [--facts-history]
```

## pytest 清单（21 新 case）

`test_person_facts.py`：
- `test_add_fact_inserts_current_row`
- `test_add_fact_with_structured_value_json`
- `test_repeated_write_is_noop`
- `test_new_value_closes_old_fact`
- `test_point_in_time_query`
- `test_invalidate_fact`
- `test_confidence_and_source_persisted`
- `test_force_writes_even_when_identical`
- `test_missing_inputs_raise`
- `test_include_history_returns_closed_rows`
- `test_get_fact_returns_none_when_absent`

`test_person_metrics.py`：
- `test_recompute_one_with_no_interactions_returns_cleared`
- `test_recompute_single_person_basic_counts`
- `test_recompute_all_rebuilds_multiple_people`
- `test_dormancy_calculation_bounds`
- `test_orphan_removal`
- `test_empty_person_id_returns_error`
- `test_ignores_rows_with_blank_person_id`

`test_people_render.py`（新增 3）：
- `test_people_render_emits_facts_and_metrics`
- `test_people_render_no_facts_section_when_empty`
- `test_people_render_facts_history_flag`
