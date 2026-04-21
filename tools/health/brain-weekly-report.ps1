#Requires -Version 5.1
<#
.SYNOPSIS
    每周自动生成 brain 周报 (由 Windows 任务计划程序调用).

.DESCRIPTION
    调用 cursor-agent 以 headless 模式分析本周 brain 活动,
    生成一份周报写进 04-journal/weekly/YYYY-Www.md 并 git commit.

.NOTES
    - 触发方式: 每周日 21:00 (Task Scheduler)
    - 日志:     D:\second-brain-content\.brain-weekly.log
    - 手动跑:   直接 .\brain-weekly-report.ps1

    更新历史:
    - 2026-04-19 初版
#>

$ErrorActionPreference = 'Continue'

# ============================================================
# 配置 (与 PowerShell profile 一致)
# ============================================================
$BRAIN_ROOT  = "D:\second-brain-content"
$AGENT_CMD   = "C:\Users\chase\AppData\Local\cursor-agent\agent.cmd"
$LOG_FILE    = Join-Path $BRAIN_ROOT ".brain-weekly.log"
$LOCK_FILE   = Join-Path $BRAIN_ROOT ".brain-weekly.lock"

# ============================================================
# 计算 ISO 周号 (W01 起)
# ============================================================
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$cal     = $culture.Calendar
$now     = Get-Date
$weekNum = $cal.GetWeekOfYear($now, [System.Globalization.CalendarWeekRule]::FirstFourDayWeek, [System.DayOfWeek]::Monday)
$year    = $now.Year
$weekId  = "$year-W$('{0:D2}' -f $weekNum)"
$reportRel = "04-journal/weekly/$weekId.md"

# ============================================================
# 防重复运行
# ============================================================
if (Test-Path $LOCK_FILE) {
    $lockAge = (Get-Date) - (Get-Item $LOCK_FILE).LastWriteTime
    if ($lockAge.TotalMinutes -lt 30) {
        "=== $($now.ToString('yyyy-MM-dd HH:mm:ss')) skipped (lock active, $([Math]::Round($lockAge.TotalMinutes, 1))m old) ===" |
            Out-File $LOG_FILE -Append -Encoding UTF8
        exit 0
    }
    Remove-Item $LOCK_FILE -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $AGENT_CMD)) {
    "=== $($now.ToString('yyyy-MM-dd HH:mm:ss')) ERROR: cursor-agent not found at $AGENT_CMD ===" |
        Out-File $LOG_FILE -Append -Encoding UTF8
    exit 1
}

New-Item $LOCK_FILE -ItemType File -Force | Out-Null

"=== $($now.ToString('yyyy-MM-dd HH:mm:ss')) weekly report start [$weekId] ===" |
    Out-File $LOG_FILE -Append -Encoding UTF8

# ============================================================
# 周报 prompt (交给 cursor-agent)
# ============================================================
$prompt = @"
生成 brain 本周周报, 写进文件 $reportRel (必要时自动创建 04-journal/weekly/ 目录).

数据源 (请自己跑命令获取):
1. git log --since="7 days ago" --pretty=format:'%h %ad %s' --date=short
2. git log --since="7 days ago" --stat --pretty=format:'%h %s'
3. 04-journal/ 下本周 (最近 7 天) 新建或修改的 .md
4. 00-memory/ 最近 7 天是否有改动 (git log --since="7 days ago" -- 00-memory/)
5. 99-inbox/ 当前剩余 paste-*.md 数量

周报模板 (严格遵守):

---
title: $weekId 周报
week: $weekId
created: [今天日期]
tags: [weekly-report]
status: auto-generated
---

# $weekId 周报

## 一句话总结

[本周最重要的一件事, 1 行]

## 活动统计

- 总 commits: N
- 新建文件: N
- 修改文件: N
- 新增目录: (列出, 如果有)
- 00-memory/ 改动: (有/无, 有的话列条目)

## 主题聚类 (本周干了啥)

按主题分组 commits, 每组 2-4 条 bullet. 引用 commit 用反引号.
例: - **PostgREST 深挖**: \`f3d9353\` 追加教学比喻; \`abc1234\` 新增练习

## 我最投入的 3 个话题

基于 04-journal/ 本周条目 + commit 频率推断, 每个话题:
- **话题名**: 1 行为什么上心, 相关文件路径

## 下周值得继续的 1-2 个点

从以下线索挖:
- journal 里 "碎片捕捉" / "待澄清" 段落
- pending-category 标签的 inbox 项 (如果还有)
- 半截没写完的概念卡 (字符 < 300 的 .md)

## 观察 (可选)

1-3 行对自己本周的客观观察 (精力投入倾向 / 跨话题联系 / 偏科信号).

---

写完后严格按 AGENTS.md 协议:
1. 先做 pre-weekly 快照 commit (如果有未提交改动)
2. 写入文件
3. git add + commit, 消息格式:
   notes(weekly): $weekId 周报自动生成
   触发: 每周日定时任务
   影响核心认知: 否
4. 本任务触发源: cron (Windows 任务计划程序, 每周日 21:00)
"@

try {
    & $AGENT_CMD -p --force --trust --workspace $BRAIN_ROOT $prompt *>&1 |
        Out-File $LOG_FILE -Append -Encoding UTF8
}
catch {
    "ERROR: $($_.Exception.Message)" | Out-File $LOG_FILE -Append -Encoding UTF8
}
finally {
    "=== $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) weekly report done [$weekId] ===" |
        Out-File $LOG_FILE -Append -Encoding UTF8
    Remove-Item $LOCK_FILE -Force -ErrorAction SilentlyContinue
}
