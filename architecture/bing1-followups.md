---
title: B-ING-1 · 首次 apply 的 follow-ups
status: open
created: 2026-04-22
authoritative_at: C:\dev-projects\second-brain-hub\architecture\bing1-followups.md
related:
  - architecture/bing1-runbook.md
  - architecture/real-ingest-scope.md
---

# B-ING-1 · 首次 apply 的 follow-ups

B-ING-1 本身已 ✅（248/248，snapshot `20260422-011824-bing1-ios-addressbook.duckdb`，sha `53ad43bd…`）。  
本文档只记录真跑之后冒出来、**不阻塞打勾**、但**必须在 B-ING-3 WhatsApp 上线前**处理的问题。

| 编号 | 标题 | 紧迫度 | 范围 |
|------|------|--------|------|
| **B-ING-0.1** | Phone normalizer: NL 本地 `06…` → `+316…`（并扩到通用「本地国家码」规则） | **HIGH**（直接造成真·重复） | 代码 |
| **B-ING-1.4** | `ios_backup_locator` 选优：不要选空子库 | MEDIUM（坑新手 / 老练用户手动 `--db` 绕过） | 代码 |
| **B-ING-1.5** | 清理 DuckDB 里的 T-fixture 污染（174 persons + 8 merge_log） | MEDIUM（噪音干扰 sync-from-graph） | 数据清理 + 加测试隔离 |
| **B-ING-1.6** | 加 `merge-candidates enqueue-manual --pair` 子命令（解决"同名无 shared identifier"的人工合并） | MEDIUM（多处真·重复需要它） | 代码 |
| **B-ING-1.7** | `ingest_events.backup` 字段回填最近一次 snapshot 路径/sha | LOW（审计完备性） | 代码 |
| **B-ING-1.8** | 手动处理 9 组真·重复（Cheng Wang 等） | 在 1.4 / 0.1 / 1.6 完成后再跑 | 数据 |

---

## B-ING-0.1 · Phone normalizer 补 NL 本地号（并泛化）

### 现象

本次 apply 在 `person_identifiers` 里写入了下列三对、**逻辑上同号、`value_normalized` 不同**的记录：

| 名字 | `value_normalized` / `value_original` |
|------|---------------------------------------|
| Hammond | `31615156595` / `+31615156595` vs `0615156595` / `0615156595` |
| Jerrel | `31615556491` / `+31615556491` vs `0615556491` / `(06) 15 55 64 91` |
| Patricia | `31683165725` / `+31683165725` vs `0683165725` / `(06) 83 16 57 25` |

正常化逻辑把带 `+` 的号剥成 `31…`，但对 iOS 里存的 **纯本地号 `06…`**（没有国家前缀）不处理，于是同一个号在两份 iOS 卡上被写成两个不同的 `value_normalized`，T3 `sync-from-graph` 自然认不出重合。

### 根因

`contacts_ingest_ios` 的 phone normalizer 没有「默认国家上下文」假设，把未带 `+` 的号当成「原样字符串」存。

### 修复方向

1. 增加 **默认国家码**配置（例如 `config/paths.yaml` 或 `config/normalize.yaml`），
   - `default_country: NL`（从 iOS AddressBook 元数据 / device locale / 用户在 `paths.yaml` 手配 三者其一推导；优先级：AddressBook > device > config）。
2. 引入 **本地号前缀映射表**：
   - NL `0` → `+31 `
   - UK `0` → `+44 `
   - DE `0` → `+49 `
   - CN `0` → `+86 `（大陆一般直接存 11 位手机号不带 `0`，但固话带 `0`；要谨慎）
   - 必须只在**没有 `+` 前缀**且**号首位为 `0`**时触发，避免误伤。
3. 复用成熟库（推荐 **`phonenumbers`** — Google libphonenumber Python binding），而不是自己写 regex；按 `default_country` 解析 → 存 `value_normalized` 为 E.164 / 不带 `+` 的纯数字。
4. 加 pytest：NL / UK / DE 本地号、国际号、纯数字、带空格/括号/连字符、短号（救援号、10xxx）的矩阵。

### 验收

- 前后两次 `contacts-ingest-ios`（同一份 `AddressBook.sqlitedb`）在 **归一化后** 的 `value_normalized` 集合保持幂等。
- Hammond/Jerrel/Patricia 在新 ingest 后自动合并（`persons_created` 对应减少；`merge-candidates sync-from-graph` 产生 shared identifier 候选或 ingest 内直接 dedup 到 1 个 person）。

---

## B-ING-1.4 · `ios_backup_locator` 不要选空子库

### 现象

`backup-ios-locate` 自动把命中列表里**第一条** `Library/AddressBook/Family/<uuid>:22AddressBook.sqlitedb`（Source ID 22 的来源子库）选为 `selected`，但那份子库 `person_rows: 0`。真正含 248 行的主库 `Library/AddressBook/AddressBook.sqlitedb` 排在列表第 5。

### 修复方向

在 `locate_bundle` 的选优里：

1. **硬优先**：若命中 `Library/AddressBook/AddressBook.sqlitedb`（无 `Family/` 子路径），直接选它。
2. **次优先**：若只命中 Family 子库，用 `sqlite3` 打开取 `SELECT COUNT(*) FROM ABPerson`，选**行数最多的那份**（并附 tie-break 规则）。
3. CLI 输出里暴露 `candidates`（所有命中 + 各自 `person_count`）+ `selected` 的选择理由字段 `selected_reason`，方便人工验收。

### 验收

- 本次这份 UDID 备份上重跑 `backup-ios-locate`，`selected` 自动落在 `31/31bb...`（主库）。
- 单测覆盖：多命中 / 主库缺失 / 全空子库三种场景。

---

## B-ING-1.5 · 清理 DuckDB 里的 T-fixture 污染

### 现状（2026-04-22 扫描）

| 表 | T-fixture 引用数 |
|----|------------------|
| `persons`（primary_name `LIKE 'T %'`） | **174** |
| `merge_log.kept_person_id` | **8** |
| `merge_log.absorbed_person_id` | 0 |
| `person_identifiers.person_id` | 0 |
| `interactions.person_id` | 0 |
| `open_threads.person_id` | 0 |
| `person_notes.person_id` | 0 |
| `person_insights.person_id` | 0 |
| `merge_candidates` | **未确认**（列名不叫 `person_id`，下方扫描脚本需扩展） |

T 前缀：`T Bad A/B ×29`、`T Reject A/B ×29`、`T Acc A/B ×13-16`、`T Keep A/B ×13-16`。**应来自 merge_candidates 测试**，早期测试跑在真 telemetry.duckdb 上留下的。

### 清理前补齐扫描

```sql
SELECT column_name, data_type
FROM duckdb_columns()
WHERE schema_name='main' AND table_name='merge_candidates'
ORDER BY column_index;
```

若 `merge_candidates` 含如 `person_a`, `person_b` 或 `candidate_person_id`、`target_person_id` 这类非 `*person_id*` 命名的 FK，要先清完再删 persons。

### 清理 SQL（确认后按事务执行）

```sql
BEGIN TRANSACTION;

-- 1) merge_log 里引用 T 的记录
DELETE FROM merge_log
WHERE kept_person_id IN (SELECT person_id FROM persons WHERE primary_name LIKE 'T %')
   OR absorbed_person_id IN (SELECT person_id FROM persons WHERE primary_name LIKE 'T %');

-- 2) merge_candidates（填上真实列名后再执行；示例）
-- DELETE FROM merge_candidates
-- WHERE person_a IN (SELECT person_id FROM persons WHERE primary_name LIKE 'T %')
--    OR person_b IN (SELECT person_id FROM persons WHERE primary_name LIKE 'T %');

-- 3) persons 本体（T-fixture 在其他业务表已确认为 0 引用）
DELETE FROM persons WHERE primary_name LIKE 'T %';

COMMIT;
```

**前置**：跑之前强制新 snapshot。

### 预防

所有 `merge_candidates` / `merge_log` 相关测试必须用**临时 DuckDB 文件 + `monkeypatch`** 或 **`:memory:` 连接**，严禁打到 `config/paths.yaml` 指向的真 telemetry 库。补 linter-style check 或测试里断言 `conn.filename` 是临时路径。

### 验收

- 清理后 `SELECT COUNT(*) FROM persons` 从 396 → 222（396 − 174）。
- `merge-candidates sync-from-graph --dry-run` 结果中无 `T ` 开头的 candidate。
- `pytest` 全绿，且任何 merge_candidates 测试结束后真 telemetry.duckdb `LIKE 'T %'` 计数为 0。

---

## B-ING-1.6 · `merge-candidates enqueue-manual --pair`

### 为什么需要

`merge-candidates sync-from-graph` 只在两 person 共享至少一个 `value_normalized` 时 enqueue。本次真·重复里**有若干组 identifier 完全不重叠**（例如 `Cheng Wang`：一份私人邮箱、一份公司邮箱），靠 graph 永远找不到，但用户人工已确认同人。

目前 `merge-candidates` 子命令只有 `list / accept / reject / sync-from-graph`，**没法把人工决定的 pair 入队**。

### 接口提案

```
brain merge-candidates enqueue-manual \
    --pair <person_id_a> <person_id_b> \
    --reason "<自由文本>" \
    [--score 1.0] \
    [--auto-apply]
```

- 直接写一行到 `merge_candidates`，`score = 1.0`，`reason = "manual: ..."`，`status = pending`（或直接 `accepted` 若传 `--auto-apply`，走和 F3 一致的 accept 路径）。
- 对应 MCP 工具：`merge_candidates_enqueue_manual_tool`。
- 单测：双向对称（A,B == B,A）、同 id 拒绝、不存在 id 报错、落库后 `list` 能读到。

### 验收

- 9 组真·重复里 identifier 完全不重叠的那几组（`Cheng Wang` 等）可以通过此命令入队，再 `accept` 完成合并。
- F3 的 `auto-apply-min-score` 路径与本命令组合兼容。

---

## B-ING-1.7 · `ingest_events.backup` 字段回填

### 现象

本次 apply 的 `ingest-log-recent` 审计行 `backup: null`——`ingest-backup-now` 生成的 snapshot 路径/sha 没有被关联到该次 ingest 事件。

### 修复方向

`contacts_ingest_ios` 的事务入口处读取「最近一次成功 `ingest-backup-now` 的 label 前缀匹配」或**显式接收** `--snapshot-ref` 参数；事件写入时把 `{path, sha256, ts_utc}` 填进 `backup` 字段。次选：在 `ingest-backup-now` 里把结果写到一个小表 `ingest_snapshots`，ingest 事件持 id 引用。

---

## B-ING-1.8 · 手动处理 9 组真·重复

**前置**：B-ING-0.1（归一化）+ B-ING-1.6（手动入队）完成，再执行。执行顺序：

1. 重跑 `contacts-ingest-ios --dry-run --db "...\31\31bb..."`，确认归一化修复后 `person_rows` 降到 241 左右（减去 Hammond/Jerrel/Patricia 三对，应减 3；但再跑 ingest 需确认是幂等 upsert，否则见 B-ING-1.9）。
2. 对剩余组逐个决定：

    | 名字 | 人工决定 | 动作 |
    |------|----------|------|
    | Cheng Wang | 同人 | `enqueue-manual --pair p_0788eefdd6c4 p_7e885752da1c` → accept |
    | Alice Klamer | 待判（phone vs email 两份） | 待人工看 iOS 原卡 |
    | Magda | 可能不同人（NL vs US） | 先留，不动 |
    | Sara | 可能不同人（DE vs NL） | 先留，不动 |
    | unknown | 多半不同人 | 先留，不动 |
    | 英华 张 | 一份空壳 | 删除空壳（直接 SQL）或 enqueue-manual 合并 |

---

## B-ING-1.9 · `contacts-ingest-ios` 幂等性

B-ING-1.8 重跑之前要确认：同一 `AddressBook.sqlitedb` 第二次 apply 不会重复写入 person / identifier。证据：`value_normalized` 上应有 UNIQUE 或 upsert 语义；`persons_created` 第二次应 ≈ 0 或只等于归一化修复后新合并/新增的差值。

若不幂等 → 在 B-ING-1.8 之前补上 "已存在的 `value_normalized` 不再新建 person，而是挂到既有 person" 的逻辑。
