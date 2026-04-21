---
title: second-brain-hub 架构索引 (原 brain-tools)
tags: [workflow, dotfiles, tools-index, authoritative-source]
created: 2026-04-18
updated: 2026-04-19-hub-migration
status: active-needs-rewrite
authoritative_at: C:\dev-projects\second-brain-hub\brain-tools-index.md
mirror_at: D:\second-brain-content\01-concepts\workflow\brain-tools-index.md
---

# second-brain-hub · 控制中枢的架构索引

> **📍 权威副本**: `C:\dev-projects\second-brain-hub\brain-tools-index.md`
> 镜像: `D:\second-brain-content\01-concepts\workflow\brain-tools-index.md`
>
> **⚠️ 内容尚未全面更新**: 本文描述的路径 (如 `C:\dev-projects\brain-tools\powershell\*.ps1`)
> 对应 **2026-04-19 前**的旧 `brain-tools` 布局. 新布局为 `second-brain-hub/tools/<domain>/`.
> 详见本仓库 [README.md](README.md) 和各子目录的 README.md. 下一轮将重写本文.

---

## 🆕 新布局速查 (2026-04-19 迁移后)

| 原路径 | 新路径 |
|---|---|
| `brain-tools/ahk/` | `second-brain-hub/tools/ahk/` |
| `brain-tools/powershell/brain-asset-*.ps1` | `second-brain-hub/tools/asset/` |
| `brain-tools/powershell/brain-health-*.ps1` | `second-brain-hub/tools/health/` |
| `brain-tools/powershell/brain-nightly-*.ps1` | `second-brain-hub/tools/housekeeping/` |
| `brain-tools/powershell/brain-staging-*.ps1` | `second-brain-hub/tools/housekeeping/` |
| `brain-tools/powershell/register-*-task.ps1` | `second-brain-hub/tools/health/` 或 `housekeeping/` |
| `brain-tools/powershell/wait-for-batch.ps1` | `second-brain-hub/tools/lib/` |
| `brain-tools/powershell/brain-asset-pdf-*.ps1` | `second-brain-hub/tools/ollama-pipeline/` |
| `brain-tools/ollama-pipeline/*.ps1` | `second-brain-hub/tools/ollama-pipeline/` |
| `brain-tools/ollama-pipeline/schema.json` | `second-brain-hub/schemas/pdf-classify.schema.json` |
| `brain-tools/ollama-pipeline/prompt-template.md` | `second-brain-hub/prompts/system/pdf-classifier.md` |
| `brain-tools/ollama-pipeline/category-to-path.md` | `second-brain-hub/tools/ollama-pipeline/` (暂留, 将转 `config/categories.yaml`) |

---

# (以下为旧内容, 路径描述过时, 功能说明仍然有效)

> 本卡是 **指针 + 架构说明**——不存任何代码，只记录 `chase-brain-tools` 仓库的位置、结构、和 brain 之间的关系。代码真源在仓库自身。

## 项目位置

| 维度 | 信息 |
|---|---|
| **本地路径** | `C:\dev-projects\brain-tools` |
| **独立 Git 仓库** | ✅ 是（与 brain 分仓） |
| **GitHub 仓库** | [chase-brain-tools](https://github.com/chasewang0718/chase-brain-tools)（私有） |
| **覆盖范围** | Windows + AutoHotkey v2 + PowerShell 5.1 |

## 为什么分仓

按照 brain 的架构哲学（见 `AGENTS.md`）：

| 资产类型 | 归宿 |
|---|---|
| **知识 · Markdown** | `chase-brain` |
| **代码项目 · 特定领域** | 独立仓库（如 `cito-latex-template`） |
| **本机运行时配置** | `chase-brain-tools`（本仓库） |

这三者**不混放**。brain 里留"架构索引卡"（本卡 + `latex-engine-index.md`），AI 作为"跨仓库索引器"在需要时读卡跳转。

## 仓库结构速查

```
brain-tools/
├── ahk/
│   ├── Chase202602.ahk             Chase 日常输入体系
│   └── gsave-hotkey.ahk            CapsLock+D → inbox
├── powershell/
│   ├── Microsoft.PowerShell_profile.ps1
│   ├── brain-weekly-report.ps1     周报生成脚本 (被 Task Scheduler 调用)
│   ├── register-weekly-task.ps1    注册 / 注销周报定时任务
│   ├── brain-asset-migrate.ps1     外部资产扫描 / 迁移 (B3 已迁 Python: brain asset-scan / asset-migrate-execute; PS 暂留对拍)
│   ├── brain-asset-source-cleanup.ps1   迁移 7 天后清理源文件 (带 size 校验)
│   ├── register-source-cleanup-task.ps1 注册一次性清源任务
│   ├── brain-asset-pdf-pilot.ps1        Phase 2.3 PDF pilot (小样本验证)
│   ├── brain-asset-pdf-batch.ps1        Phase 2.3 PDF batch orchestrator
│   ├── brain-staging-dispose.ps1        98-staging/ 三层处置 (L1 删 / L2 聚类 / L3 agent)
│   ├── brain-health-check.ps1           brain 健康检查 (断链/孤儿/frontmatter, 0 token)
│   ├── brain-asset-dedup.ps1            brain-assets SHA256 去重候选 (0 token, dry-run)
│   ├── brain-asset-stats.ps1            brain-assets 目录/ext/月份统计 (0 token)
│   ├── brain-nightly-push.ps1           每晚 22:00 自动 git push (brain + brain-tools)
│   ├── register-nightly-push-task.ps1   注册 BrainNightlyPush 定时任务
│   └── wait-for-batch.ps1               watcher: 等 Phase 2.3 完成自动启 overview dry-run
├── install.ps1
├── README.md
└── .gitignore
```

## 各组件职能

### `ahk/Chase202602.ahk`

| 热键 | 功能 |
|---|---|
| Tab+W / Tab+Q | 智能关闭 / 截图 |
| CapsLock（单按） | 粘贴 |
| CapsLock + Q/W/E/A/S | 剪切 / 撤销 / 重做 / 全选 / 保存 |
| Shift（单按） | 复制 |
| F12 | 挂起所有热键 |
| ;mail / ;web / ;tel / ;addr / ;date | 文本扩展 |

**重要**：F12 是"紧急开关"，调试别的 AHK 脚本时先按一下挂起 Chase202602 避免键位冲突。

### `ahk/gsave-hotkey.ahk`

**CapsLock+D** → 剪贴板 → `D:\second-brain-content\99-inbox\paste-YYYYMMDD-HHMMSS.md`

详见 `01-concepts/workflow/brain-inbox-ingest.md` 和 `AGENTS.md` 第 8 条。

### `powershell/Microsoft.PowerShell_profile.ps1`

**双副本机制**：
- **仓库版**：`C:\dev-projects\brain-tools\powershell\Microsoft.PowerShell_profile.ps1`（版本化权威源）
- **运行时**：`$PROFILE` = `C:\Users\chase\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`（PowerShell 实际加载的位置）

**修改规则**：改仓库版 → 重跑 `install.ps1` 同步到 `$PROFILE` → 重开 PowerShell 生效。

**函数清单**：

| 函数 | 功能 | 类别 |
|---|---|---|
| `gsave` | 读剪贴板 → 写 inbox；累计 ≥ 10 自动触发 cursor-agent 整理 | inbox |
| `ginbox` | 列出 inbox 现状 + auto-trigger 阈值进度 + 锁状态 | inbox |
| `gclean` | 手动立即触发一次 inbox 整理（不等阈值） | inbox |
| `gclean-log` | 查看 auto-trigger 日志（`-Tail N` 参数） | inbox |
| `brain-ask` | **只读**语义查询 brain 仓库（命令行版 Cursor 侧边栏） | agent |
| `g-ask` | 通用一次性问题，不限定 brain（替代部分 ChatGPT 网页使用） | agent |
| `explain-this` | 管道版快速解释（`git log \| explain-this`） | agent |
| `gasset` | 查看 `D:\second-brain-assets\` 现状（Tier B 容量 / 分布） | assets |
| `gasset-scan <path>` | Stage 1 扫描: 按规则分类源目录, 输出 manifest TSV（0 token） | assets |
| `gasset-migrate [-ManifestPath <p>]` | Stage 3 执行: 按 manifest copy 文件到 Tier B（不 move，保留原文件） | assets |
| `gbatch-status` / `gbatch-tail` / `gbatch-resume` / `gbatch-stop` | Phase 2.3 PDF 批处理监控 | batch |
| `ghealth` | brain 健康检查（断链 / 孤儿 / frontmatter / asset_path，0 token） | housekeeping |
| `gdedup` | brain-assets SHA256 去重扫描，生成候选报告（0 token, dry-run） | housekeeping |
| `gstats` | brain-assets 目录 / ext / 月份分布统计（0 token） | housekeeping |
| `goverview [-Execute]` | Tier B 叶子目录 → Tier A 总览卡生成（默认 dry-run） | agent |
| `gwatch-batch [-TargetPid <n>]` | watcher: 等 Phase 2.3 batch 跑完自动启 overview dry-run | housekeeping |

### `powershell/brain-weekly-report.ps1`

每周日 21:00 由 Task Scheduler 调用，后台 headless 运行：

1. 让 cursor-agent 读本周 git log + 04-journal/ 条目
2. 按模板生成 `04-journal/weekly/YYYY-Www.md`
3. 自动 git commit

**日志**：`D:\second-brain-content\.brain-weekly.log`（已进 `.gitignore`）
**锁文件**：`D:\second-brain-content\.brain-weekly.lock`（防重复运行）
**手动触发**：`.\register-weekly-task.ps1 -RunNow`

### `powershell/brain-asset-migrate.ps1`

Tier B 资产批量迁移的"引擎"。按 AGENTS.md §11 的 4 阶段流水线设计：

**Stage 1 · Scan** — `gasset-scan <source>`（0 token）
- 枚举源目录 → 读 `~/.brain-exclude.txt` 过滤 Tier C → 按扩展名 / EXIF 日期生成 TSV manifest
- 输出：`D:\second-brain-assets\_migration\<job>-manifest.tsv`
- manifest 可用 Excel / VSCode 打开手改 `target_dir` / `action`

**Stage 3 · Execute** — `gasset-migrate [-ManifestPath <p>]`
- 按 manifest 逐行 copy（不 move），保留原文件 mtime
- 目标重名自动加 `-YYYYMMDD-HHMMSS` 后缀
- trash 候选只标记不删（用户 7 天后自己清理）
- 失败行记到 `<job>-execute.log`，不中断整体

**分类规则**（内置）：photo → `10-photos/YYYY-MM/`（按 EXIF，fallback mtime）/ video → `12-video/YYYY-MM/` / audio → `13-audio/` / font → `11-fonts/` / archive → `14-archives/` / book → `16-books/` / PDF → `99-inbox/` / text → `99-inbox/` / trash → 标记不动 / 其他 → `98-staging/`

### `powershell/brain-asset-source-cleanup.ps1`

Stage 4 收尾 —— 迁移 N 天后自动清理源位置。为防误删，每个文件要过 **三道校验** 才删：

1. 源文件仍然存在（用户没自己清过）
2. `brain-assets/` 里对应文件存在
3. 源 / 目标文件**大小一致**（快速完整性校验）

任何一条不过就跳过并记日志。

**手动**：`.\brain-asset-source-cleanup.ps1 -DryRun`（推荐先跑）/ 不加参数真删
**日志**：`_migration/<job>-cleanup.log`
**顺便**：清完后删 `D:\BaiduSyncdisk\` 下的空目录（默认开）

### `powershell/register-source-cleanup-task.ps1`

注册 Task Scheduler **一次性任务**执行清源：

| 用法 | 效果 |
|---|---|
| `.\register-source-cleanup-task.ps1` | 默认注册到 2026-04-26 09:00（Phase 2.2 后第 7 天） |
| `.\register-source-cleanup-task.ps1 -RunDate "2026-05-10 21:00"` | 改日期 |
| `.\register-source-cleanup-task.ps1 -Remove` | 提前取消 |
| `.\register-source-cleanup-task.ps1 -RunNow` | 立即跑 DryRun（测试） |

任务名：`BrainAssetSourceCleanup-Baidu2026-04`

### `powershell/brain-health-check.ps1` + `brain-asset-dedup.ps1` + `brain-asset-stats.ps1`

**brain 保养三件套**——零 token，纯元数据分析，可随时跑，适合夜间巡检。

| 脚本 | 输入 | 输出 | 耗时 |
|---|---|---|---|
| `ghealth` | `D:\second-brain-content` | `04-journal/brain-health-YYYY-MM-DD.md` | 秒级 |
| `gdedup` | `D:\second-brain-assets` | `_migration/dedup-YYYY-MM-DD.md` + `.tsv` | 依文件数，百 MB 几分钟 |
| `gstats` | `D:\second-brain-assets` | `04-journal/brain-assets-stats-YYYY-MM-DD.md` | 秒级 |

**健康检查 5 项**：断的 `[[wiki-link]]` / 失效 `asset_path` / frontmatter 缺字段 / 孤儿 md（无人引用）/ 目录命名不一致。

**去重**：两遍扫（先按 size group 再算 SHA256），只报告候选，**不自动删**；`KEEP` 标建议保留的那个。

**统计**：一级目录 / 扩展名 top20 / 按月增长（基于 mtime）/ top10 单文件。

### `powershell/brain-nightly-push.ps1` + `register-nightly-push-task.ps1`

每晚 **22:00** Task Scheduler 自动跑，把 `D:\second-brain-content` 和 `C:\dev-projects\second-brain-hub` 的本地 commit 推到 GitHub。

- **只 push 不 commit**（commit 由人/agent 主动触发，保证粒度）
- 无未推送 commit 就静默跳过，不打扰
- 日志：`D:\second-brain-content\.brain-nightly-push.log`（已 gitignore）
- 任务名：`BrainNightlyPush`

注册 / 改时间 / 立即跑 / 注销：

```powershell
.\register-nightly-push-task.ps1                   # 默认 22:00
.\register-nightly-push-task.ps1 -Time "23:30"     # 改时间
.\register-nightly-push-task.ps1 -RunNow           # 立即手动跑
.\register-nightly-push-task.ps1 -Unregister       # 注销
```

### `powershell/wait-for-batch.ps1`

Watcher 模式——等某个 PID（比如 Phase 2.3 batch）退出，然后自动启动 overview 卡 dry-run（0 token，只出候选清单给人 review）。用 `gwatch-batch` 启动。

设计目的：批处理跑完后"接力"下一个步骤，不浪费人肉监工时间。

### `powershell/register-weekly-task.ps1`

管理 Windows 任务计划程序里的 `BrainWeeklyReport` 任务：

| 用法 | 效果 |
|---|---|
| `.\register-weekly-task.ps1` | 注册（默认） |
| `.\register-weekly-task.ps1 -Remove` | 注销 |
| `.\register-weekly-task.ps1 -RunNow` | 立即手动运行一次（测试） |

**任务参数**：每周日 21:00；用户登录时运行；30 分钟超时；电池模式也跑。

### `install.ps1`

新机器一键部署。步骤：

1. 检查 AutoHotkey v2 是否已装
2. 复制 Profile 到 `$PROFILE`（UTF-8 BOM）
3. 在启动目录建两个快捷方式（Chase202602 / gsave-hotkey），指向本仓库 `ahk/`
4. 立即启动两个 AHK
5. **注册 `BrainWeeklyReport` 任务计划程序**（每周日 21:00 自动生成周报）

**参数**：
- `-SkipStartupShortcuts`：不建开机自启
- `-SkipLaunch`：不立即启动 AHK
- `-SkipWeeklyTask`：不注册周报任务（临时不想要周报时）

## 迁移历史（2026-04-18）

之前的现状：
- `Chase202602.ahk` 放在 `D:\BaiduSyncdisk\AHK\`（百度云同步盘）
- 启动目录的快捷方式指向百度云路径
- 没有 Git 版本历史

迁移完成状态：
- ✅ 本地真源 → `C:\dev-projects\brain-tools\ahk\Chase202602.ahk`
- ✅ 启动目录快捷方式 → 已指向新路径（并新增 `gsave-hotkey.ahk` 开机自启）
- ✅ 百度云副本（`D:\BaiduSyncdisk\AHK\Chase202602.ahk` 及其 lnk）→ **已删除**（2026-04-18 晚）
- ✅ Git 历史从 2026-04-18 开始

**结果**：AHK 脚本现在**只有一份真源**（git 管理），不再存在"改了一份另一份忘记同步"的风险。

## 工作纪律（已落地）

| 规则 | 说明 |
|---|---|
| **AHK 脚本的唯一真源** = `C:\dev-projects\brain-tools\ahk\*.ahk` | 改完直接 commit；重启 AHK 进程即生效 |
| **PowerShell profile 有两个副本** | 仓库版是权威源，`$PROFILE` 是运行时副本；改仓库版后跑 `install.ps1 -SkipStartupShortcuts -SkipLaunch` 同步 |
| **启动目录 lnk 由 `install.ps1` 维护** | 不要手动改启动目录的 lnk；改了就去更新 `install.ps1` |

## 跟 brain 的协作方式

| 场景 | 怎么做 |
|---|---|
| 改个热键 | 直接在 `brain-tools/ahk/*.ahk` 改，commit，重启 AHK 进程 |
| 改 `gsave` 函数行为 | 改仓库版 Profile → `install.ps1 -SkipStartupShortcuts -SkipLaunch`（只同步 Profile） |
| 新增一种本机工具配置（如 WinTerm） | 直接在 `brain-tools/` 加目录，commit；必要时更新 `install.ps1` |
| 记录"为什么这样设计某个热键" | 写到这张卡 或新建 `01-concepts/workflow/<具体主题>.md` |

**关键约束**：brain 里**永远不直接放 AHK/PowerShell 可执行代码**，只放指针和设计说明。

## 兄弟仓库速查

| 仓库 | 地位 | brain 索引位置 |
|---|---|---|
| `chase-brain` | 知识库（Markdown Only） | — |
| `cito-latex-template` | Cito 考试 LaTeX 渲染引擎 | `03-projects/cito-exam/latex-engine-index.md` |
| **`chase-brain-tools`** | 本机工具配置 | **本卡** |

## 新机器部署清单（从 0 恢复）

```powershell
# 1. 装 AutoHotkey v2
winget install --id=AutoHotkey.AutoHotkey --silent --accept-source-agreements --accept-package-agreements

# 2. 装 cursor-agent CLI（让 brain-ask / g-ask / 周报自动化能工作）
irm "https://cursor.com/install?win32=true" | iex

# 3. clone 两个仓库
git clone https://github.com/chasewang0718/chase-brain.git D:\second-brain-content
git clone https://github.com/chasewang0718/chase-brain-tools.git C:\dev-projects\second-brain-hub

# 4. 配置执行策略 + 一键部署（profile + AHK 启动项 + 周报任务）
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
cd C:\dev-projects\brain-tools
.\install.ps1

# 5. 首次登录 cursor-agent（交互, 浏览器弹窗授权一次）
agent login

# 6. 新开 PowerShell 窗口, 冒烟测试
gsave          # 应报"剪贴板为空"
ginbox         # 应显示 inbox 当前状态
g-ask 1+1=?    # agent 类函数验证
Get-ScheduledTask BrainWeeklyReport | Select State  # 应为 Ready
```

预计用时：**15-20 分钟**（主要在等 winget / clone / agent 首次下载模型）。

**关键点**：`install.ps1` **不帮你注册 cursor-agent**（要浏览器登录），这是唯一需要交互的一步。
