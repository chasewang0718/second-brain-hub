---
title: Brain Inbox 闭环 · 剪贴板一键归档 + 阈值自动整理
tags: [workflow, automation, brain-ops, authoritative-source]
created: 2026-04-18
updated: 2026-04-19
status: active
authoritative_at: C:\dev-projects\second-brain-hub\rules\inbox-ingest.md
mirror_at: D:\brain\01-concepts\workflow\brain-inbox-ingest.md
---

# Brain Inbox 闭环：从 Gemini/任意剪贴板 → 自动归档

> **📍 权威副本**: `C:\dev-projects\second-brain-hub\rules\inbox-ingest.md`
> 镜像: `D:\brain\01-concepts\workflow\brain-inbox-ingest.md`
> **注意**: 本文档内 "brain-tools" 的路径引用是旧架构, 新架构是 `second-brain-hub/tools/`.
> 完整路径映射待下一轮更新.

> **问题**：每天 2+ 次想把 Gemini 的讨论结论、网页片段、灵感 dump 到 brain。手动打开编辑器、粘贴、命名、选目录 = 每次 30 秒心智负担。
>
> **解法**：三层自动化（快捷键 → 剪贴板 → Inbox → AI 分类），Chase 只负责**按 CapsLock+D**，其余都由工具链和 AI 完成。

## 工作流全貌（一张图）

```
[任何应用, e.g. Gemini Web]
        │
        │ Ctrl+C
        ▼
   [剪贴板]
        │
        │ CapsLock+D   ← AutoHotkey 热键
        ▼
  [PowerShell gsave]
        │
        │ 写文件
        ▼
  D:\brain\99-inbox\paste-YYYYMMDD-HHMMSS.md
        │
        ├──(paste-*.md 数 ≥ 10)─── ★ 自动触发路径 (2026-04-19 新增)
        │                          │
        │                          ▼
        │                   [gsave 后台 spawn cursor-agent]
        │                          │
        │                          ▼
        │                   [agent -p --force --trust]
        │                          │
        │                          ▼ (headless, 日志写 .brain-autotrigger.log)
        │                   [完整 8 步流程 + commit + push]
        │
        └──(手动路径)──────────────
                ▼
         [Cursor 打开 brain, 说 "整理 inbox"]
                │
                ▼
         [AI 读完 → 识别主题 → 重命名 → 分类 → 合并 → commit]
                │
                ▼
  01-concepts/ / 02-snippets/ / 03-projects/ / 06-people/ / 07-life/ / ...
```

## 三层组件

### 1. 热键层 · AutoHotkey v2

| 项 | 值 |
|---|---|
| 安装命令 | `winget install AutoHotkey.AutoHotkey` |
| 脚本路径 | `C:\dev-projects\brain-tools\ahk\gsave-hotkey.ahk` |
| 快捷键 | `CapsLock + D` |
| 行为 | 选中文字 → 按热键 → 自动 Ctrl+C + 推送 inbox（2026-04-19 升级） |
| 管理仓库 | `chase-brain-tools`（见 [brain-tools-index.md](./brain-tools-index.md)） |
| 运行方式 | 由 `brain-tools/install.ps1` 在启动目录建快捷方式，开机自启 |
| 重启脚本 | `Stop-Process -Name AutoHotkey64 -Force; Start-Process <ahk 路径>`（或直接双击 `.ahk` 文件） |

**行为（2026-04-19 升级）**：

1. 按 CapsLock+D → **先自动发 Ctrl+C 复制选中文字**
2. `ClipWait(0.5)` 等最多 500ms 看剪贴板有没有被填上
3. **有选中** → 用选中内容
4. **没选中** → 恢复原剪贴板作为降级（向后兼容：老流程"先 Ctrl+C 再 CapsLock+D"照样能用）
5. 调用 `powershell.exe gsave` 写入 inbox

**使用方式**：
- ✅ **新推荐**：选中文字 → CapsLock+D（一步到位，**不用先 Ctrl+C**）
- ✅ **兼容旧**：Ctrl+C → CapsLock+D（照样工作）

**脚本全文**见 `brain-tools` 仓库：`C:\dev-projects\brain-tools\ahk\gsave-hotkey.ahk`（不在本卡 inline，避免两处同步）

### 2. PowerShell 函数层

| 项 | 值 |
|---|---|
| Profile 路径 | `C:\Users\chase\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1` |
| Inbox 根 | `D:\brain\99-inbox` |
| 文件名规则 | `paste-YYYYMMDD-HHMMSS.md` |
| 编码 | UTF-8 **with BOM**（Windows PowerShell 5.1 必须） |

四个核心函数（2026-04-19 扩展）：

- `gsave` — 读剪贴板，写入 inbox，加 YAML frontmatter（source, saved_at, status）；**保存后计数，≥ 10 自动 spawn cursor-agent**
- `ginbox` — 列出当前 inbox 所有未加工文件 + 年龄 + auto-trigger 阈值进度 + 锁状态
- `gclean` — 手动触发一次 cursor-agent 整理（不等阈值）
- `gclean-log` — 查看最近一次 auto-trigger 日志（`.brain-autotrigger.log`）

配置变量（Profile 顶部）：
- `$BRAIN_AUTO_THRESHOLD = 10` — 阈值
- `$BRAIN_AGENT_CMD = "C:\Users\chase\AppData\Local\cursor-agent\agent.cmd"` — cursor-agent CLI 位置
- `$BRAIN_AUTO_LOCK / $BRAIN_AUTO_LOG` — 运行时产物（已加入 `.gitignore`）

完整定义见 Profile 文件（不复制到本卡，避免两处同步）。

### 3. AI 分类层

两个入口：

**A. 手动入口**：在 Cursor 里说 **"整理 inbox"** 或快捷触发词（见 `AGENTS.md` 第 8 条）。

**B. 自动入口（2026-04-19 新增）**：`gsave` 计数 ≥ 10 时自动 spawn `cursor-agent` 后台进程。AI 以 headless 模式跑（`-p --force --trust`），完整 8 步 + 5-pass 流水线，产出写入 `.brain-autotrigger.log`。

AI 会（两个入口都一样）：

1. 读每个 `paste-*.md` 的内容
2. **自动识别主题**（Chase 不打标签）
3. 走 5-pass 处理流水线（见 AGENTS.md 第 8 条）
4. 英文 kebab-case 重命名
5. 按决策树归类（必要时进化决策树：信号 A-E）
6. **必要时直接建顶层目录 / 更新 `00-memory/`**（L1 权限，手动入口下）；自动入口下保守，新分类打 pending-category
7. 输出整理报告 + commit（可多次 commit 提高可读性）

## 首次部署清单（新机器照做）

见 `brain-tools-index.md` 的"新机器部署清单"——通过 `install.ps1` 一键完成 AHK 脚本、Profile、开机自启三件事。

## 常见坑

| 症状 | 原因 | 解法 |
|---|---|---|
| 运行 `gsave` 报"无法识别" | Profile 未加载 | 新开 PowerShell 窗口，或 `. $PROFILE` |
| Profile 中文乱码、parser error | 文件没有 UTF-8 BOM | 用 `Out-File -Encoding UTF8` 重写 |
| 按 CapsLock+D 无反应 | AHK 脚本没运行 | 任务管理器看有无 AutoHotkey64 进程；没有就手动启动 `.ahk` |
| Inbox 堆到 10+ 文件 | 没关系，auto-trigger 会自动清 | 看 `gclean-log` 追踪进度 |
| auto-trigger 不触发 | `agent.cmd` 不在 PATH / 锁文件卡住 | `gclean-log` 看错误；手动 `Remove-Item .brain-autotrigger.lock` |
| auto-trigger 重复触发 | 理论上锁文件已防护（15 分钟过期） | 看到异常直接 `Stop-Process` + 删锁 |
| cursor-agent 需要 API key | 首次运行可能要求登录 | `agent` 交互式跑一次完成登录，之后 headless 能跑 |
| 剪贴板是图片/富文本 | `Get-Clipboard -Raw` 只读纯文本 | 图片另存，再手动整理（这个场景少见） |

## 为什么是这个架构

| 可能的替代方案 | 为何没选 |
|---|---|
| 手动粘贴到 Cursor 让 AI 存 | 每次 30 秒，2 次/天 = 每月耽误 30 分钟；心智负担更高 |
| Chrome 插件抓 Gemini | 只覆盖 Gemini，不覆盖"任何剪贴板来源"；而且 Gemini UI 随时可能变 |
| 云端脚本（iCloud/OneDrive） | 增加网络依赖；brain 在本地 D:\ 已经是真源 |
| 直接写进 brain 某个日期文件 | inbox 的价值是**延迟决策**，立刻归位反而剥夺了 AI 判断空间 |

## 相关

- `D:\brain\AGENTS.md` 第 8 条：Inbox 批量整理协议完整定义
- `D:\brain\01-concepts\ai\gemini-api-vs-web.md`：为什么不用 API 直连 Gemini
- `D:\brain\99-inbox\README.md`：inbox 目录本身的说明
