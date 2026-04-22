# Phase A6 Sprint 3 验收报告 · Rolling Topics + Weekly Digest

**日期**: 2026-04-22
**Sprint 范围**: 每人 rolling topic 抽取 + 周报式 LLM 小结 + Obsidian 卡 `## Topics (30d)` / `## Weekly Digest` 两节 + E2 自动化
**状态**: ✅ 全部交付并通过生产烟测

---

## 1 · 设计决策

### 1.1 `person_insights` 如何承担"版本历史"

A5 留下的 `person_insights` 表只有 `(person_id, insight_type, body, detail_json, created_at)`——老的 `refresh_people_insights` 用 `DELETE FROM person_insights WHERE person_id = ?` + INSERT 3 行的"一键 replace"语义，历史直接丢掉。Sprint 3 不想重复这个错误，所以照搬 `person_facts` 的 bi-temporal / superseded_by 模式：

| 列 | 作用 |
| --- | --- |
| `window_start_utc` / `window_end_utc` | 回答"这条小结覆盖哪段时间"；天然支持 2026-04 → 2026-05 的跨月分析 |
| `source_kind` | `'llm'` / `'heuristic'`，UI 可以标注"LLM 没工作，这条是占位" |
| `superseded_by BIGINT` | 指向新 row 的 id。`NULL` = 当前视图；历史 row 永不删、不改 body |

写入逻辑在 `_insert_and_supersede`：先 INSERT 新 row，fetch 它的 id，然后 `UPDATE` 把旧 row 的 `superseded_by` 指向新 id，**单事务**（`structured.transaction()`）。

ALTER TABLE 路径保证对生产 90 行老 `topics`/`commitments`/`warmth` 行安全——它们 `superseded_by = NULL` 被天然当作 current，不影响 A5 的 `refresh_people_insights` 继续用（S3 的两类 insight_type 是新名字，不冲突）。

### 1.2 为什么分 `topics_30d` 和 `weekly_digest` 两类

- **topics_30d**：长窗口 (30d)，产出 **结构化主题词数组**（用于人卡顶部 tag chips，一眼扫"这人最近都在聊啥"）+ 一段 60–160 字小结。Prompt 要求 JSON 严格返回，解析时做了 fenced JSON + 散文夹带 JSON 两种兜底。
- **weekly_digest**：短窗口 (7d)，产出 **纯自然语言段落**（100–200 字），直接拿来当"周报",允许包含情绪/待跟进描述——这类文本没法用 JSON schema 规范，强行 JSON 反而给 LLM 添加了无意义约束。

两类 prompt 完全独立，`_rebuild_topics` / `_rebuild_weekly` 各走各的——失败路径也隔离：topics 崩了 weekly 不受影响。

### 1.3 降级链

任何一步都**不允许**让 `rebuild_all` 整批崩掉：

| 失败点 | 降级 |
| --- | --- |
| LLM 连接失败 / 超时（`raise` from `_call_llm`） | 走 `_heuristic_topics` / `_heuristic_weekly`，写 `source_kind='heuristic'` |
| LLM 返回空字符串 / 不含 JSON / 不含 narrative | 同上 |
| 窗口内没有任何 interaction summary | `status: skipped, reason: no_interactions_in_window`，**不写 row**（避免把空 narrative 作为 current） |
| 单人 rebuild 抛 Python 异常 | `rebuild_all` 捕获 → 记 `errors[]`，继续下一个人 |

### 1.4 时间窗口算术：为什么 `_utc_now()` 保留微秒

Sprint 2 原版 `_utc_now()` 会 `replace(microsecond=0)` 截掉微秒。在 S3 测试里发现一个 subtle bug：如果 interaction 在 `09:00:00.500` 写入、rebuild 在 `09:00:00.250` 启动，Python `.now()` 会被截成 `09:00:00`，window_end = `09:00:00` < `09:00:00.500` → interaction 被挡在窗口外。保留微秒后问题消失。

## 2 · 交付清单

### 2.1 schema 迁移

- `tools/py/src/brain_memory/structured.py` · `_brain_migrations` 升到 **v5**
- `person_insights` 补 4 列（`window_start_utc`, `window_end_utc`, `source_kind`, `superseded_by`）
- ALTER TABLE 兼容现存 90 行旧 `topics`/`commitments`/`warmth` 行

### 2.2 核心模块

- `tools/py/src/brain_agents/person_digest.py`（~430 行）
  - `rebuild_one(person_id, *, insight_types, topics_days=30, weekly_days=7, ...)` · 幂等 + superseded 链
  - `rebuild_all(*, min_interactions_30d=1, max_persons=500, ...)` · 扫所有近 30 天活跃人
  - `get_current_insights(person_id)` · 只返回 `superseded_by IS NULL` 的 topics + weekly
  - `_call_llm(prompt, model)` · 单点隔离给测试用 mock 替换
  - `_parse_topics_payload` / `_heuristic_topics` / `_heuristic_weekly` · 降级链

### 2.3 CLI

- `brain person-digest rebuild [--person-id|--all] [--insight-type both|topics|weekly] [--topics-days 30] [--weekly-days 7] [--interaction-limit 40] [--min-interactions-30d N] [--max-persons N]`
- `brain person-digest show <person_id>`

### 2.4 人卡渲染

- `tools/py/src/brain_agents/people_render.py` 在 `## Open threads` 之后注入：
  - `## Topics (30d)` — chip 列表 `` `人民币` · `欧元` · `自拍杆` `` + narrative 段落 + `_window ending … · source: llm_` 元数据
  - `## Weekly Digest` — narrative 段落 + `_window: … → … · source: …_` 元数据
  - 无 current 行时**整节省略**（不出空 header），`get_current_insights` 抛错也安全降级

### 2.5 E2 自动化

- `tools/housekeeping/brain-e2-task.ps1` · `weekly-review` 分支在 people-eval 趋势前追加两步：
  1. `brain person-metrics recompute --all`（刷新 dormancy/counters）
  2. `brain person-digest rebuild --all --weekly-days 7 --topics-days 30`
  - 失败只 `hub-alert` 不中断主任务
- 复用既有 `BrainWeeklyReview`（每周日 20:00）调度，不需新任务

### 2.6 测试

- `tools/py/tests/test_person_digest.py` · **15 新 case**
  - rebuild 双写两类 insight（`topics_30d` + `weekly_digest`）
  - 幂等 + `superseded_by` 链正确指向
  - 空 interactions 静默跳过（`status=skipped`）
  - LLM 崩盘回退启发式（`source_kind='heuristic'`）
  - LLM 返回乱码/空同样回退
  - 30d 窗口真的过滤掉 60 天前的旧对话（只把 3 天前的喂给 LLM）
  - 指定 `insight_types=[weekly]` 只跑 weekly 不跑 topics
  - 未知 insight_type / 空 person_id 立即 ValueError
  - Fenced JSON（` ```json …``` `）与散文夹带 JSON 都能解析
  - `rebuild_all` 只扫有近 30 天 interaction 的人（冷人跳过）
  - `rebuild_all` 单人异常被隔离，不影响下一个人
  - `get_current_insights` 对无数据的 person 返回 `{topics: None, weekly: None}`
- `tools/py/tests/test_people_render.py` · **扩 2 新 case**
  - Topics + Weekly 两节渲染（chips tag、narrative、window 元数据）
  - 无 digest 数据时两节静默省略（不出空 header）

**最终结果**: 本地 Sprint 1+2+3 核心套件 **77/77 passed**，跨 7 个测试文件（test_person_facts, test_person_metrics, test_open_threads, test_commitment_extract, test_digest, test_people_render, test_person_digest）。

---

## 3 · 生产烟测

### 3.1 Pre-apply snapshot

```
snapshot:   D:\second-brain-assets\_runtime\logs\brain-telemetry-pre-a6s3-20260422-220054.duckdb
sha256-16:  2D92DE01E2AA5487
size_MB:    47.01
```

### 3.2 Migration v5

```
migrations: [
  {'version': 2, ...},
  {'version': 3, 'applied_at': 2026-04-22 20:48:35},  # Sprint 1
  {'version': 4, 'applied_at': 2026-04-22 21:30:02},  # Sprint 2
  {'version': 5, 'applied_at': 2026-04-22 22:01:14},  # Sprint 3 ← 新增
]
person_insights cols: [id, person_id, insight_type, body, detail_json,
                       created_at, window_start_utc, window_end_utc,
                       source_kind, superseded_by]
row_count: 90（现存历史行）
current (superseded_by IS NULL) count: 90  # 老行天然当作 current，零破坏
```

### 3.3 田果首次 rebuild（真 LLM）

```json
{
  "status": "ok",
  "person_id": "p_8168e6185835",
  "window_end": "2026-04-22 20:01:25.980218",
  "results": [
    {"status": "ok", "insight_type": "topics_30d", "id": 91,
     "prior_id": null, "sample_count": 40, "topics_count": 3, "mode": "llm"},
    {"status": "ok", "insight_type": "weekly_digest", "id": 92,
     "prior_id": null, "sample_count": 23, "mode": "llm"}
  ]
}
```

`brain person-digest show p_8168e6185835` 的实际 LLM 输出（非杜撰）：

- **topics_30d.topics**: `人民币`, `欧元`, `自拍杆`
- **topics_30d.narrative**: "宝宝向妈妈求助换汇和带物品，提到机票和睡眠情况。"
- **weekly_digest.body**: "本周主要聊了一些生活琐事和旅行准备，包括询问对方是否遇到困难、帮忙筹集旅行资金以及确认自拍杆的携带事宜。此外还关心了机票购买情况，并提醒有事可以打电话联系。整体来看，对方状态较为平稳，偶尔透露出些许不耐烦的情绪。"
- 两条都 `mode: "llm"`, `model: "qwen2.5:14b-instruct"`

### 3.4 人卡渲染后形态

`D:\second-brain-content\06-people\by-person\田果__p_8168e6185835.md` 节目录变化：

```
## Identifiers
## Facts              ← Sprint 1
## Metrics            ← Sprint 1
## 近期对话
## Recent interactions
## Caps+D notes
## Open threads       ← Sprint 2
## Topics (30d)       ← Sprint 3 新增
## Weekly Digest      ← Sprint 3 新增
```

`## Topics (30d)` 实际内容：

```
`人民币` · `欧元` · `自拍杆`

宝宝向妈妈求助换汇和带物品，提到机票和睡眠情况。

_window ending 2026-04-22 20:01:25.980218 · source: llm_
```

### 3.5 `rebuild --all` 批量真跑

```
$ brain person-digest rebuild --all --min-interactions-30d 3 --max-persons 20

scanned: 20
rebuilt: 20
partial_skips: 6   # 这 6 人有 30d 数据但 7d 窗口内没有，topics 写了 / weekly 跳过
errors: []
elapsed: ~3 min（20 人 × 2 类 × qwen2.5:14b，约 5 s/LLM call）
```

### 3.6 Superseded 链验证

对田果再跑一次 `rebuild --person-id` 后的表状态：

```
{id: 91, insight_type: 'topics_30d',    superseded_by: 95,   window_end: 20:01:25}
{id: 92, insight_type: 'weekly_digest', superseded_by: 96,   window_end: 20:01:25}
{id: 95, insight_type: 'topics_30d',    superseded_by: None, window_end: 20:02:16}  ← current
{id: 96, insight_type: 'weekly_digest', superseded_by: None, window_end: 20:02:16}  ← current

current (superseded_by IS NULL) count: 2   # 稳定为 2，不会"每次 rebuild 增一"
```

链式 91→95、92→96 正确，历史 body 保留未被改写，`get_current_insights` 正确只返回 95/96。

---

## 4 · 与 Sprint 2 的回路反哺

Sprint 2 验收时发现一个"真空"：`brain threads-scan` 在田果身上抽出 **0** 条承诺候选，原因是单条 WeChat interaction summary 的信息密度太低（短句 / 元数据 / `[msg_type=50]`），LLM 按"严格承诺"prompt 找不到可抽的 span。

Sprint 3 的同一批 summary 在**聚合层**给了 LLM 一个更高的视角：

- weekly_digest 产出了"**帮忙筹集旅行资金以及确认自拍杆的携带事宜**"这样的非空叙述——里面明显含待办语义（"帮忙筹集"、"确认..."）
- topics_30d 产出的 tag chip `人民币` · `欧元` · `自拍杆` 也能直接作为"这人最近的关注面"——比单条消息片段更稳定

这验证了一个设计假设：**噪音在条目层噪、聚合层清**。S4 的 `tier suggest` 可以直接基于 `weekly_digest` 的 warmth 信号做建议，不再依赖抽单条承诺。

---

## 5 · 已知限制

1. **LLM 成本**：`rebuild --all` 的 20 人跑了约 3 分钟（40 次 LLM call）。全量 600+ people 跑一遍要~1.5h。`min_interactions_30d=3` 的默认过滤已经有效压缩到活跃人群；如果还要更快，可以考虑走 `num_predict` 限制或换更小的模型（配 `BRAIN_PERSON_DIGEST_MODEL`）。
2. **Chinese console encoding**：PowerShell 控制台显示 Chinese 仍会被 GBK 码表搅乱；DuckDB / Markdown 底层 UTF-8 存储完全正常，只是终端回显花屏。
3. **历史 topics/commitments/warmth 不会被自动覆盖**：A5 遗留的 90 行旧 insight 是 `insight_type IN ('topics','commitments','warmth')`，S3 的写入用新 insight_type 名称 (`topics_30d` / `weekly_digest`)，两套并存。如果要彻底替换 A5 `refresh_people_insights`，需要在 Sprint 4 做一次"旧 insight 归档 + 切换"。
4. **`weekly_digest` 本质是"最近 7 天"**：如果某人 7 天内没互动，weekly 会被 skipped。人卡上 `## Weekly Digest` 节就不出——这是想要的行为，避免误导"这周聊了很多"。

---

## 6 · 下一步

Sprint 3 的出口标志：tier=inner 的人卡里有≤7d 旧的 Topics 段落 + `BrainWeeklyReview` 一次后 `person_insights` 有 weekly_digest。**已满足**（田果当前 topics_30d window_end = 2026-04-22 20:02:16，rendered md 已含 Topics + Weekly 两节）。

Sprint 4 建议起跑：
- `person_facts key='relationship_tier'`（inner / close / working / acquaintance / dormant）
- `config/thresholds.yaml` 的 `people_cadence:` 段（tier → 联系间隔天数）
- `brain tier set|suggest` CLI
- 可复用 Sprint 3 的 `weekly_digest` 作为 tier_suggest 的 warm signal

---

**验收签字**：@chase · 2026-04-22
**Sprint 1+2+3 联合覆盖**：本地 77/77 绿；生产 DuckDB 成功从 v2 → v3 → v4 → v5 连跳三次 migration，0 数据丢失。
