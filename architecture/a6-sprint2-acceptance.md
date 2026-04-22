# Phase A6 Sprint 2 · Acceptance Report

**日期**: 2026-04-22
**范围**: `open_threads` 到期化 + LLM 承诺抽取 + daily digest + Obsidian 渲染
**结论**: ✅ 交付，生产已上线，全部退出标志达成

---

## 1. 设计决策

| 决策点 | 选项 | 理由 |
|---|---|---|
| A · `due_utc` 类型 | **TIMESTAMP**（非 DATE） | 一些承诺带具体时间（"下午 3 点前反馈"）；date-only 输入（`"2026-05-01"`）自动 snap 到 23:59:59 UTC，保证"当天任何时刻都算没到期" |
| B · LLM 抽取模式 | **选项 1：dry-run + 人工 --apply 两步制** | 与 Sprint 1 `merge-candidates --auto-apply-min-score` 一致的审慎传统；Ollama 误报可控 |
| C · 幂等策略 | **body_hash（每人级 SHA256 前 16）** | 重扫不重复写；manual 入口无 hash 所以人工重复输入合法 |
| D · 状态机 | **open → done / dropped / reopen** | 扁平、可审计；done 与 dropped 语义区分 |

---

## 2. 交付物

### 2.1 DuckDB schema v4
`open_threads` 新增 7 列，对 6192 行既有数据 **0 破坏性**（纯 ALTER TABLE ADD COLUMN）：

| 新列 | 类型 | 作用 |
|---|---|---|
| `due_utc` | TIMESTAMP | 承诺到期时刻（可空） |
| `promised_by` | VARCHAR | `self` \| `other`（我欠对方 vs 对方欠我） |
| `last_mentioned_utc` | TIMESTAMP | 最后一次在聊天里被提到（LLM 重扫时刷新） |
| `source_interaction_id` | BIGINT | 回溯到源 interaction |
| `source_kind` | VARCHAR | `manual` \| `llm_extracted` \| … |
| `body_hash` | VARCHAR | 每人级幂等键（sha256 前 16） |
| `created_at` | TIMESTAMP | 审计字段 |

迁移 migration 在 `brain_memory.structured._ensure_v2_tables` 里，向后兼容；version 表自动从 3 → 4。

### 2.2 新增模块

| 模块 | 行数 | 覆盖 |
|---|---|---|
| `brain_agents/open_threads.py` | ~330 | 7 公开 API：`add_thread` / `close_thread` / `reopen_thread` / `update_due` / `list_threads` / `list_due` / `get_thread` / `classify_due` |
| `brain_agents/commitment_extract.py` | ~230 | `scan_commitments` + `_parse_candidates` + `_call_llm`（注入点） |

### 2.3 CLI

| 命令 | 说明 |
|---|---|
| `brain thread add <pid> "<body>" [--due YYYY-MM-DD] [--promised-by self/other] [--source-kind] [--force]` | 手动记录承诺 |
| `brain thread close <id> [--status done/dropped]` | 状态机：open → done/dropped |
| `brain thread reopen <id>` | done/dropped → open |
| `brain thread update-due <id> [--due …]` | 修改或清空到期 |
| `brain thread list [--person-id] [--status open/all] [--limit]` | 列表查询 |
| `brain due [--within 7] [--person-id] [--overdue-only]` | 到期+超期清单，overdue 最先 |
| `brain threads-scan [--since-days 14] [--per-person-limit 30] [--max-persons 50] [--min-confidence 0.6] [--apply]` | LLM 候选抽取，默认 dry-run |

### 2.4 Obsidian 渲染
`people_render` 的 `## Open threads` 节从单行列表升级为 6 列表格：

```
| status | due | who owes | body | last seen | source |
| --- | --- | --- | --- | --- | --- |
| ⏳ soon | 2026-04-29 23:59:59 | self | 下周三寄书给她 | 2026-04-22 19:45:14 | demo |
```

- `classify_due()` 产出 4 芯片：⚠️ overdue / 🔥 today / ⏳ soon / later
- 空状态依然显示 `(none)`（向后兼容旧卡）
- 闭合线程不显示（保持卡只展示"仍欠着的"）

### 2.5 Daily digest
`generate_daily_digest()` 在"Overdue Contacts"之后新增两节：

```markdown
## Today's Commitments
- [self] `p_a984659b7fd9` 帮他看一下简历改进意见 (due 2026-04-22 23:59:59)

## Overdue Commitments
- [other] `p_e1dc884806aa` 她承诺下周发照片过来 (due 2026-04-20 23:59:59)  · **1d overdue**
```

返回 JSON 加 `due_today_count` / `overdue_commitments_count` 便于未来监控。

---

## 3. 测试 (pytest +34 case)

| 文件 | 用例 | 覆盖 |
|---|---|---|
| `test_open_threads.py` | **17** | add 最小/带 due/日期-only snap / required 字段 / promised_by 枚举 / body_hash 去重 / manual 不去重 / --force / close 状态机 / 未知 status reject / 未找到 / reopen / update-due set 和 clear / list 过滤 / list_due within+overdue / list_due 排除 closed / classify_due 4 桶 |
| `test_commitment_extract.py` | **12** | parse 正常 JSON / 代码块围栏 / 散文中回收 / 垃圾降级空 / 坏条目过滤 / dry-run 不写 / apply 写入 / apply 幂等 / min_confidence 过滤 / LLM 崩溃隔离 / person_id 过滤 / source_interaction_id 回填 |
| `test_digest.py` | **3** | 2 节双路径 / 无承诺时 (none) 占位 / 已关闭线程不出现 |
| `test_people_render.py` 扩展 | **+2** | Open threads 表格渲染（overdue+soon 芯片）/ 空状态不渲染表头 |

**核心套件**: 60 / 60 passed（S1 + S2）

---

## 4. 生产烟测

### 4.1 Pre-apply snapshot
```
path: D:\second-brain-assets\_runtime\logs\20260422-214452-a6-sprint2-pre-apply.duckdb
sha256 (first 16): AC6D82DE6EB4A7C2
size: 47.01 MB
```

### 4.2 Migration
```
_brain_migrations.version: 3 → 4
open_threads columns: 6 → 13 (0 rows touched)
ALTER TABLE errors: 0
```

### 4.3 三条手动承诺

| id | person_id | body | due_utc | promised_by | 预期 bucket |
|---|---|---|---|---|---|
| 1 | `p_8168e6185835` (田果) | 下周三寄书给她 | 2026-04-29 23:59:59 | self | ⏳ soon |
| 2 | `p_a984659b7fd9` | 帮他看一下简历改进意见 | 2026-04-22 23:59:59 | self | 🔥 today |
| 3 | `p_e1dc884806aa` | 她承诺下周发照片过来 | 2026-04-20 23:59:59 | other | ⚠️ overdue (1d) |

### 4.4 `brain due --within 10` 输出
按预期：overdue 优先 → today → soon。全部 body_hash 不为空，`source_kind='demo'`。

### 4.5 `brain threads-scan --since-days 30 --max-persons 10` (dry-run)
```json
{
  "status": "ok",
  "mode": "dry-run",
  "scanned_persons": 10,
  "model": "qwen2.5:14b-instruct",
  "candidates": [],
  "candidate_count": 0,
  "errors": []
}
```
**22s 完成，0 错误，0 幻觉候选**。

**分析**：抽出的 summaries 多为 `[msg_type=50]` / `没有` / `你还会什么歌来着` 等低信息元数据，Ollama 正确返回 `[]`（遵循 prompt 的"只抽取真实承诺"约束）。这反而证明了 prompt 设计是 conservative 的，也是 **Sprint 3 interaction summaries 必要性** 的直接证据——有了真正的一句话摘要，重扫 `threads-scan` 会显著提升 recall。这是**已知限制**，不是 bug。

### 4.6 Daily digest 产物
`D:\second-brain-content\08-indexes\digests\daily-2026-04-22.md`：

```
## Today's Commitments
- [self] `p_a984659b7fd9` 帮他看一下简历改进意见 (due 2026-04-22 23:59:59)

## Overdue Commitments
- [other] `p_e1dc884806aa` 她承诺下周发照片过来 (due 2026-04-20 23:59:59)  · **1d overdue**
```
返回 JSON：`due_today_count=1`, `overdue_commitments_count=1` ✓

### 4.7 田果卡重渲染
`D:\second-brain-content\06-people\by-person\田果__p_8168e6185835.md`

```markdown
## Open threads

| status | due | who owes | body | last seen | source |
| --- | --- | --- | --- | --- | --- |
| ⏳ soon | 2026-04-29 23:59:59 | self | 下周三寄书给她 | 2026-04-22 19:45:14 | demo |
```
✓

---

## 5. 已修 Bug（在测试 + 生产验证里发现）

1. **date-only `--due` 被 `fromisoformat` 解析成 00:00:00** → 加了"无时间分量检测"逻辑，自动 snap 到 23:59:59 UTC（`test_add_thread_date_only_gets_end_of_day`）
2. **`list_due(within_days=0, include_overdue=False)` 边界**：原来用 `BETWEEN now AND horizon`，时间戳竞争会漏掉 due_utc=now 的线程 → 改成 `BETWEEN day_start AND horizon`（`test_list_due_includes_overdue_and_future`）
3. **daily digest "Today's Commitments" 漏 23:59 到期线程**：`list_due(within_days=0)` 的 horizon=wall_clock_now，19:45 < 23:59 导致当日末尾的承诺被漏掉 → 改成 `within_days=1` 然后 Python 侧按 `day_end` 二次过滤（生产烟测首次复现，一次修好）

---

## 6. 退出标志核验

| 退出标志 | 状态 |
|---|---|
| schema v4 (`open_threads` 补 7 列) 上生产库 0 error | ✅ |
| `brain thread add/close/reopen/list` + `brain due` CLI 可用 | ✅ |
| `brain threads-scan --dry-run` LLM 跑通无崩盘 | ✅（10 persons / 0 candidates / 0 errors / 22s） |
| `people_render` `## Open threads` 表格 + 芯片 | ✅（田果卡已验证） |
| `generate_daily_digest` 两节落 md | ✅ |
| pytest 新增 ≥ 15 case | ✅ **交付 34** |

---

## 7. 已知局限 / Sprint 3 & 4 接力点

1. **LLM recall 受限于 summary 质量**：WeChat interactions 的 summary 当前是 raw 消息或 `[msg_type=50]` 元数据，缺乏对话级摘要。Sprint 3 的 rolling topics 需要先把 summaries 生成出来（可考虑 30d batch 一次），然后 `threads-scan` 复扫会有质的变化。
2. **`promised_by` 仍是二元**：未来可扩 `both` 或 `team` 语义（Sprint 4 tier 落地后一起看）
3. **没有提醒通知**：到期只在 daily digest 里提示，没主动推送。E2 下一轮 `BrainRelationshipAlerts` 可以把 overdue commitments 加进去。

---

## 8. 下一步

Sprint 3: Rolling topics + weekly digest（`person_insights(insight_type='topics_30d')`）。这同时会反哺 Sprint 2 的 LLM recall 问题。
