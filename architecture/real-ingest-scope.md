---
title: 真实 iOS / WeChat / WhatsApp 落库 · 上线前的范围与门槛
status: scope
created: 2026-04-21
authoritative_at: C:\dev-projects\second-brain-hub\architecture\real-ingest-scope.md
---

# 真实数据落库 · 上线前的范围与门槛

## 为什么写这份

截止 `2693807`，hub 已经**写好了 4 个数据源的摄取代码**——
`ios_backup_locator` / `contacts_ingest_ios`（通讯录）/
`whatsapp_ingest_ios`（ChatStorage.sqlite）/ `wechat_sync`
（contact DB + chat JSON）——每一个都有 `--dry-run` 能跑通
（我们在 verify_ingest_dry_run.py 里确认过）。但**没有一条
真跑到过真实设备数据**。原因不是代码没写完，是上线有**很重的
前置条件**，一旦蹚错方向会污染 DuckDB / 引出错误的 T3 合并
候选，代价很高。

本文档**不写任何代码**，只定清楚：

1. 每条线到真跑 `--apply` 之间还缺什么
2. 什么风险必须先兜底
3. 分几步上线、每步的退出标志

## 四条摄取线的当前状态

| 数据源 | 代码就绪 | 已 dry-run 真数据？ | 已 apply 真数据？ | 门槛优先级 |
|---|---|---|---|---|
| iOS AddressBook（通讯录） | ✅ `contacts_ingest_ios.ingest_address_book_sqlite` | ❌ | ❌ | **P0**（最容易，收益最高） |
| iOS WhatsApp | ✅ `whatsapp_ingest_ios.ingest_chatstorage_sqlite` | ❌ | ❌ | P1 |
| WeChat（wechat-decoder 产物） | ✅ `wechat_sync.sync_all` | ❌ | ❌ | P2（依赖外部解包工具） |
| WeChat remark 抽取 | ✅ `wechat_remark_extract` | n/a（纯函数） | n/a | 随 P2 一起 |

**关键观察**：代码侧阻塞 = 0；**流程 & 前置条件**阻塞 = 全部。

## 公共前置条件（上线任何一条之前都必须具备）

### PC-1 · DuckDB 可回退快照
真跑 `--apply` 之前，**必须**先备一份 `brain-telemetry.duckdb` 到
`D:\second-brain-assets\_backup\telemetry\YYYYMMDD-HHMM-pre-ingest.duckdb`。
理由：ingest 会写 `persons` / `person_identifiers` / `interactions`
三张表；identity_resolver 可能 T2 自动合并；一旦出错只能整表还原。

**验收**：`brain ingest-backup-now` 存在（**未实现**，需要新增 ~20 行的 CLI
命令，这也是后面 B-ING-0 批要做的）。

### PC-2 · T3 合并候选阈值演练
当前 T3 的阈值来自 demo 数据。真实通讯录里会有**大量同姓同名**
（"张伟" / "李娟"）+ **少量多身份同一人**（同一个手机号在通讯录和微信都出现）。
需要先用**前 100 条真数据 dry-run** 看一眼：

- `merge_candidates` 被提多少条
- 里面多少条是真正"同一人"、多少是假阳性
- 假阳性率 > 10% 就调阈值后再往前

**验收**：手工 review 第一批 50 条 `merge_candidates` 全部处理完（`--apply-accept`
或 `--reject`），才允许吞第二批数据。

### PC-3 · Provenance trail
每一次 ingest 要在日志里记录：来源路径、快照 sha256、处理了多少行、
写了多少新 person / 多少新 interaction、用了多少秒。目前 ingest 函数返
回了 stats dict，但**没有把它写到 `telemetry_logs_dir` 的结构化日志**——
只是打 print。

**验收**：`logs/ingest-YYYY-MM-DD.jsonl` 每次 ingest 追加一行，字段包括
`source`, `source_sha256`, `started_at`, `elapsed_ms`, `persons_added`,
`interactions_added`, `t3_queued`。

### PC-4 · 回滚预案
任何一次 apply 之前，`structured.execute` 必须走 `BEGIN TRANSACTION`，
最外层 try/except 里回滚。当前 ingest 直接 `execute(...)` 无事务包裹。
这是**真数据上线的硬门槛**，必改。

## 分条线门槛

### 🟢 iOS AddressBook（P0，最该先上）

**为什么第一个上**：
- 通讯录是纯名-手机号-邮箱三元组，**歧义最少**
- 没有消息体，不涉及隐私敏感字段
- 一次 ingest 能把 T3 合并候选的"骨架"立起来

**额外门槛**：
- [ ] PC-1 ~ PC-4 全部达成
- [ ] 用户确认 `Manifest.db` 所在的 iTunes 备份是 **unencrypted** 的
      （加密备份 AddressBook.sqlitedb 读不出来；需要手工关掉加密重备）
- [ ] 用 `verify_ingest_dry_run.py` 对真实 `AddressBook.sqlitedb` 跑一次，
      肉眼看前 20 条输出

**预计落地工时**：PC-1 ~ PC-4 共约 4h；AddressBook 真跑约 30min
（dry-run → review → apply）。

### 🟡 iOS WhatsApp（P1）

**额外门槛**：
- [ ] AddressBook 已跑完、T3 已清空（骨架建起来，WhatsApp 才能挂载）
- [ ] 用户确认备份非加密
- [ ] `ChatStorage.sqlite` 中的**会话量**先数一下（用 `sqlite3` 直接 query
      `SELECT COUNT(*) FROM ZWAMESSAGE`）——超过 10 万条时，先 `--limit` 小批
      摄取，避免一次把 interactions 表塞爆
- [ ] 处理附件路径：**不**把媒体文件拷进 `brain-assets`，只记 `media_hint`
      字段作为指针；真要看再手工过去找。否则会爆盘

**预计**：2-3h（含 10 万条以内的完整摄取）。

### 🟠 WeChat（P2）

**最重的门槛**（代码最齐、流程最复杂）：
- [ ] 用户已用 `wechat-decoder`（外部工具）把**当前时刻**的 WeChat 数据
      解到 `D:\second-brain-content\wechat-decoder-export\` 类的固定位置
- [ ] 产出结构确认与 `wechat_sync.sync_all` 期望一致（contact DB + chats/*.json）
- [ ] 先跑 `wechat_remark_extract` 对 contact DB 过一遍 → 看 remark 抽取质量
      （低于 80% 命中就不要急着 apply，先补规则）
- [ ] `--since` 参数只摄取最近 30 天的消息，**老聊天不回溯**（否则 interactions
      会爆且意义递减）

**预计**：4-6h（大部分时间是外部 wechat-decoder 本身的使用与质量核验）。

## 上线步骤（严格有序）

| 步骤 | 内容 | 退出标志 | 工时 |
|---:|---|---|---:|
| B-ING-0 | ✅ **已完成（2026-04-21）**：`brain ingest-backup-now` + 三表事务包裹 + jsonl 日志 | PC-1 / PC-3 / PC-4 全过 | 4h |
| B-ING-1 | AddressBook 真跑 dry-run → review → apply — **Runbook: `bing1-runbook.md`** | T3 清空，person 数增量与通讯录条目数匹配 ±5% | 1d（含观察期） |
| B-ING-2 | T3 阈值再评估（基于 B-ING-1 的真实分布） | 阈值 hard-coded 改为 config 驱动 | 2h |
| B-ING-3 | WhatsApp 真跑（--limit 1000） | 抽 20 条消息对照原设备确认无错位 | 2h |
| B-ING-4 | WhatsApp 全量 | interactions 表不爆（< 500 MB） | 2h |
| B-ING-5 | WeChat dry-run → remark 抽取复核 → apply (--since 30d) | remark 命中率 ≥ 80% | 1d |
| B-ING-6 | 三条线 ingest 全跑完后重建 Kuzu + 扫 merge_candidates | F3 给出 ≥ 10 条高分候选 | 1h |

**总工时**：~3 个工日，跨度约 1 周（需要真实设备在手 + 外部工具配合）。

## 绝对不做的事

- ❌ **不**在 PC-1 ~ PC-4 全绿之前跑任何 `--apply`
- ❌ **不**尝试本地解密 WhatsApp/WeChat 加密库（用户已明确拒绝；按依赖外部备份）
- ❌ **不**在一次 ingest 会话里跨越两个数据源（一条线做完，备份，再下一条）
- ❌ **不**让 ingest 写 `asset_pointer` 之外的附件文件到 `brain-assets`
- ❌ **不**回溯老于 **1 年**的 WeChat/WhatsApp 消息（价值极低、噪音巨大）
- ❌ **不**在用户不在场时跑任何 `--apply`（本地个人数据，人必须在）

## 为什么现在只写文档、不开工

三点原因：

1. **B-ING-0 是代码活**（约 4h），但需要**等用户同意开这一摊**再动
   （涉及 DuckDB schema 迁移、日志改动，牵连面广）
2. **B-ING-1 需要真实设备接入**——用户的 iPhone + 一次 iTunes/Finder 备份
   的现场操作，AI 侧只能准备，不能代行
3. **T3 阈值调优**（B-ING-2）必须基于用户真实通讯录的分布决定，纸上推演没用

所以**推荐的动作是**：等用户下次说"开 B-ING-0"，就可以从 ingest-backup-now
CLI + 事务包裹开始。一旦 B-ING-0 合并，B-ING-1 就只欠用户做一次非加密备份。

## 和其他计划的关系

- `architecture/asset-migration-plan.md`：独立路径，可以和本计划并行
- `architecture/stage3-f3-kuzu-poc.md`：B-ING-6 会用到 Kuzu，届时真数据量
  会给 F3 第一次真正的压力测试
- `architecture/e1-weekly-maintenance-runbook.md`：B-ING-0 的 `ingest-backup-now`
  也应在 E1 周任务里挂一个"健康检查"步骤

## 变更记录

| 日期 | 说明 |
|---|---|
| 2026-04-21 | 首版；4 条线 × 4 公共门槛 × 7 步上线路线。 |
