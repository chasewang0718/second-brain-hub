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

| 编号 | 标题 | 紧迫度 | 范围 | 状态 |
|------|------|--------|------|------|
| **B-ING-0.1** | Phone normalizer: NL 本地 `06…` → `+316…`（通过 `phonenumbers` + `default_region`） | **HIGH** | 代码 | **✅ 2026-04-22** |
| **B-ING-1.4** | `ios_backup_locator` 选优：不要选空子库 | MEDIUM | 代码 | **✅ 2026-04-22** |
| **B-ING-1.5** | 清理 DuckDB 里的 T-fixture 污染（174 persons + 8 merge_log） | MEDIUM | 数据 + 测试隔离 | open |
| **B-ING-1.6** | 加 `merge-candidates enqueue-manual --pair` 子命令 | MEDIUM | 代码 | open |
| **B-ING-1.7** | `ingest_events.backup` 字段回填最近一次 snapshot 路径/sha | LOW | 代码 | open |
| **B-ING-1.8** | 手动处理 9 组真·重复 | MEDIUM | 数据 | **✅ 9/9 2026-04-22** |
| **B-ING-1.10** | `identifiers-repair --dry-run` 不应写 `merge_candidates`（且应按 (person_a, person_b) 去重） | LOW | 代码 | **✅ 2026-04-22** |
| **B-ING-1.11** | `merge_persons` 应自动把 absorbed.primary_name append 到 kept.aliases_json | MEDIUM | 代码 | **✅ 2026-04-22** |

---

## B-ING-0.1 · Phone normalizer 补 NL 本地号（并泛化） ✅ 2026-04-22

### 现象（修复前）

本次 apply 在 `person_identifiers` 里写入了下列三对、**逻辑上同号、`value_normalized` 不同**的记录：

| 名字 | `value_normalized` / `value_original` |
|------|---------------------------------------|
| Hammond | `31615156595` / `+31615156595` vs `0615156595` / `0615156595` |
| Jerrel | `31615556491` / `+31615556491` vs `0615556491` / `(06) 15 55 64 91` |
| Patricia | `31683165725` / `+31683165725` vs `0683165725` / `(06) 83 16 57 25` |

正常化逻辑把带 `+` 的号剥成 `31…`，但对 iOS 里存的 **纯本地号 `06…`**（没有国家前缀）不处理，于是同一个号在两份 iOS 卡上被写成两个不同的 `value_normalized`，T3 `sync-from-graph` 自然认不出重合。

### 根因

`identity_resolver.normalize_phone_digits` 只有 CN mobile + `0086…` 特判 + digits-only 兜底，没有「默认国家上下文」，把未带 `+` 的号当字符串原样保留。

### 修复（已落地）

1. `tools/py/pyproject.toml` 加依赖 `phonenumbers>=9.0.28`（Google libphonenumber 的 Python port）。
2. `config/thresholds.yaml` 新增段落：

   ```yaml
   identity:
     phone_default_region: "NL"
   ```

3. `identity_resolver.normalize_phone_digits(raw, *, default_region=None)`：
   - **Step 1（不变）**：裸 11 位 CN 手机号 + `0086…` 前缀短路，保持既有语义（`86…`），所有老测试保持绿。
   - **Step 2（新）**：`phonenumbers.parse(raw, default_region)`，成功 → 返回 E.164 去掉 `+` 的纯数字（`31615156595`）。
   - **Step 3（兜底）**：libphonenumber 抛 `NumberParseException` 或号码实在无效 → 回到 digits-only。
   - `default_region=None` 时自动读 `thresholds.yaml → identity.phone_default_region`（`lru_cache`，每进程一次）。
4. `normalize_value(kind, value, *, default_region=None)` 透传 region 到 phone 分支；`email` / `gmail_addr` / `wxid` 行为不变。
5. `tests/test_identity_phone_normalize.py` 从 5 个测试扩到 **13 个**：保留全部 CN 用例，新增 NL 本地 / 带空格括号 / 带 `+` 形式、UK `07…`、Ghana `+233…`、DE `+49…`、Colombia `+57…`、`normalize_value` 透传 region、email 忽略 region、NL 本地+国际形式**幂等**。

### 验收痕迹（真跑）

Snapshot：`D:\second-brain-assets\_backup\telemetry\20260422-015459-bing01-phone-normalize.duckdb`  sha `a1108eb29333634dc8615cf9d77aa729fc4f38097879540fbcf2d531dcf464a7`（41955328 bytes）。

```
brain identifiers-repair --kinds phone --dry-run / --apply
  rows_scanned       201
  skipped_unchanged  178   # 已是对的
  updated             14   # 同人内 06… → 31… 静默纠正
  deleted_duplicate    0
  merge_candidates     9   # 跨 person 冲突 → 进 T3 队列等人工 accept
```

- `brain merge-candidates list --status pending` 里 **9 对** `phone_repair_collision` 全部是真重复：Hammond、Jerrel、Patricia、Harry / Harry Schortinghuis、Lunsing Kazemier / Cazemier、Hady / Hadi、乐燕 / Leyan、悦取 / 老婆、英华 / 小华。
- 全量 pytest 200/201 pass，唯一失败的 `test_context_for_meeting_markdown_contains_shared_identifier_section` 属 B-ING-1.5（DB 污染）、与本次修改无关（`git stash` 基线复现同样失败）。
- 顺手发现：`identifiers-repair` 的 `--dry-run` 仍然会往 `merge_candidates` 写 + 不按 (person_a, person_b) pair 去重；重跑两轮后队列里 9 对膨胀到 36 行，已手工 SQL 去重回 9 行。→ 单立 **B-ING-1.10**。

### 后续

- **B-ING-1.8** 现在有 9 条明确的 pending 可直接过 `brain merge-candidates accept <id>`：7 条（同名或拼写变体）可直接批；2 条（`悦取/老婆`、`英华/小华`）需要人眼再确认。
- 建议 accept 后再跑一次 `identifiers-repair --kinds phone`：被 absorbed 行的 `0615156595` 会此时撞 kept 的 `31615156595` 命中 `deleted_duplicate` 路径，彻底清理。

---

## B-ING-1.4 · `ios_backup_locator` 不要选空子库 ✅ 2026-04-22

### 现象（修复前）

`backup-ios-locate` 把命中列表里**第一条** `Library/AddressBook/Family/<uuid>:22AddressBook.sqlitedb`（Source ID 22 的来源子库）选为 `selected`，但那份子库 `person_rows: 0`。真正含 248 行的主库 `Library/AddressBook/AddressBook.sqlitedb` 排在列表靠后。B-ING-1 第一次 apply 因此差点把空库当成全量，靠 Kuzu 统计才看出不对。

### 修复

`tools/py/src/brain_agents/ios_backup_locator.py` 重构：

1. 拆出共享辅助 `_find_backup_file(...)`，`find_addressbook_sqlitedb` / `find_chatstorage_sqlite` 都走它，签名保持向后兼容（`status` / `backup_dir` / `hits` / `selected` 不变）。
2. 新增 `_select_best_hit(hits, *, exact_basename)` 做排名：
   - 只考虑物理文件存在的 hit。
   - **硬优先**：basename 严格等于期望名的优先（`AddressBook.sqlitedb` vs `AddressBook.sqlitedb-wal` / `-shm` / `Family/…` 子库）。
   - **次优先**：在 exact-basename 桶里按文件 size 降序取最大非零。
   - **兜底**：全 0 字节时按 `file_id` 字典序取第一个，并把 `selected_reason` 带上 `all_empty_fallback`，让 caller 看得出是兜底。
3. 返回字段新增：
   - `selected_reason` —— 人类可读的决策原因（`exact_basename+largest_size_204800`、`exact_basename+all_empty_fallback`、`no_resolved_candidate` 等）。
   - `selected_size` —— 选中文件的 size，便于 runbook 直接眼看「这 20 KB 肯定空」。
   - `candidates` —— 排名过的完整候选列表，每条含 `basename` / `size` / `exact_basename_match`。

### 测试

`tests/test_ios_backup_locator.py`：8 条全绿，覆盖：

- `test_prefers_exact_basename_over_wal_sibling`：WAL 再大也不选。
- `test_picks_nonempty_when_two_exact_basename_candidates`：同名 0-byte + 150 KB，选 150 KB 那份。
- `test_reports_reason_when_only_empty_db_available`：`selected_reason` 带 `all_empty_fallback`。
- `test_candidates_list_exposed_with_size_and_flag`：新字段结构正确。
- `test_chatstorage_also_uses_ranking`：WhatsApp `.sqlite-shm` sibling 也被正确降权。
- 其余 3 条：空输入 / 无匹配行 / `domain_like` 过滤的 regression guard。

下游回归：`tests/test_mcp_server.py` + `tests/test_mcp_readonly_tools.py` 5/5 仍绿（他们通过 `locate_bundle` 调 locator，只看 `status` / `selected` 字段）。

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

## B-ING-1.8 · 手动处理重复 persons — ✅ 9/9 2026-04-22

B-ING-0.1 落地后，`identifiers-repair --kinds phone` 在 T3 队列里凭 phone 归一化发现 **9 对** `phone_repair_collision`，9 对全部经人工 review 合并完成。

### 合并全表

| mc.id | kept → absorbed | 备注 |
|-------|----------------|------|
| 217 | `p_8b8db0a78fec` Harry Schortinghuis ← `p_31eb934ae096` Harry | `--keep` 保留更完整的姓名 |
| 218 | `p_1872d6e1a674` Patricia ← `p_7bb0b255b73d` Patricia | 默认（同名） |
| 219 | `p_491c30816955` Lunsing Kazemier ← `p_adbc5eb59074` Lunsing Cazemier | 拼写差异，保留 "Kazemier" |
| 220 | `p_b07f2fdc42ab` Jerrel ← `p_b620dcef885d` Jerrel | 默认 |
| 221 | `p_16d38b5b1f89` Hady ← `p_b8a1db3ab6af` Hadi | 拼写差异 |
| 222 | `p_0e2bf6170bfe` 乐燕 ← `p_4f001edc22bd` Leyan | 中文 / 拼音 |
| 223 | `p_0ac7536db641` Hammond ← `p_1eba139a22ef` Hammond | 默认 |
| 224 | `p_5a6cbab7be21` 英华 ← `p_ec9cb3a33938` 小华 | 昵称，用户确认同人 |
| 225 | `p_2b1cb206bb2b` 悦取 ← `p_b1719d0e1a64` 老婆 | 关系标签卡，用户确认同人 |

### Snapshot 时序

- `20260422-015459-bing01-phone-normalize.duckdb` sha `a1108eb2…` — repair pass-1 前（B-ING-0.1 落地）
- `20260422-074832-bing01-pre-7-accepts.duckdb` sha `af3be7d2…` — 前 7 条 accept 前
- `20260422-080156-bing18-last-2-accepts.duckdb` sha `75b70cb1…` — 最后 2 条 accept 前

### Repair 扫描结果（每轮自动 dedup absorbed 行里的遗留 NL 本地形式）

| pass | rows_scanned | updated | deleted_duplicate | merge_candidates |
|---|---:|---:|---:|---:|
| 1 (B-ING-0.1) | 201 | 14 | 0 | 9 |
| 2 (7 accepts 后) | 201 | 0 | 7 | 2 再次入队（B-ING-1.10） |
| 3 (9 accepts 后) | 194 | 0 | 2 | **0** |

### Alias 回填（B-ING-1.11 band-aid）

因 `merge_persons` 不自动把 absorbed.primary_name 挂到 kept.aliases_json，以下 **6 个名字** 在合并后无法用 `who` 搜索到，已用 SQL 手工回填：

| kept person | +alias |
|---|---|
| `p_8b8db0a78fec` Harry Schortinghuis | `Harry` |
| `p_491c30816955` Lunsing Kazemier | `Lunsing Cazemier` |
| `p_16d38b5b1f89` Hady | `Hadi` |
| `p_0e2bf6170bfe` 乐燕 | `Leyan` |
| `p_5a6cbab7be21` 英华 | `小华` |
| `p_2b1cb206bb2b` 悦取 | `老婆` |

### 最终数

`persons` 402 → **393**（-9），`person_identifiers` 468 → **459**（-9）。Kuzu graph 重建：393 / 459 / 456 has_identifier。

### Pre-0.1 设想的其他重复组（历史 scope，非本轮 repair 发现）

| 名字 | 人工决定 | 动作 |
|------|----------|------|
| Cheng Wang | 同人（personal / business email） | 等 **B-ING-1.6**（`enqueue-manual --pair`）落地再处理 |
| Alice Klamer | 待判（phone vs email 两份，identifier 没重合） | 同上 |
| Magda / Sara / unknown | 多半不同人 | 先留不动 |
| 英华 张 | 一份空壳（`p_7ab52b139d73`，与本轮合并的 `p_5a6cbab7be21` 英华 无 shared identifier） | 删空壳（SQL）或 `enqueue-manual` 合并 |

---

## B-ING-1.10 · `identifiers-repair` dry-run 纯净 + pair 去重 ✅ 2026-04-22

### 现象（修复前）

1. `brain identifiers-repair --dry-run` 照样往 `merge_candidates` 表里 INSERT 行 —— dry-run 应该只读。
2. B-ING-1.8 实跑时，9 对真·重复被拆成 36 行 `phone_repair_collision` / `phone_repair_ambiguous`（多条 legacy `06…` 号都朝同一个 survivor 撞），人工还得用 SQL 按 `(person_a, person_b)` 挑最小 id 去重到 9 行再 accept。

### 修复

`tools/py/src/brain_agents/identity_resolver.py::_enqueue_merge_candidate` 改签名：

- 统一把 pair 规整为 `(smaller_id, larger_id)`；
- `SELECT` 检查该 pair 是否已有任意状态的行，有则直接 return `False`；
- 新增 `dry_run` kwarg，dry-run 时只返回判断不 INSERT；
- 返回 `bool`（`True` = 真写了 / dry-run 下"会写"；`False` = 已存在被跳过）。

`_repair_identifier_kind_group` 循环里再加一层 run 内部 `seen_pairs` 兜底（因为 dry-run 不 commit，DB 检查看不到同 run 前几次已"会写"的 pair），然后：

- `stats["merge_candidates"]` 改为 **真正会新增的 pair 数**（不再是 per-row collision 数）；
- 新增 `merge_candidate_collisions`（per-row 命中次数，用于诊断）；
- 新增 `merge_candidate_skipped_existing`（被去重跳过的次数）。

### 测试

`tests/test_identity_repair.py`：

- `test_repair_dry_run_does_not_write_merge_candidates`：dry-run 前后 `merge_candidates` 表行数相等；
- `test_repair_pair_dedupe_multiple_rows_same_pair`：A 一行 + B 三行 uppercase twin 撞 A → 只生成 **1** 个 candidate，`collisions>=3`，`skipped_existing>=2`；
- `test_repair_pair_dedupe_second_run_is_noop`：第一次真跑后第二次是 no-op，`merge_candidates=0`。

16/16（含 `test_merge_candidates.py` 的 11 条）通过。

### 实况冒烟（真库）

B-ING-1.8 后所有 identifier 已 canonical，全量 dry-run `rows_scanned=211 / skipped_unchanged=211`，`merge_candidates` 表 `pre=37 post=37`，零副作用。下次真跑新 ingest 时才是 1.10 真正发挥价值的时候。

---

## B-ING-1.11 · `merge_persons` 自动回填 alias ✅ 2026-04-22

### 现象（修复前）

B-ING-1.8 里，每次合并都要人肉把 absorbed.primary_name 手写进 kept.aliases_json，否则 `brain who "<absorbed_name>"` 会返回空。band-aid 段（上面那张 6 行表）就是证据。

### 修复

`identity_resolver.merge_persons` 在 `DELETE FROM persons` 之前，先：

1. 取 absorbed 和 kept 的 `primary_name` / `aliases_json`；
2. 走 `_merge_aliases_payload(...)`：把 kept.aliases + absorbed.primary_name + absorbed.aliases 合并，去掉和 kept.primary_name 大小写相等的冗余项，再按首次出现顺序去重；
3. `UPDATE persons SET aliases_json = ? WHERE person_id = kept`。

顺序：absorbed.primary_name 插在 absorbed.aliases 之前，因为它才是用户最可能用 `who` 搜的字面量。

### 测试

`tests/test_merge_candidates.py`：

- `test_merge_aliases_payload_dedupes_and_drops_primary_echo`
- `test_merge_aliases_payload_skips_alias_equal_to_kept_primary`（Hammond ← Hammond 不会污染 aliases）
- `test_merge_aliases_payload_preserves_kept_then_absorbed_order`
- `test_merge_persons_auto_aliases_absorbed_primary`（端到端：走完 merge 后 `aliases_json` 真的有值）
- `test_merge_persons_carries_absorbed_aliases_forward`（absorbed 自己的历史 alias 不丢）
- `test_merge_persons_skips_alias_when_names_equal`

11/11 通过（含老 5 条 + 新 6 条）。

### 影响

下一次再合并同名 / 昵称 / 翻译名时，不需要再手写 SQL 回填。上面 B-ING-1.8 里的 6 行 band-aid 表格**不再产生新条目**（已写入的 6 条 alias 保持不变，作为历史事实）。

---

## B-ING-1.9 · `contacts-ingest-ios` 幂等性

B-ING-1.8 重跑之前要确认：同一 `AddressBook.sqlitedb` 第二次 apply 不会重复写入 person / identifier。证据：`value_normalized` 上应有 UNIQUE 或 upsert 语义；`persons_created` 第二次应 ≈ 0 或只等于归一化修复后新合并/新增的差值。

若不幂等 → 在 B-ING-1.8 之前补上 "已存在的 `value_normalized` 不再新建 person，而是挂到既有 person" 的逻辑。
