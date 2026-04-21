---
title: B-ING-1 · iOS AddressBook 真数据上线 Runbook
status: ready
created: 2026-04-21
authoritative_at: C:\dev-projects\second-brain-hub\architecture\bing1-runbook.md
---

# B-ING-1 · iOS 通讯录真数据 ingest Runbook

## 适用范围

这是 `real-ingest-scope.md` 里 **B-ING-1** 的执行清单——从手上这台
iPhone 的一次 iTunes/Finder 备份，把通讯录（AddressBook.sqlitedb）
导进 DuckDB 的 `persons` + `person_identifiers` 两张表。

**代码全部就绪**（B-ING-0 已合并 20924ab，四个前置门槛全绿）。
这份文档的作用是：**你只要照步骤做，不用想。**

## 前置要求（跑之前确认）

- [ ] Windows PC 是当前这台，hub 在 `C:\dev-projects\second-brain-hub`
- [ ] Python 环境有 `duckdb`（`python -c "import duckdb"` 不报错就行）
- [ ] DuckDB 文件存在：`D:\second-brain-assets\_runtime\logs\brain-telemetry.duckdb`
- [ ] **iPhone 连接了 PC**，但先**不要开始备份**（看第 1 步）

## 五步上线

### 步骤 1 · 做一次**非加密**的 iTunes/Finder 备份（你来做）

**必须**：Windows 的 "Apple 设备" 应用（或 iTunes）。打开后：

1. 点这台 iPhone
2. "备份"面板里找到 **"加密本地备份"**——**必须取消勾选**
3. 弹出"确认不加密"对话框 → 选"不加密"
4. 点"立即备份"，等进度条走完

> ⚠️ 加密备份里 AddressBook.sqlitedb 是锁死的，
> Python 读不出来。hub 不会尝试解密（`real-ingest-scope.md` 绝对
> 不做清单里明文约束）。如果你想继续加密，**停在这里**，告诉我，
> 我们另走一条路（通过 iCloud 通讯录导出 vCard）。

备份完成后，备份通常落在：
```
%AppData%\Apple Computer\MobileSync\Backup\<UDID>\
```
其中 `<UDID>` 是一个 40 字符十六进制字符串。

### 步骤 2 · 定位备份（我帮你跑）

```powershell
cd C:\dev-projects\second-brain-hub\tools\py
$env:PYTHONPATH = 'src'
python -m brain_cli.main backup-ios-locate
```

**期望输出**（JSON）：
- `selected` 字段**非空**（指向最新备份的 UDID 目录）
- `addressbook` 字段指向某个 `Manifest.db` 能解析出来的路径

**如果 `selected` 为 null**：备份没完成 / 没找到 / 这台 PC 没备份
过这部 iPhone。回步骤 1。

### 步骤 3 · 先快照 DuckDB（强制前置）

**绝对不能跳过**。这是回滚保险。

```powershell
python -m brain_cli.main ingest-backup-now --label bing1-ios-addressbook
```

**期望输出**：
- `status: ok`
- `snapshot` 字段指向新落地的 `.duckdb` 文件
- `sha256` 有值

这一份 `.duckdb` 是"动手前的状态"。后续任何时候想回滚：
1. 关掉所有用 DuckDB 的进程（brain CLI / MCP 服务等）
2. 把 snapshot 文件 `copy` 覆盖回
   `D:\second-brain-assets\_runtime\logs\brain-telemetry.duckdb`
3. 结束

### 步骤 4 · Dry-run 看前 20 条

```powershell
python -m brain_cli.main contacts-ingest-ios --dry-run | more
```

JSON 里会有 `sample`（前 20 条）。**人工眼看确认**：
- [ ] 名字中文/英文都能正常显示（不是 `???`）
- [ ] `phones` 里是期望的国家代码格式（会在 apply 时规范成 `86` 前缀）
- [ ] `emails` 是期望的地址
- [ ] `person_rows` 总数量级合理（正常家用 100-2000 之间）

如果任何一项不对劲，**停住**，告诉我原始 JSON。

### 步骤 5 · 真 apply（这一步才真的写库）

```powershell
python -m brain_cli.main contacts-ingest-ios
```

**成功标志**：
- `status: "ok"`
- `persons_created` > 0（首次 ingest 应 ≈ `person_rows`）
- `identifiers_added` ≥ `persons_created`（每人至少 1 个电话或邮箱）
- 无 `error` 字段

**同时**会落两条审计：

```powershell
python -m brain_cli.main ingest-log-recent --source ios_addressbook --limit 3
```

应看到刚才 apply 的一行，字段完整。

### 步骤 6（可选）· 看看 T3 队列

```powershell
python -m brain_cli.main merge-candidates sync-from-graph --dry-run
# 或
python -m brain_cli.main merge-candidates list --status pending --limit 20
```

如果新 ingest 触发了跨人 shared-identifier 合并候选，这里会看到。
**本次 B-ING-1 不处理 T3**——那是 B-ING-2 的事（真实分布出来后
才好调阈值）。扫一眼有个数即可。

## 出错了怎么办

| 症状 | 动作 |
|---|---|
| 备份文件路径找不到 | 检查步骤 1 是否真正完成，`selected` 是否 null |
| dry-run 中文乱码 | 备份加密了；回步骤 1 关掉加密 |
| apply 中途 Python 抛异常 | 事务已 ROLLBACK，DuckDB 原样；`ingest-log-recent` 会显示 `status: error` 那一行；把完整 JSON 发我 |
| 想完全重来 | 用步骤 3 落的 snapshot 覆盖回去，重新跑 |

## 退出标志

- [ ] Apply 成功，`persons_created` ≈ 备份里的联系人数 ±5%
- [ ] `ingest-log-recent` 能看到那一行审计
- [ ] 跑一次 `brain graph-rebuild-if-stale --force`，`persons` 计数
      和 DuckDB 一致
- [ ] 手工挑 3 个熟人用 `brain who "名字"` 验一下能查到
- [ ] （可选）`brain context-for-meeting "某熟人"` 看看 graph_hints
      是否给出了新发现的关联

满足前四条就可以在本 runbook 末尾打勾。

## 打勾

- [ ] 2026-__-__ 第一次成功 apply，本人在场

## 变更记录

| 日期 | 说明 |
|---|---|
| 2026-04-21 | 首版；6 步，配合 B-ING-0 (`20924ab`) + `27c0827` 使用。 |
