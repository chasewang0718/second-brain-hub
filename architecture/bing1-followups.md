---
title: B-ING-1 · 首次 apply 的 follow-ups
status: all_closed
created: 2026-04-22
closed: 2026-04-22
authoritative_at: C:\dev-projects\second-brain-hub\architecture\bing1-followups.md
related:
  - architecture/bing1-runbook.md
  - architecture/real-ingest-scope.md
---

# B-ING-1 · 首次 apply 的 follow-ups

B-ING-1 本身已 ✅（248/248，snapshot `20260422-011824-bing1-ios-addressbook.duckdb`，sha `53ad43bd…`）。  
本文档记录真跑之后冒出来、**不阻塞打勾**、但**必须在 B-ING-3 WhatsApp 上线前**处理的问题。

**2026-04-22 收官**：10 条 follow-up（0.1 / 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9 / 1.10 / 1.11 / **1.12**）**全部 ✅**。全量 `pytest tools/py/tests/` **234/234** 绿。B-ING-3 WhatsApp 可开工。

| 编号 | 标题 | 紧迫度 | 范围 | 状态 |
|------|------|--------|------|------|
| **B-ING-0.1** | Phone normalizer: NL 本地 `06…` → `+316…`（通过 `phonenumbers` + `default_region`） | **HIGH** | 代码 | **✅ 2026-04-22** |
| **B-ING-1.4** | `ios_backup_locator` 选优：不要选空子库 | MEDIUM | 代码 | **✅ 2026-04-22** |
| **B-ING-1.5** | 清理 DuckDB 里的 T-fixture 污染 + pytest 真隔离 | MEDIUM | 数据 + 测试隔离 | **✅ 2026-04-22** |
| **B-ING-1.6** | 加 `merge-candidates enqueue-manual` 子命令 | MEDIUM | 代码 | **✅ 2026-04-22** |
| **B-ING-1.7** | `ingest_events.backup` 字段回填最近一次 snapshot 路径/sha | LOW | 代码 | **✅ 2026-04-22** |
| **B-ING-1.8** | 手动处理 9 组真·重复 | MEDIUM | 数据 | **✅ 9/9 2026-04-22** |
| **B-ING-1.9** | `contacts-ingest-ios` 幂等性真跑 | MEDIUM | 测试 | **✅ 2026-04-22** |
| **B-ING-1.10** | `identifiers-repair --dry-run` 不应写 `merge_candidates`（且应按 (person_a, person_b) 去重） | LOW | 代码 | **✅ 2026-04-22** |
| **B-ING-1.11** | `merge_persons` 应自动把 absorbed.primary_name append 到 kept.aliases_json | MEDIUM | 代码 | **✅ 2026-04-22** |
| **B-ING-1.12** | `contacts-ingest-ios` 在 auto-T2 merge 后未跟踪 survivor pid → orphan `person_identifiers` | **HIGH** | 代码 + 数据 | **✅ 2026-04-22** |

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

## B-ING-1.5 · T-fixture 污染清理 + pytest 隔离 ✅ 2026-04-22

### 现象（修复前）

早期 merge-candidates / identity 测试（`ensure_person_with_seed("T Reject A", ...)` 等）直接跑在 `config/paths.yaml → telemetry_logs_dir → brain-telemetry.duckdb` 上，结果：

- **204** 个 `T *` / `Repair Test Person` / `Wx Repair` 残留 person 行（含 `T Bad A/B ×64`、`T Reject A/B ×64`、`T Acc A/B ×32`、`T Keep A/B ×32`、`T Alias/Carry ×2` 等）。
- **37** 个 orphan `merge_candidates`（`person_a` / `person_b` 指向已被 test teardown 删掉的 id）。
- **test_context_for_meeting_markdown_contains_shared_identifier_section** 因为 prod 里多了个 `Alice Klamer`，`who("Alice")` 不稳定，时绿时红。

### 修复

**1. 代码：`BRAIN_DB_PATH` 环境变量覆盖**

`tools/py/src/brain_memory/structured.py::_db_path()` 新增 env 优先级：`BRAIN_DB_PATH` 非空时走它，否则回落到 `paths.yaml`。所有 execute / query / fetch_one / ensure_schema 自动跟随。

**2. 测试：pytest session-scoped autouse fixture**

`tools/py/tests/conftest.py` 加 `_isolated_duckdb_path` fixture —— `tmp_path_factory` 开一份 `test.duckdb`，写进 `BRAIN_DB_PATH`，teardown 还原。从此 pytest 跑什么都打不到真库。

**3. 数据：一次性清扫脚本**

安全删除条件：`primary_name LIKE 'T %'` / 已知 fixture 名 **并且** `NOT EXISTS (person_identifiers)`，避免误删真联系人（`Tim / Tahir Vladi / Ties / Tim Van Zuijlen / Trinh / T..a Froger` 全都保留）。

### 执行

| 阶段 | snapshot | sha |
|---|---|---|
| pre-cleanup | `20260422-082747-bing15-pre-cleanup.duckdb` | `cdec46ba…` |
| post-cleanup | `20260422-083032-bing15-post-cleanup.duckdb` | `9b691472…` |

- `persons` **411 → 213**（-198；T Bad ×64、T Reject ×64、T Acc ×32、T Keep ×32、T Alias ×2、T Carry ×2、T Eq Name ×2）
- `person_identifiers` **459 → 459**（不变，证明删的都是裸 person 行，无真数据牵连）
- `merge_candidates` **37 → 0**（全部为 orphan）
- Kuzu graph 重建：**213 / 459 / 456** has_identifier。

剩余 213 里 211 有 identifier，2 无的是 demo seed `p_alice` (Alice Zhang) 和 `p_bob` (Bob van Dijk)，`seed_demo_people_data()` 的 idempotent 固定行，有意保留。

### 回归

- 全量 `pytest tests/` 在 `BRAIN_DB_PATH` 指向 tmp 路径下 **217/217** 通过，包含之前偶尔 fail 的 `test_context_for_meeting_markdown_contains_shared_identifier_section`。
- 真库计数 `prod scan`：`T *` 模式 0 行，`test_*` reason 的 merge_log 6 行（历史事实，保留）。

### 延伸（不阻塞本条收尾）

- `conftest.py` 目前是 **session** 作用域，测试间不做 TRUNCATE。若未来交叉测试需要完全隔离，再加 function-scope 的 reset fixture。
- `ensure_person_with_seed` 仍允许 caller 指向非-test 名字；防呆靠 fixture 本身。

---

## B-ING-1.6 · `merge-candidates enqueue-manual` ✅ 2026-04-22

### 现象（修复前）

`merge-candidates sync-from-graph` 只在两 person 共享至少一个 `value_normalized` 时 enqueue。B-ING-1.8 里的 `Cheng Wang`（私人 vs 公司邮箱）、`Alice Klamer`（phone-only vs email-only）这类真·重复 identifier 完全不重叠，graph 永远找不到。子命令只有 `list / accept / reject / sync-from-graph`，**没法把人工决定的 pair 入队**。

### 修复

`tools/py/src/brain_agents/merge_candidates.py` 新增 `enqueue_manual_candidate(person_a, person_b, *, reason, score=1.0, auto_apply=False)`：

1. 两个 id 同值 → `{"status":"error","reason":"same_person"}`。
2. 任一 id 在 `persons` 中不存在 → `{"status":"error","reason":"person_not_found","person_id":...}`。
3. pair 规整为 `(smaller_id, larger_id)`（对称）。
4. 已在 `merge_log` 或 `merge_candidates`（任意状态）命中 pair → `{"status":"noop","reason":"already_handled","existing_merge_candidate_id":...,"existing_status":...}`。
5. 写一行 `merge_candidates`，`reason = "manual:<user-text>"`（前缀区分 graph 来源），`detail_json.source = "manual_cli"`。
6. `score` clamp 到 `[0, 1]`。
7. `auto_apply=True` 时立刻 `accept_candidate(new_id)` → 直接合并 + 写 `merge_log`。

CLI（`tools/py/src/brain_cli/main.py`）：

```
brain merge-candidates enqueue-manual <person_id_a> <person_id_b> \
    --reason "<自由文本>" \
    [--score 1.0] [--auto-apply]
```

### 测试

`tests/test_merge_candidates.py` 新增 7 条：
- `test_enqueue_manual_happy_path_inserts_pending_row`：reason 带 `manual:` 前缀、status=pending。
- `test_enqueue_manual_canonicalizes_pair_order`：(B,A) 调用后返回的 `person_a/person_b` 已排序。
- `test_enqueue_manual_dedupes_against_existing_pair`：同 pair 再入队返回 `noop`，反向 pair 也去重。
- `test_enqueue_manual_rejects_same_person` / `test_enqueue_manual_rejects_unknown_person_id`。
- `test_enqueue_manual_auto_apply_merges_immediately`：`auto_apply=True` 后 absorbed 行消失、candidate 转 `accepted`。
- `test_enqueue_manual_clamps_score_into_unit_range`：`score=7.5` 落库为 `1.0`。

`pytest tests/test_merge_candidates.py` 18/18 通过（历史 11 + 新 7）。

### 用法

```
brain merge-candidates enqueue-manual p_cheng_personal p_cheng_work \
    --reason "same_person_email_split" --auto-apply
```

对应 B-ING-1.8 备注里的 `Cheng Wang` / `Alice Klamer` 那几组 identifier 完全不重叠的真·重复，现在不再需要手搓 SQL。

---

## B-ING-1.7 · `ingest_events.backup` 字段回填 ✅ 2026-04-22

### 现象（修复前）

B-ING-1 真·apply 后 `brain ingest-log-recent` 的审计行 `backup: null`。`brain ingest-backup-now` 生成的 snapshot 路径/sha 没有被关联到该次 ingest 事件，回滚时需要肉眼去 `_backup/telemetry/pointer-log.jsonl` 里按时间找最近一条，容易认错。

### 修复

两件事：

**1. `brain_agents/ingest_backup.py` 新增 `latest_snapshot(*, label_prefix, max_age_minutes=120, now=..., dest_root=...)`**

- 读 `pointer-log.jsonl`，按 `ts_utc` 倒序扫描。
- `label_prefix` 做**大小写不敏感 startswith 匹配**（`ios-addressbook` 匹配 `ios-addressbook-pre-apply` / `ios-addressbook-redo`）；`None` = 任意 label。
- `max_age_minutes` 默认 **120**（操作流程是先 snapshot 立即 apply，>2h 老快照大概率是别的事件的）；`None` 或 `<=0` = 不限。
- 无法解析 `ts_utc` 的条目直接跳过，避免错关联。
- 找不到时返回 `None`。

同时新增 `_short_descriptor(desc)` — 把完整 descriptor 收窄成 `{snapshot, sha256, ts_utc, label, bytes}`，写进 `ingest_events.backup` 时字段更克制（不重复 `elapsed_ms` / `source` 这类不必要的）。

**2. `brain_cli.main` 的 `contacts-ingest-ios` / `whatsapp-ingest-ios` CLI 入口**

新增两个 flag：
- `--snapshot-ref <path>` — 显式指定要归属的 `.duckdb` snapshot 路径（pointer-log 里有匹配才算数，没有就按 None 走）。
- `--snapshot-max-age-minutes 120` — auto-pick 窗口；`0` = 不限。

挑选顺序：
1. `--snapshot-ref` 显式命中 → 用；
2. 否则 `latest_snapshot(label_prefix="ios-addressbook" / "whatsapp", max_age_minutes=...)`；
3. 再兜底 `latest_snapshot(label_prefix=None, max_age_minutes=...)`（防止操作员打错 label）；
4. `--dry-run` 时**跳过 auto-pick**（dry-run 不应该认领真 snapshot）。

选中的 descriptor 经 `_short_descriptor` 压扁后以 `backup_descriptor=` 传给 `ingest_address_book_sqlite` / `ingest_chatstorage_sqlite`，agent 内部原有的 `log_ingest_event(..., backup=backup_descriptor)` 自动把它写进 JSONL 的 `backup` 字段。

### 测试

`tests/test_ingest_backup.py` 新增 6 条：
- `test_latest_snapshot_prefers_label_prefix`：4 条 snapshot 里 2 条 `ios-addressbook*`，挑出最新那条。
- `test_latest_snapshot_respects_age_cap`：180 min 老的 snapshot + 120 min cap → `None`；放到 240 min cap → 找回。
- `test_latest_snapshot_prefix_miss_returns_none`：`wechat` 前缀无匹配时返回 `None`（不静默退回全库最新，避免错关联）。
- `test_latest_snapshot_falls_back_to_newest_when_no_prefix`：`label_prefix=None` 时返回全库最新。
- `test_latest_snapshot_empty_returns_none`：无 pointer-log 文件时安全返回。
- `test_short_descriptor_keeps_audit_fields`：只留 `{snapshot, sha256, ts_utc, label, bytes}`。

回归：
- `pytest tests/test_ingest_backup.py` 10/10（含原 4 条）。
- `pytest tests/test_ingest_log.py` 5/5：`test_log_apply_writes_jsonl` 本就验证 `ev["backup"]["sha256"] == "abc"` 能端到端穿过 JSONL。
- 全量 `pytest tests/` **232/232** 绿。

### 用法

```
brain ingest-backup-now --label ios-addressbook-pre-apply
brain contacts-ingest-ios                     # 自动把上面那条 snapshot 写进 backup 字段
brain contacts-ingest-ios --snapshot-ref "D:/.../_backup/telemetry/20260422-093000-ios-addressbook-pre-apply.duckdb"   # 显式覆盖
brain ingest-log-recent --days 1              # 审计行 backup.{snapshot,sha256,ts_utc,label,bytes} 都有值
```

后续如果 pointer-log 增速变快（比如一天几十次），可以加 `ingest_snapshots` DuckDB 表按 id 索引；目前线性扫 200 行足够。

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

## B-ING-1.9 · `contacts-ingest-ios` 幂等性 ✅ 2026-04-22

### 要回答的问题

同一 `AddressBook.sqlitedb` 第二次 apply，会不会把每个联系人再复制一份？

### 验证方法

`tests/test_contacts_ingest_ios_idempotent.py` 用 tmp_path 造一份最小 iOS AddressBook schema（`ABPerson` + `ABMultiValue`，3 条联系人 + 2 phone + 2 email），跑两遍 `ingest_address_book_sqlite`：

| pass | status | person_rows | persons_created | persons total | identifiers total |
|---|---|---:|---:|---:|---:|
| 1 | ok | 3 | **3** | +3 | +3 ios_contact_row + phones/emails |
| 2 | ok | 3 | **0** | 不变 | 不变 |

### 结论 ✅

**幂等**。稳定键 `ios_contact_row:ios_ab:<rid>` + `resolve_identifier` short-circuit + `person_identifiers.ON CONFLICT (person_id, kind, value_normalized) DO NOTHING` 三层一起保证：

- 第二次跑不新建 person。
- 第二次跑不新建 identifier 行。
- `dry_run` 测试顺手确认 dry-run 不写库。

2/2 绿（`pytest tests/test_contacts_ingest_ios_idempotent.py`），在 B-ING-1.5 装的 `BRAIN_DB_PATH` 隔离 fixture 下跑，对生产库无任何影响。

### 已知小气味（不阻塞）

`stats["identifiers_added"]` 按 `register_identifier` 返回 `status="ok"` 计数，而 `ok` 在 `ON CONFLICT DO NOTHING` 时也返回 —— 所以第一次真跑时该计数会**虚高**（包括 no-op 的 upsert）。不影响幂等结论，但 B-ING-3 WhatsApp 上线前可以顺手修成按实际影响行数计。

若不幂等 → 在 B-ING-1.8 之前补上 "已存在的 `value_normalized` 不再新建 person，而是挂到既有 person" 的逻辑。

---

## B-ING-1.12 · `contacts-ingest-ios` 未跟踪 auto-T2 survivor pid → orphan identifiers ✅ 2026-04-22

### 现象（修复前）

B-ING-1 全部 follow-up 收官后做宏观验收时发现：`persons`=213，但"至少有 1 个 identifier 的 person_id 个数"=214。差出来的 1 是一组 orphan —— 展开发现 **3 条 `person_identifiers` 的 `person_id` 在 `persons` 表里不存在**：

| `id` | 被孤立的 `person_id` | `kind` | `value_normalized` |
|-----:|----------------------|--------|--------------------|
| 522 | `p_ac8da4f9ac38` | email | `amirnesta@gmail.com` |
| 534 | `p_5e98869f465c` | email | `h.oosterhuis119@outlook.com` |
| 542 | `p_fa3b50ec34a2` | email | `astone.shi@gmail.com` |

三条全部是 B-ING-1 首次 apply 时写入的真邮箱，都带 `source_kind='ios_addressbook'`。

影响：`brain who <email>` 对这三个地址返回空 —— **19 封 ingest 邮箱里 16% 不可解析**。

### 根因

`identity_resolver.register_identifier`（strong kind 分支）在发现该 identifier 已被别的 person 持有时，触发 `merge_persons(kept, absorbed, "auto_t2_strong_identifier")`，然后**把函数内局部 `person_id` 变量改写为 `kept`**，并返回 `{"status": "ok", "person_id": kept, ...}`。

问题不在 `register_identifier` —— 它已经把 survivor pid 返回了。问题在 **caller（`contacts_ingest_ios._apply`）没有接这个返回值**：

```python
# BEFORE（bug）
for ph in phones:
    r = register_identifier(pid, "phone", ph, ...)   # ← phone 撞到别人，触发 auto-T2 merge
    # pid 此时可能已经被 absorbed，但本地变量没更新
for em in emails:
    r = register_identifier(pid, "email", em, ...)   # ← 用已经消失的 pid 插入 → orphan!
```

`person_identifiers` 表**没有外键约束**（只有 `UNIQUE(person_id, kind, value_normalized)`），所以"往不存在的 person 插入 identifier"不会报错 —— 静默写入，留下孤儿行。

生产 3 条 orphan 的触发路径都是同一模式：iOS 卡里先挂 phone（这个 phone 别人已经在用，触发 auto-T2 merge，local pid 被 absorbed），后挂 email（用已失效的 pid 插入）。

### 修复

**caller 跟踪 survivor pid**（`tools/py/src/brain_agents/contacts_ingest_ios.py`）：

```python
# AFTER
for ph in phones:
    r = register_identifier(pid, "phone", ph, ...)
    if r.get("status") == "ok":
        stats["identifiers_added"] += 1
    pid = r.get("person_id") or pid   # ← 跟住 merge survivor
for em in emails:
    r = register_identifier(pid, "email", em, ...)
    if r.get("status") == "ok":
        stats["identifiers_added"] += 1
    pid = r.get("person_id") or pid
```

同时在 `identity_resolver`：

1. **`register_identifier` 补 docstring**：显式写清 caller 的义务 —— strong-kind auto-T2 merge 后必须 follow 返回的 `person_id`，忽略返回值会泄漏 orphan。
2. **`ensure_person_with_seed` 同步加固**：当 `seed_identifiers` 里某一条触发 auto-T2 时，返回的 pid 必须是 survivor，而不是刚刚新建的那个（现在 iOS 只传 1 个 weak-kind seed 不会触发，但接口契约上这是潜在坑）。

3. **WhatsApp ingest** (`whatsapp_ingest_ios.py`) 当前只对每条消息的 peer 做 1 次 `resolve_identifier` + 缺则 `ensure_person_with_seed(…, seed=[("wa_jid", peer)])`，没有"先挂 A 再挂 B"的多-identifier 循环 —— 随着 `ensure_person_with_seed` 的加固，**自动免疫**同类 bug。不需要改 WhatsApp 代码。

### 测试

新增 `tests/test_contacts_ingest_ios_orphan_regression.py`：

| 用例 | 场景 | 断言 |
|------|------|------|
| `test_phone_collision_does_not_leak_orphan_email` | 两张 iOS 卡共享同一 phone、各带一个不同 email（复刻生产 bug 路径） | `person_identifiers` 没有任何 orphan；两个 email 都指向同一个 survivor；survivor 存在于 `persons` |
| `test_phone_collision_survives_reingest` | 同一份书第二次 apply | `persons_created=0`，orphan 保持 0 |

全量 `pytest tools/py/` **234/234 绿**（含新 2 条）。

### 生产数据清理

1. 执行前 snapshot：`20260422-090206-bing1.12-orphan-cleanup.duckdb`（sha `9b691472…`，49.3 MB）。
2. 对每条 orphan，从 `merge_log.absorbed_person_id` 回查 `kept_person_id`（顺着 merge 链最多走 10 跳）；若 survivor 还在且没有同一 identifier，reparent；否则删。
3. 3 条全部 reparent 成功：
   - `amirnesta@gmail.com`      → `p_256e3b0e6f2a`
   - `h.oosterhuis119@outlook.com` → `p_3cf988cbd985`
   - `astone.shi@gmail.com`     → `p_ce0c73b93893`
4. 复查：orphan `person_identifiers` = **0**。

### 影响

- B-ING-3 WhatsApp ingest 以及所有未来要在"单条 ingest 内挂多个 strong-kind identifier"的路径**不会再掉进这个坑**（代码层）。
- 3 个真邮箱现在能通过 `brain who` / `resolve_identifier` 解析了。
- 该 bug 的存在时间只有 B-ING-1 那一次真 apply，数据量可控（3 / 19 = 16%），已全部修复。
