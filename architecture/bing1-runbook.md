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

**代码全部就绪**（B-ING-0 已合并：事务包裹 + JSONL 审计 + `ingest-backup-now`）。
这份文档的作用是：**你只要照步骤做，不用想。**

---

## 保姆级一步步操作指南

> 零基础零思考版。**全程在同一个 PowerShell 窗口**完成；每步按「操作 → 期望 → 卡住时」三栏读。
> 后面的「超详细操作稿（阶段 0–7）」「五步上线（精简版）」是技术冗余版，日常只照本节做即可。

### 0 · 打开本文件 + 打开 PowerShell

- **打开文档**：Cursor / VS Code 里按 `Ctrl+P` → 输 `bing1` → 选 `architecture/bing1-runbook.md`。  
  聊天里的 `C:\...` 长路径链接 **不要点**（URL 编码把 `\` 变成 `%5C` 会打不开；文件没丢）。
- **打开终端**：按 `Win` → 输 `powershell` → 回车打开 **Windows PowerShell**。  
  这个窗口**全程保持打开**，所有命令都在它里面跑。

### 1 · 准备清单（1 分钟核对）

| 准备项 | 判据 |
|--------|------|
| 仓库路径 | `C:\dev-projects\second-brain-hub`（若不同，下文路径里的这一段**整体替换**） |
| iPhone + 数据线 | 有线连 PC，手机解锁；首次连接弹窗点「**信任**」 |
| Apple 软件 | Windows 10/11 装 **「Apple 设备」**，或仍可用的老版 **iTunes** |
| 时间窗 | 30 ~ 90 分钟（首次全量备份可能较慢） |
| telemetry DuckDB | 常见在 `D:\second-brain-assets\_runtime\logs\brain-telemetry.duckdb`；以 `config/paths.yaml` 为准 |

### 2 · 总览（先看一眼顺序）

| 步骤 | 做什么 | 约时 |
|------|--------|------|
| 3 | 环境自检（一次粘贴） | 1 分钟 |
| 4 | iPhone **非加密**本地备份 | 10 ~ 60 分钟 |
| 5 | 解析备份里的 `AddressBook.sqlitedb` | 1 分钟 |
| 6 | **快照** DuckDB（强制，回滚保险） | 10 秒 |
| 7 | **Dry-run**（只读，不写库） | 1 分钟 |
| 8 | **Apply**（真写入） | 1 ~ 5 分钟 |
| 9 | 审计 + 验收打勾 | 2 分钟 |

---

### 3 · 环境自检（整段复制，一次粘贴）

```powershell
cd C:\dev-projects\second-brain-hub\tools\py
$env:PYTHONPATH = "src"
$env:PYTHONIOENCODING = "utf-8"
python --version
python -c "import duckdb; print('duckdb ok')"
Test-Path "D:\second-brain-assets\_runtime\logs\brain-telemetry.duckdb"
python -m brain_cli.main contacts-ingest-ios --help | Select-Object -First 5
```

**期望（四条全中才通过）**：

- 提示符里出现 `...\second-brain-hub\tools\py`
- `Python 3.x`、`duckdb ok`
- `True`
- 帮助前几行里含 `contacts-ingest-ios`，无红色 Traceback

**卡住时**：

- `python` 找不到 → 装 Python 后**重开** PowerShell 再来（否则 PATH 不刷新）。
- `duckdb` 报 `ModuleNotFoundError` → `pip install duckdb`。
- `Test-Path` 输出 `False` → 打开 `config/paths.yaml`，把 telemetry 路径改成你本机的再测；**未通过不要继续**。

---

### 4 · iPhone 非加密本地备份（人工）

1. 打开 **Apple 设备**（或 iTunes），选中这台 iPhone。
2. 进入「**备份**」面板，**取消勾选「加密本地备份」**。
3. 若弹「确定不加密」→ 选 **不加密**。
4. 点 **立即备份**，等进度条**完全走完**。

**硬规则**：加密备份里的 `AddressBook.sqlitedb` 是锁死的；hub **不解密、不破解**。若你必须加密，**停在这里**，改走 iCloud 通讯录导出 vCard（不在本 runbook 范围）。

备份通常落在 `%LOCALAPPDATA%\Apple Computer\MobileSync\Backup\<UDID>\`（40 位十六进制文件夹，里面有 `Manifest.db`）。**不必手抄**，下一步自动解析。

---

### 5 · 定位备份里的 AddressBook

```powershell
python -m brain_cli.main backup-ios-locate
```

**期望**：一段嵌套 JSON，只看 `address_book`：

```json
{
  "address_book": {
    "status": "ok",
    "backup_dir": "C:\\Users\\...\\Backup\\<UDID>",
    "selected": "C:\\Users\\...\\Backup\\<UDID>\\<hash-or-AddressBook.sqlitedb>"
  }
}
```

- `selected` **非空、`status: ok`** → 通过，进入第 6 步。
- `selected` = `null` 或 `status` 是 `not_found` / `unresolved` → **不要**做快照也不要 ingest。

**卡住时**：

- 备份未完成 / 加密 / 落在非默认目录 → 回第 4 步。
- 你清楚 UDID 目录：`python -m brain_cli.main backup-ios-locate --backup-root "完整路径"`。
- 资源管理器进 UDID 文件夹搜 `AddressBook.sqlitedb`，**把完整路径复制下来**，第 7/8 步加 `--db "完整路径"`。

---

### 6 · 给 DuckDB 做快照（强制，回滚保险）

```powershell
python -m brain_cli.main ingest-backup-now --label bing1-ios-addressbook
```

**期望**：`status: ok`；有 `snapshot`（新生成的 `.duckdb` 路径）与 `sha256`。**把 `snapshot` 路径复制到记事本**。

**回滚步骤**（仅在需要时）：

1. 关掉所有打开 `brain-telemetry.duckdb` 的进程：本仓库 CLI、Cursor MCP、其它 Python。
2. 覆盖回去（路径以 `paths.yaml` 为准）：

    ```powershell
    Copy-Item "<你记下的 snapshot 路径>" "D:\second-brain-assets\_runtime\logs\brain-telemetry.duckdb" -Force
    ```

3. 重启依赖它的工具（MCP、CLI）。

---

### 7 · Dry-run（只读，绝不写库）

```powershell
python -m brain_cli.main contacts-ingest-ios --dry-run | Out-File -Encoding utf8 "$env:TEMP\bing1-contacts-dryrun.json"
notepad "$env:TEMP\bing1-contacts-dryrun.json"
```

若第 5 步是手动拿到的 `--db` 路径：

```powershell
python -m brain_cli.main contacts-ingest-ios --dry-run --db "C:\完整路径\AddressBook.sqlitedb" | Out-File -Encoding utf8 "$env:TEMP\bing1-contacts-dryrun.json"
```

**肉眼检查**（对着 `sample` 前 20 条看）：

| 字段 | 合格 |
|------|------|
| `status` | `dry_run` |
| `sample[*].name` | 中英文都能正常显示，**不是** `???` 一片 |
| `sample[*].phones` | 形似真号码（apply 时才会归一化成 `86` 前缀，此刻不强求） |
| `sample[*].emails` | 形似真邮箱 |
| `person_rows` | 量级像你的通讯录（常见 100 ~ 2000；`0` 或上万要警惕） |

**任一项不对劲 → 停**，把 JSON 发给能判读的人，不要继续第 8 步。

---

### 8 · Apply（真写入，本人在电脑旁）

前置：第 6 步快照成功 + 第 7 步 dry-run 样本你认可。

```powershell
python -m brain_cli.main contacts-ingest-ios | Out-File -Encoding utf8 "$env:TEMP\bing1-contacts-apply.json"
Get-Content "$env:TEMP\bing1-contacts-apply.json"
```

（若第 7 步用过 `--db "..."`，这里**同样加**，保持一致。）

**期望 JSON**：

- `status`: `ok`
- `persons_created` > 0，且**接近**第 7 步的 `person_rows`（已有 person 只追加 identifier，轻微少是正常）
- `identifiers_added` ≥ `persons_created`（每人至少 1 个电话或邮箱）
- **没有**顶层 `error`

**Apply 中途 Python 抛异常**：事务会 `ROLLBACK`，DuckDB 逻辑上回到 apply 前；**把终端完整报错 + `%TEMP%\bing1-contacts-apply.json` 一起保留**，不要立刻重跑。

---

### 9 · 审计 + 验收打勾

```powershell
python -m brain_cli.main ingest-log-recent --source ios_addressbook --days 7 --limit 5
```

**期望**：最新一条 `mode: apply`、`status: ok`、`persons_added` 合理。

**验收清单**（四条都 ✓ 即可收工）：

- [ ] Apply 返回 `status: ok`，`persons_created` ≈ 备份里的联系人数（±5%）
- [ ] `ingest-log-recent` 有对应那一行
- [ ] `python -m brain_cli.main graph-rebuild-if-stale --force` 成功，`persons` 计数与 DuckDB 一致
- [ ] 手挑 3 个熟人跑 `python -m brain_cli.main who "某某"`，能查到

**可选**（不影响收工）：

```powershell
python -m brain_cli.main merge-candidates sync-from-graph --dry-run
```

如出现 T3 合并候选，**本次不处理**——留给 B-ING-2（真实分布出来后再调阈值）。扫一眼有个数即可。

四条 ✓ 后，到本文末「## 打勾」一节填日期收工。

---

### 故障速查

| 症状 | 直接动作 |
|------|----------|
| `backup-ios-locate` 的 `address_book.selected` = `null` 或 `status` ≠ `ok` | 备份未完成 / 加密 / 非默认路径；回第 4 步，或用 `--backup-root` |
| Dry-run `sample` 姓名大片 `???` | 备份仍是加密的；回第 4 步关掉加密，**不要**硬继续 |
| `contacts-ingest-ios` 报 `missing_db` | 回第 5 步拿到完整 `.sqlitedb` 路径，加 `--db "完整路径"` |
| Apply 期间抛异常 | 事务已 ROLLBACK；保留完整 JSON + 报错，不要重试 |
| 想完全回到 apply 前 | 按第 6 步「回滚步骤」覆盖 snapshot |

### 求助时请附这些

1. `%TEMP%\bing1-contacts-dryrun.json`（第 7 步）
2. `%TEMP%\bing1-contacts-apply.json`（第 8 步，若已跑）
3. `ingest-log-recent` 整段终端输出
4. 一句话：**备份是否未加密** / **是否首次 apply** / **卡在第几步的哪一条判据**

---

## 前置要求（跑之前确认）

- [ ] Windows PC 是当前这台，hub 在 `C:\dev-projects\second-brain-hub`
- [ ] Python 环境有 `duckdb`（`python -c "import duckdb"` 不报错就行）
- [ ] DuckDB 文件存在：`D:\second-brain-assets\_runtime\logs\brain-telemetry.duckdb`
- [ ] **iPhone 连接了 PC**，但先**不要开始备份**（看第 1 步）

## 超详细操作稿（PowerShell · 复制粘贴版）

下面与「五步上线」一一对应，只是每一步拆成**可执行的命令**、**期望看见什么**、**卡住时怎么办**。建议新开一个 **Windows PowerShell 5.1** 或 **PowerShell 7** 窗口，全程在本窗口完成（避免漏设环境变量）。

### 阶段 0 · 环境与仓库自检（约 2 分钟）

1. 进入 Python 工具目录并固定编码（避免 JSON 里中文在个别终端乱码）：

```powershell
cd C:\dev-projects\second-brain-hub\tools\py
$env:PYTHONPATH = "src"
$env:PYTHONIOENCODING = "utf-8"
```

2. 确认 Python 与 DuckDB 可用：

```powershell
python --version
python -c "import duckdb; print('duckdb ok')"
```

3. 确认 DuckDB 文件在约定路径（若你的 `paths.yaml` 改过路径，以实际为准）：

```powershell
Test-Path "D:\second-brain-assets\_runtime\logs\brain-telemetry.duckdb"
```

期望输出：`True`。若是 `False`，先不要继续 ingest，先检查 `config/paths.yaml` 里的 telemetry 路径。

4. 确认 `brain` 子命令能加载（看到帮助里含 `contacts-ingest-ios` 即可）：

```powershell
python -m brain_cli.main contacts-ingest-ios --help
```

**本阶段通过标准**：无红色报错；`duckdb ok` 打印成功。

---

### 阶段 1 · 非加密备份（人工 · 约 10–60 分钟）

在 **Apple 设备 / iTunes / Finder（Windows 上为「Apple 设备」应用）** 中：

1. 选中当前 iPhone。
2. 找到 **「加密本地备份」** → **取消勾选**。
3. 若提示确认「不加密」→ 选 **不加密**。
4. 点击 **立即备份**，等进度完成。

**硬门槛**：加密备份里的通讯录库 hub **不解密**、也不尝试破解；若保持加密，请停下并改用「iCloud 导出 vCard」等其它路径（不在本 runbook 范围内）。

备份完成后，Windows 上默认根目录通常是：

```text
%LOCALAPPDATA%\Apple Computer\MobileSync\Backup\<UDID>\
```

`<UDID>` 为约 40 位十六进制文件夹名；其下应有 `Manifest.db`。

---

### 阶段 2 · 定位备份与 AddressBook 路径（命令 · 约 1 分钟）

仍在 `tools\py` 目录、`PYTHONPATH` 已设的前提下：

```powershell
python -m brain_cli.main backup-ios-locate
```

CLI 返回**嵌套 JSON**（实现见 `ios_backup_locator.locate_bundle`）：

- 顶层键：`whatsapp`、`address_book`（两条线一次列出；你只要看通讯录）。
- **`address_book.selected`**：解析到的 **`AddressBook.sqlitedb`** 绝对路径字符串；非空则自动 ingest 可用。
- **`address_book.backup_dir`**：当前选用的 UDID 备份根目录。
- **`address_book.status`**：一般为 `ok`；若为 `not_found` / `unresolved`，不要继续 ingest。

若通讯录未解析：

- 确认阶段 1 备份已成功、且**未加密**。
- 若你知道 UDID 文件夹路径，显式传入（示例）：

```powershell
python -m brain_cli.main backup-ios-locate --backup-root "C:\Users\<你>\AppData\Local\Apple Computer\MobileSync\Backup\<UDID>"
```

常见备份根（择一存在即可）：`%LOCALAPPDATA%\Apple Computer\MobileSync\Backup\`、或 `%USERPROFILE%\Apple\MobileSync\Backup\`。

**本阶段通过标准**：`address_book.selected` 非空且指向存在的文件；否则不要进入阶段 3。

---

### 阶段 3 · DuckDB 快照（强制 · 约 10 秒）

**任何 `--apply` 真写入之前都必须做**。这是整库回滚保险。

```powershell
python -m brain_cli.main ingest-backup-now --label bing1-ios-addressbook
```

**期望 JSON 含义（重点字段）**：

- `status` 为 **`ok`**（或与你本地 `ingest_backup` 实现一致的成功态）。
- 出现 **`snapshot`** / **`path`** 类字段，指向新生成的 `*.duckdb` 备份文件路径。
- 出现 **`sha256`**（或 sidecar 校验文件），便于事后核对文件未被篡改。

请**手动复制**打印出来的快照路径到一个记事本（回滚要用）。

**回滚（仅在需要时）**：关闭所有占用 `brain-telemetry.duckdb` 的进程（本仓库 CLI、Cursor MCP、其它 Python），将快照文件复制覆盖 telemetry 库路径（与 `paths.yaml` 一致），再重启相关工具。

**本阶段通过标准**：快照命令成功结束；你已保存快照路径。

---

### 阶段 4 · Dry-run（只读 · 约 1 分钟）

Dry-run **不写 DuckDB**，只解析备份并给出样本。

```powershell
python -m brain_cli.main contacts-ingest-ios --dry-run
```

输出较长，建议同时落盘便于你和我对照：

```powershell
python -m brain_cli.main contacts-ingest-ios --dry-run | Out-File -Encoding utf8 "$env:TEMP\bing1-contacts-dryrun.json"
notepad "$env:TEMP\bing1-contacts-dryrun.json"
```

**人工检查 `sample` 数组（前 20 条左右）**：

| 检查项 | 合格 |
|--------|------|
| 姓名显示 | 中文/英文可读，不是大片 `?` |
| `phones` | 号码大致合理（apply 后会走归一化，不要求此处已是 `86`） |
| `emails` | 看起来像真实邮箱 |
| `person_rows` | 总量级合理（常见几百～几千；若为 0 或极端大，先停） |

若 CLI 报 **`missing_db`**，说明自动定位失败。请用资源管理器在备份 UDID 目录下搜索 **`AddressBook.sqlitedb`**，找到后显式传入：

```powershell
python -m brain_cli.main contacts-ingest-ios --dry-run --db "D:\完整路径\AddressBook.sqlitedb"
```

**本阶段通过标准**：`status` 为 **`dry_run`**（或文档约定的 dry-run 成功态）；样本肉眼可信。

---

### 阶段 5 · Apply（真写入 · 约 1–5 分钟）

**确认**：阶段 3 快照已成功；阶段 4 样本你已认可；**本人在电脑旁**（`real-ingest-scope` 要求：真 apply 时用户在场）。

```powershell
python -m brain_cli.main contacts-ingest-ios
```

未传 `--db` 时仍会自动定位；若 dry-run 时你已必须用 `--db`，此处**用同一路径**：

```powershell
python -m brain_cli.main contacts-ingest-ios --db "D:\完整路径\AddressBook.sqlitedb"
```

**成功时 JSON 典型特征**：

- `status`: **`ok`**
- `persons_created`: 首次全量导入时通常 **> 0**，数量级应接近 dry-run 里的 `person_rows`（不要求逐字相等：已有 person 可能只追加 identifier）
- `identifiers_added`: 通常 **≥** 有明显标识增量
- 不应出现未解释的顶层 **`error`**（若有，事务应已回滚，见下文故障表）

建议保存输出：

```powershell
python -m brain_cli.main contacts-ingest-ios | Out-File -Encoding utf8 "$env:TEMP\bing1-contacts-apply.json"
```

---

### 阶段 6 · 审计日志（约 30 秒）

写入成功后应有一条 JSONL 事件（字段含 `started_at`、`elapsed_ms`、`persons_added` 等）：

```powershell
python -m brain_cli.main ingest-log-recent --source ios_addressbook --days 7 --limit 5
```

**期望**：`events` 数组最新一条的时间、路径、`mode`=`apply`、`status`=`ok`。

若 ingest 中途抛错，仍可能出现一行 `status`=`error` 的审计 —— 用于复盘，不把失败当成成功。

---

### 阶段 7（可选）· T3 / 图 / 抽查熟人

按需执行（详见上文「步骤 6（可选）」与「退出标志」）：

```powershell
python -m brain_cli.main merge-candidates sync-from-graph --dry-run
python -m brain_cli.main graph-rebuild-if-stale --max-age-hours 1
python -m brain_cli.main who "<某人显示名>"
```

---

### 如何把结果发给我判读

若任一步.output 看不懂，请打包发：

1. **`bing1-contacts-dryrun.json`**（阶段 4 保存的文本）。
2. **`bing1-contacts-apply.json`**（阶段 5，若已跑）。
3. **`ingest-log-recent`** 整段终端输出。
4. 一句话说明：**备份是否确认未加密**、**是否首次 apply**。

我会根据 JSON 字段告诉你是否可继续、是否要回滚快照。

---

## 五步上线（精简版 · 与上文阶段对应）

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

### 步骤 2 · 定位备份（CLI）

```powershell
cd C:\dev-projects\second-brain-hub\tools\py
$env:PYTHONPATH = 'src'
python -m brain_cli.main backup-ios-locate
```

**期望输出**（JSON）：嵌套结构；通讯录路径在 **`address_book.selected`**（`AddressBook.sqlitedb` 的绝对路径）。可选 **`whatsapp`** 块（与本步骤无关）。

**若 `address_book.selected` 为 null**：备份未完成、未找到含 `Manifest.db` 的 UDID 目录、或 Manifest 未解析出文件。回到步骤 1，或用 `--backup-root` 指向正确 UDID 目录再跑一次。

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

- [x] **2026-04-22** 第一次成功 apply，本人在场。

## 首次执行痕迹（2026-04-22）

**源**：`AddressBook.sqlitedb`（主库）  
`C:\Users\chase\Apple\MobileSync\Backup\00008101-0002250A21A3003A\31\31bb7ba8914766d4ba40d6dfb6113c8b614be442`  
`source_sha256`: `7add7e476e34b738dd1e31bd7aad75f5726bb6d3d6bc3c8929cd64888496b272`

**Pre-apply snapshot**：  
`D:\second-brain-assets\_backup\telemetry\20260422-011824-bing1-ios-addressbook.duckdb`  
`sha256`: `53ad43bd4482aa0db6e602032aa9babcc966ee543ab7b1f112df3eaca22bc4dd` · 38,809,600 bytes

**Apply 结果**（`contacts-ingest-ios`）：

| 字段 | 值 |
|------|----|
| `status` | `ok` |
| `person_rows` | 248 |
| `multi_value_rows` | 250 |
| `persons_created` | **248** |
| `identifiers_added` | **250** |
| `elapsed_ms` | 4116.2 |

**审计**（`ingest-log-recent --source ios_addressbook`）：最新一条 `mode: apply`、`status: ok`、`persons_added: 248`、`identifiers_added: 250`、`t3_queued: 0`、`backup: null`（⚠️ 见 follow-up）。

**Graph rebuild**：`rebuilt: true`；`persons: 396`、`identifiers: 468`、`has_identifier_edges: 465`、`interacted_edges: 0`。

**验证**：`who "Cheng Wang" | "Hammond" | "Junlin"` 全部命中。

**事后发现（不阻塞 B-ING-1 打勾，转 follow-up）**：

- `backup-ios-locate` 把空的 `Library/AddressBook/Family/...:22AddressBook.sqlitedb` 误选为 `selected`；主库 `Library/AddressBook/AddressBook.sqlitedb` 需要手动 `--db` 指定。
- ingest 审计里 `backup` 字段为 `null`，未回填第 6 步 snapshot。
- 电话归一化对 NL 本地格式 `06XXXXXXXX` 没映射到 `+316XXXXXXXX` → 本次产生 `Hammond / Jerrel / Patricia` 等 3 组可本自动 merge 却未自动 merge 的同名人。
- DuckDB 里检出 174 行 `T xxx` 测试夹具 person（所有 T-fixture `person_identifiers=0`；`merge_log.kept_person_id` 引用 8 条，其余业务表 0）。
- 存在 9 组真实同名重复（详见 `bing1-followups.md`）。

→ 全部转入 **`architecture/bing1-followups.md`**。

## 变更记录

| 日期 | 说明 |
|---|---|
| 2026-04-21 | 首版；6 步，配合 B-ING-0 (`20924ab`) + `27c0827` 使用。 |
| 2026-04-22 | 新增「超详细操作稿」：阶段 0–7（ PowerShell 复制粘贴、`backup-ios-locate` 嵌套 JSON 说明、`Out-File` 落盘）；精简版步骤 2 与 `address_book.selected` 对齐；备份路径注明 `LOCALAPPDATA` / `Apple\MobileSync`。 |
| 2026-04-22 | 重写「保姆级一步步操作指南」：按数字步骤 0–9 对齐「操作 / 期望 / 卡住时」三栏；环境自检整合为一次粘贴；加入 `backup-ios-locate` 期望 JSON 示例、回滚 `Copy-Item` 命令、故障速查表、验收打勾清单；删掉原 A–I 字母小节的冗余标题。 |
| 2026-04-22 | **首次 apply 成功**（248/248，快照 sha `53ad43bd…`）；在文末新增「首次执行痕迹」小节；发现 5 项事后问题，开 `bing1-followups.md` 跟踪。 |
| 2026-04-22 | **B-ING-0.1 关**（Phone normalizer 经 `phonenumbers` + `identity.phone_default_region: NL`）：`identifiers-repair --kinds phone` 真跑出 14 行静默升级 + 9 对跨 person 候选进 T3 队列；快照 `20260422-015459-bing01-phone-normalize.duckdb` sha `a1108eb2…`；顺手挖到 B-ING-1.10（repair dry-run 仍写 `merge_candidates`）。 |
| 2026-04-22 | **B-ING-1.8 进 7/9**：snapshot `20260422-074832-bing01-pre-7-accepts.duckdb` sha `af3be7d2…`；accept Hammond/Jerrel/Patricia/Harry(Schortinghuis)/Lunsing(Kazemier)/Hady/乐燕 共 7 对，pass-2 repair 清掉 7 条 `deleted_duplicate`；persons 402→395 / identifiers 468→461。副作用：`merge_persons` 不回填 alias，导致 `who "Leyan"` 等失效，已 SQL 手挂 4 条 alias + 新开 B-ING-1.11。剩 2 对（`英华/小华`、`悦取/老婆`）pending 待人工。 |
| 2026-04-22 | **B-ING-1.8 ✅ 9/9**：snapshot `20260422-080156-bing18-last-2-accepts.duckdb` sha `75b70cb1…`；accept `英华/小华` + `悦取/老婆`，pass-3 repair 清 2 条 `deleted_duplicate`，T3 队列 `phone_repair_*` 归零。回填 `小华` / `老婆` 2 条 alias（共 6 条 SQL 补救，落到 B-ING-1.11 彻底修）。persons 402→**393**（-9）/ identifiers 468→**459**（-9）/ Kuzu graph 393·459·456。 |
