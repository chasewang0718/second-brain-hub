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

本文档以范围与验收为主（B-ING-0 相关代码已落在仓库）；这里只定清楚：

1. 每条线到真跑 `--apply` 之间还缺什么
2. 什么风险必须先兜底
3. 分几步上线、每步的退出标志

## 四条摄取线的当前状态

| 数据源 | 代码就绪 | 已 dry-run 真数据？ | 已 apply 真数据？ | 门槛优先级 |
|---|---|---|---|---|
| iOS AddressBook（通讯录） | ✅ `contacts_ingest_ios.ingest_address_book_sqlite` | ❌ | ❌ | **P0**（最容易，收益最高） |
| iOS WhatsApp | ✅ `whatsapp_ingest_ios.ingest_chatstorage_sqlite` | ✅（2026-04-22） | ✅（2026-04-22） | P1 |
| WeChat（wechat-decoder 产物） | ✅ `wechat_sync.sync_all` | ✅（2026-04-22） | ✅（2026-04-22） | P2（依赖外部解包工具） |
| WeChat remark 抽取 | ✅ `wechat_remark_extract` | n/a（纯函数） | n/a | 随 P2 一起 |

**关键观察**：代码侧阻塞 = 0；**流程 & 前置条件**阻塞 = 全部。

## 公共前置条件（上线任何一条之前都必须具备）

### PC-1 · DuckDB 可回退快照 ✅（B-ING-0）
真跑 `--apply` 之前，**必须**先备一份 `brain-telemetry.duckdb` 到
`_backup/telemetry/<ts>-<label>.duckdb`（sha256 sidecar + pointer-log）。
理由：ingest 会写 `persons` / `person_identifiers` / `interactions`
三张表；identity_resolver 可能 T2 自动合并；一旦出错只能整表还原。

**实现**：`brain_agents/ingest_backup.py` · CLI `brain ingest-backup-now [--label]`。

### PC-2 · T3 合并候选阈值演练
当前 T3 的阈值来自 demo 数据。真实通讯录里会有**大量同姓同名**
（"张伟" / "李娟"）+ **少量多身份同一人**（同一个手机号在通讯录和微信都出现）。
需要先用**前 100 条真数据 dry-run** 看一眼：

- `merge_candidates` 被提多少条
- 里面多少条是真正"同一人"、多少是假阳性
- 假阳性率 > 10% 就调阈值后再往前

**验收**：手工 review 第一批 50 条 `merge_candidates` 全部处理完（`--apply-accept`
或 `--reject`），才允许吞第二批数据。

### PC-3 · Provenance trail ✅（B-ING-0）
每一次 ingest 要在结构化日志里记录：来源路径、快照 sha256、近似开始/结束时刻、
处理统计、耗时。三条摄取线均在 apply（及可选 dry-run）末尾调用 `log_ingest_event`。

**实现**：`brain_agents/ingest_log.py` · 默认路径
`<telemetry_logs_dir>/ingest-YYYY-MM-DD.jsonl` · CLI `brain ingest-log-recent`。

**字段**（节选）：`source`, `mode`, `source_path`, `source_sha256`（apply 才有）,
`started_at`（显式传入或根据 `ts_utc`−`elapsed_ms` 推导）, `elapsed_ms`,
`persons_added`, `interactions_added`, `t3_queued`, `backup`, `detail`。

### PC-4 · 回滚预案 ✅（B-ING-0）
三条摄取（AddressBook / WhatsApp iOS / WeChat `sync_all`）在 `--apply` 且未关闭
`wrap_transaction` 时，写 DuckDB 的路径包在 `brain_memory.structured.transaction()`
里：失败则 `ROLLBACK`，成功则 `COMMIT`。

**实现**：`brain_memory/structured.py` 的 `transaction()` 上下文（禁止嵌套）。

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
| B-ING-1 | ✅ **已完成（2026-04-22）**：AddressBook 主库 apply 248/248，snapshot `20260422-011824-bing1-ios-addressbook.duckdb`。事后发现 5 项问题 → **`bing1-followups.md`**（runbook: `bing1-runbook.md`） | T3 清空，person 数增量与通讯录条目数匹配 ±5% | 1d（含观察期） |
| B-ING-2 | T3 阈值再评估（基于 B-ING-1 的真实分布） | 阈值 hard-coded 改为 config 驱动 | 2h |
| B-ING-3 | ✅ **已完成（2026-04-22）**：WhatsApp dry-run + apply（1451 rows） | 抽样消息时间/peer/preview 与设备侧一致 | 2h |
| B-ING-4 | ✅ **已完成（2026-04-22）**：WhatsApp 全量（同批完成） | `interactions` 新增 1451，库体量稳定（snapshot 可回滚） | 2h |
| B-ING-5 | ✅ **已完成（2026-04-22）**：WeChat dry-run + apply（`--since 30d`） | 首次真跑落地，后续按批次扩 chat JSON 覆盖面 | 1d |
| B-ING-5.1 | Caps+D 文本 → `person_notes` 冒烟验收 | `[people-note: ...]` 能写入 `person_notes` 且 linked_person 命中 | 0.5h |
| B-ING-6 | Kuzu 重建 + `sync-from-graph` 扫 merge_candidates | 图文件无并发锁；给出候选或明确 0-candidate 原因 | 1h |

**总工时**：~3 个工日，跨度约 1 周（需要真实设备在手 + 外部工具配合）。

## 绝对不做的事

- ❌ **不**在 PC-1 ~ PC-4 全绿之前跑任何 `--apply`
- ❌ **不**尝试本地解密 WhatsApp/WeChat 加密库（用户已明确拒绝；按依赖外部备份）
- ❌ **不**在一次 ingest 会话里跨越两个数据源（一条线做完，备份，再下一条）
- ❌ **不**让 ingest 写 `asset_pointer` 之外的附件文件到 `brain-assets`
- ❌ **不**回溯老于 **1 年**的 WeChat/WhatsApp 消息（价值极低、噪音巨大）
- ❌ **不**在用户不在场时跑任何 `--apply`（本地个人数据，人必须在）

## 上线节奏说明

1. **B-ING-0 已合并**：PC-1 / PC-3 / PC-4 在代码侧关闭；真跑前仍须手工执行
   `brain ingest-backup-now` 与人工复核 dry-run。
2. **B-ING-1 需要真实设备**：非加密 iTunes/Finder 备份 + `AddressBook.sqlitedb`。
3. **B-ING-2（T3 阈值）**依赖 B-ING-1 后的真实分布，不能纸上调参。

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
| 2026-04-22 | PC-1~PC-4 节与 B-ING-0 实现对齐；PC-3 补充 `started_at` 字段说明；删除「只写文档」旧段落。 |
| 2026-04-22 | **B-ING-3/B-ING-4 收官**：`backup-ios-locate` 命中 `ChatStorage.sqlite`（`7c7f...`，2,039,808 bytes）；先 dry-run（limit 30）后 apply 全量（`rows_seen=1451` / `inserted=1451` / `persons_created=57` / `messages_without_peer=0` / `elapsed_ms=7280.3`）。预先快照 `20260422-091535-bing3-whatsapp-pre-apply.duckdb`（sha `46b6c9c4...`）；审计日志 `ingest-log-recent` 记录 `source=whatsapp_ios mode=apply status=ok`，并自动回填 `backup` 描述。 |
| 2026-04-22 | **B-ING-5 收官**：`brain wechat-sync --dry-run` 命中 `contact.db`（6192 contacts）+ `chat_20292966501@chatroom.json`（would_insert=50），随后 `brain wechat-sync --since 2026-03-23T11:33:07` 真跑成功：`persons_created=6192`、`identifiers_added=609`（`wechat_alias`）、`interactions_added=50`、`chats_processed=1`、`elapsed_ms=111333.9`。预先快照 `20260422-093307-bing5-wechat-pre-apply.duckdb`（sha `1c8d43da...`）。落库核对：`person_identifiers.kind=wxid` 6192、`kind=wechat_alias` 609、`interactions.source_kind=wechat` 50。 |
| 2026-04-22 | **B-ING-5.1 收官**：用 `brain text-inbox-ingest` 导入 `[people-note: Hammond]` 样本，落地到 `D:\second-brain-content\99-inbox\_draft\people-note-hammond.md`；postprocess 返回 `people_notes_written=1`、`linked_person=p_0ac7536db641`、`cloud_enqueued=false`。DB 核对新增 `person_notes.source_kind='capsd-people-note'` 行，`detail_json` 包含 `tag_name=Hammond`。 |
| 2026-04-22 | **B-ING-6 现场阻塞记录**：`graph-stats` 可返回 `Person=1550`，但 `merge-candidates sync-from-graph` 多次遇到 Kuzu 文件并发锁（`Could not set lock on ... brain.kuzu`）；清理残留 `graph-rebuild-if-stale` 进程后可跑通 dry-run，但当前返回 `proposed=0`。后续需在单 writer 窗口完成一次 clean graph rebuild，再复跑 B-ING-6 验证候选是否真实为 0。 |
