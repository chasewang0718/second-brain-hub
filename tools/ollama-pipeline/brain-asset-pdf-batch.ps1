#Requires -Version 5.1
<#
.SYNOPSIS
    Phase 2.3 批处理 orchestrator: 按 namespace 自动跑完 99-inbox 里所有 PDF.

.DESCRIPTION
    特性:
    - 从 manifest 推断每个 PDF 的原 namespace, 按主题分组 + 大小排序
    - 单线程串行 (cursor-agent CLI 不支持并发)
    - 跳过 > MaxSizeMB 的超大 PDF, 单独列表事后处理
    - 断点续传: 每个 PDF 完成后, 文件会从 99-inbox 移走; 重启时自动跳过已处理的
    - 实时进度写到 batch-progress.tsv, 用来看状况
    - 单 PDF agent 失败时记录后继续下一个 (不中断整个批处理)

.PARAMETER DryRun
    只生成计划, 不调 agent.

.PARAMETER MaxSizeMB
    跳过超过这么大的 PDF. 默认 50 MB.

.PARAMETER MaxPdfs
    限制最多处理几个 (0 = 无限). 用于受控测试.

.PARAMETER SleepSec
    每个 PDF 完成后等待的秒数 (给 Cursor rate limit 喘气). 默认 0.

.PARAMETER OnlyNamespace
    只跑指定 namespace (可多个). 留空 = 所有.

.PARAMETER SourceDir
    默认 D:\second-brain-assets\99-inbox
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [int]$MaxSizeMB = 50,
    [int]$MaxPdfs = 0,
    [int]$SleepSec = 0,
    [string[]]$OnlyNamespace,
    [string]$SourceDir = "D:\second-brain-assets\99-inbox"
)

$AGENT_CMD    = "C:\Users\chase\AppData\Local\cursor-agent\agent.cmd"
$BRAIN_ROOT   = "D:\second-brain-content"
$ASSETS_ROOT  = "D:\second-brain-assets"
$MIGRATION    = Join-Path $ASSETS_ROOT "_migration"
$MANIFEST     = Join-Path $MIGRATION "baidu-2026-04-manifest.tsv"
$PILOT_SCRIPT = Join-Path $PSScriptRoot "brain-asset-pdf-pilot.ps1"
$PROGRESS_TSV = Join-Path $MIGRATION "phase2.3-batch-progress.tsv"
$LARGE_LIST   = Join-Path $MIGRATION "phase2.3-large-pdfs-deferred.txt"
$BATCH_LOG    = Join-Path $MIGRATION "phase2.3-batch.log"

# ============================================================
# 1. 读 manifest, 建立 source_path -> namespace 映射
# ============================================================
if (-not (Test-Path $MANIFEST)) {
    Write-Host "❌ manifest 不存在: $MANIFEST" -ForegroundColor Red; exit 1
}

$nsMap = @{}
$rows = Import-Csv $MANIFEST -Delimiter "`t" -Encoding UTF8 | Where-Object { $_.rule -eq 'pdf' }
foreach ($r in $rows) {
    $sourceName = [System.IO.Path]::GetFileName($r.source_path)
    $parts = $r.source_path.Replace('D:\BaiduSyncdisk\', '') -split '\\'
    $ns = if ($parts.Count -ge 2) { $parts[0..1] -join '\' } else { $parts[0] }
    $nsMap[$sourceName] = $ns
}

# ============================================================
# 2. 扫 99-inbox 现有 PDF, 打 namespace 标签
# ============================================================
$allPdfs = Get-ChildItem $SourceDir -Filter "*.pdf" -File
Write-Host "`n99-inbox 现存 PDF: $($allPdfs.Count)" -ForegroundColor Cyan

$tagged = foreach ($f in $allPdfs) {
    $ns = if ($nsMap.ContainsKey($f.Name)) { $nsMap[$f.Name] } else { 'unknown' }
    [PSCustomObject]@{
        File      = $f
        Namespace = $ns
        SizeMB    = [Math]::Round($f.Length / 1MB, 2)
    }
}

# ============================================================
# 3. 划分: 小 PDF 进入主队列, 大 PDF 进 large-list
# ============================================================
$mainQueue  = $tagged | Where-Object { $_.SizeMB -le $MaxSizeMB }
$deferred   = $tagged | Where-Object { $_.SizeMB -gt $MaxSizeMB }

if ($deferred) {
    $deferred.File.FullName | Out-File $LARGE_LIST -Encoding UTF8
    Write-Host "⚠️  跳过 $($deferred.Count) 个 > ${MaxSizeMB}MB PDF, 写入 $LARGE_LIST" -ForegroundColor Yellow
}

# 过滤 namespace
if ($OnlyNamespace) {
    $mainQueue = $mainQueue | Where-Object { $OnlyNamespace -contains $_.Namespace }
    Write-Host "只跑 namespace: $($OnlyNamespace -join ', ')" -ForegroundColor Cyan
}

# ============================================================
# 4. 按 namespace 排序 (主题统一的先)
# ============================================================
$nsPriority = @{
    'Document\Document.Factuur'      = 10
    'Document\Document.个人信息'     = 20
    'Document\Document.Inburgering'  = 30
    'Document\Document.House'        = 40
    'Document\Document.公司信息'     = 50
    '绘本写作书籍'                   = 60
    'Document\Document.儿童学习'     = 70
    'Projects\project.latex'         = 80
    'Projects\work_01'               = 90
    'Projects\Latex.templates'       = 100
    'Projects\Latex.Lezenoefeningen' = 110
    'Projects\Latex.双语朗读'        = 120
    'Projects\Latex.Nederlands'      = 130
}

$sorted = $mainQueue | Sort-Object `
    @{Expression={ if ($nsPriority.ContainsKey($_.Namespace)) { $nsPriority[$_.Namespace] } else { 999 } }}, `
    @{Expression='Namespace'}, `
    @{Expression='SizeMB'}

if ($MaxPdfs -gt 0) { $sorted = $sorted | Select-Object -First $MaxPdfs }

# ============================================================
# 5. 打印计划 + 确认
# ============================================================
Write-Host "`n==== 批处理计划 ====" -ForegroundColor Cyan
$nsStats = $sorted | Group-Object Namespace | Sort-Object @{Expression={ if ($nsPriority.ContainsKey($_.Name)) { $nsPriority[$_.Name] } else { 999 } }}
foreach ($g in $nsStats) {
    $total = [Math]::Round(($g.Group.SizeMB | Measure-Object -Sum).Sum, 1)
    "  {0,4} × {1,-40}  ({2} MB)" -f $g.Count, $g.Name, $total
}
Write-Host "`n合计: $($sorted.Count) PDFs" -ForegroundColor Green
Write-Host "预计耗时: $([Math]::Round($sorted.Count * 66 / 3600, 1)) 小时 (按平均 66s/PDF)" -ForegroundColor DarkGray

if ($DryRun) {
    Write-Host "`n[DRY-RUN] 退出." -ForegroundColor Yellow
    exit 0
}

# ============================================================
# 6. 初始化进度 TSV
# ============================================================
if (-not (Test-Path $PROGRESS_TSV)) {
    "idx`tnamespace`tfile`tsize_mb`tstatus`telapsed_s`ttimestamp" | Out-File $PROGRESS_TSV -Encoding UTF8
}
"=== batch start $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') / total=$($sorted.Count) ===" | Out-File $BATCH_LOG -Append -Encoding UTF8

# ============================================================
# 7. 主循环: 逐个调 agent
# ============================================================
function Get-BatchPrompt($pdfPath, $sizeMB) {
@"
任务: 归档这份 PDF -> $pdfPath (大小 $sizeMB MB)

这份 PDF 已经在 D:\second-brain-assets\99-inbox\ 下, 来自 Phase 2.2 百度云批量迁移. 现在让你读它然后把它归档.

请依次做 5 步, 不要问我任何问题, 不要写长篇介绍, 直接做:

第1步: 打开读这份 PDF: $pdfPath

第2步: 决定它该归到哪个类别 (参考下表):
- 发票账单 -> Tier A: D:\second-brain-content\07-life\finance\    Tier B: D:\second-brain-assets\07-life\finance\
- 医疗健康 -> Tier A: D:\second-brain-content\07-life\health\     Tier B: D:\second-brain-assets\07-life\health\
- 证件身份 -> Tier A: D:\second-brain-content\07-life\identity\   Tier B: D:\second-brain-assets\07-life\identity\
- 房屋合同 -> Tier A: D:\second-brain-content\07-life\housing\    Tier B: D:\second-brain-assets\07-life\housing\
- 公司税务 -> Tier A: D:\second-brain-content\07-life\business\   Tier B: D:\second-brain-assets\07-life\business\
- 荷兰 Inburgering -> Tier A: D:\second-brain-content\07-life\dutch-inburgering\  Tier B: D:\second-brain-assets\07-life\dutch-inburgering\
- 儿童学习 -> Tier A: D:\second-brain-content\07-life\kids-learning\              Tier B: D:\second-brain-assets\07-life\kids-learning\
- 长书/技术 -> Tier A: D:\second-brain-content\01-concepts\books\                 Tier B: D:\second-brain-assets\16-books\
- LaTeX项目 -> Tier A: D:\second-brain-content\03-projects\<proj>\                Tier B: D:\second-brain-assets\03-projects\<proj>\
- 绘本写作 -> Tier A: D:\second-brain-content\01-concepts\picture-books\          Tier B: D:\second-brain-assets\16-books\picture-books\
- 其他 -> 按内容建新目录 (内容驱动结构, 你有 L1 权限)

第3步: 生成 kebab-case slug (全英文/拼音, 不要空格或中文)

第4步: 把 PDF 移动 (不是 copy) 到对应的 Tier B 位置, 改名为 <slug>.pdf. 若目录不存在就建, 若重名就加 -YYYYMMDD 后缀.

第5步: 在对应的 Tier A 目录下新建 <slug>.md, 内容按这个模板:

---
title: <人类可读标题>
asset_type: pdf
asset_path: <Tier B 移动后的新绝对路径>
asset_size: $sizeMB MB
asset_original_source: $pdfPath
created: 2026-04-19
tags: [<3-6个kebab-case标签>]
---

# <标题>

## AI 摘要
3-6 句中文, 说清楚这份 PDF 是关于什么, 核心信息.

## 关键词
- <关键事实1, 便于 brain-ask 搜索>
- <关键事实2>

## 我的备注
(留空)

严格禁令:
- 不要 git push (git commit 可以, 粒度细方便回滚)
- 不要处理其他 PDF, 只处理这一份
- 不要改 00-memory/ AGENTS.md .gitignore
- 如果内容涉及个人隐私/金额/账号, frontmatter 加 ``sensitive: true``, 且摘要里不写具体数字
- 不要问问题, 按协议直接做
"@
}

$idx = 0
$stats = @{ ok = 0; fail = 0; skip = 0 }
$consecutiveFails = 0
$CIRCUIT_BREAKER_LIMIT = 5

foreach ($item in $sorted) {
    $idx++
    $pdf = $item.File

    # 断点续传: 文件可能已被之前轮次处理掉
    if (-not (Test-Path -LiteralPath $pdf.FullName)) {
        $stats.skip++
        "$idx`t$($item.Namespace)`t$($pdf.Name)`t$($item.SizeMB)`tALREADY-GONE`t0`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $PROGRESS_TSV -Append -Encoding UTF8
        continue
    }

    Write-Host ("`n[{0}/{1}] [{2}] {3} ({4} MB)" -f $idx, $sorted.Count, $item.Namespace, $pdf.Name, $item.SizeMB) -ForegroundColor Cyan

    $prompt = Get-BatchPrompt -pdfPath $pdf.FullName -sizeMB $item.SizeMB
    $startTime = Get-Date
    try {
        $output = & $AGENT_CMD -p --force --trust --workspace $BRAIN_ROOT $prompt 2>&1 | Out-String
        $elapsed = [Math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)

        # 判断是否真处理了: 检查原文件是否消失 (被 agent 移走)
        $stillExists = Test-Path -LiteralPath $pdf.FullName
        if ($stillExists) {
            $status = "PROCESSED-BUT-FILE-KEPT"
            $stats.fail++
            $consecutiveFails++
            Write-Host "    ⚠️  $elapsed s — file 没被 agent 移走 (可能失败)" -ForegroundColor Yellow
        } else {
            $status = "OK"
            $stats.ok++
            $consecutiveFails = 0
            Write-Host "    ✅ $elapsed s" -ForegroundColor Green
        }

        "$idx`t$($item.Namespace)`t$($pdf.Name)`t$($item.SizeMB)`t$status`t$elapsed`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $PROGRESS_TSV -Append -Encoding UTF8

        # 保存 agent 回复到详细日志
        "=== [$idx/$($sorted.Count)] $($pdf.Name) [$status, ${elapsed}s] ===" | Out-File $BATCH_LOG -Append -Encoding UTF8
        $output | Out-File $BATCH_LOG -Append -Encoding UTF8
    }
    catch {
        $elapsed = [Math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
        $stats.fail++
        $consecutiveFails++
        "$idx`t$($item.Namespace)`t$($pdf.Name)`t$($item.SizeMB)`tEXCEPTION`t$elapsed`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $PROGRESS_TSV -Append -Encoding UTF8
        "EXCEPTION on $($pdf.Name): $($_.Exception.Message)" | Out-File $BATCH_LOG -Append -Encoding UTF8
        Write-Host "    ❌ $elapsed s — $($_.Exception.Message)" -ForegroundColor Red
    }

    if ($consecutiveFails -ge $CIRCUIT_BREAKER_LIMIT) {
        "CIRCUIT-BREAKER: 连续 $consecutiveFails 个失败, halt. 用户 review 后手动 resume (重跑即可, 已处理的会跳过)." | Out-File $BATCH_LOG -Append -Encoding UTF8
        Write-Host "`n🚨 连续 $consecutiveFails 个失败, 熔断. 可能 rate limit 或 agent 挂了. 重跑脚本会从断点继续." -ForegroundColor Red
        break
    }

    if ($SleepSec -gt 0) { Start-Sleep -Seconds $SleepSec }

    # 每 20 个 PDF 给一个 milestone 输出
    if ($idx % 20 -eq 0) {
        Write-Host ("`n--- 里程碑: {0}/{1} | OK={2} FAIL={3} SKIP={4} | 99-inbox 剩余 {5} ---`n" -f `
            $idx, $sorted.Count, $stats.ok, $stats.fail, $stats.skip, `
            (Get-ChildItem $SourceDir -Filter "*.pdf").Count) -ForegroundColor Magenta
    }
}

"=== batch done $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') / OK=$($stats.ok) FAIL=$($stats.fail) SKIP=$($stats.skip) ===" | Out-File $BATCH_LOG -Append -Encoding UTF8

Write-Host "`n==== 批处理完成 ====" -ForegroundColor Cyan
Write-Host ("  OK:   {0}" -f $stats.ok) -ForegroundColor Green
Write-Host ("  FAIL: {0}" -f $stats.fail) -ForegroundColor Red
Write-Host ("  SKIP: {0} (已在之前轮次处理)" -f $stats.skip) -ForegroundColor DarkGray
Write-Host "  99-inbox 剩余: $((Get-ChildItem $SourceDir -Filter '*.pdf').Count)" -ForegroundColor Yellow
Write-Host "  大 PDF (>${MaxSizeMB}MB) 列表: $LARGE_LIST" -ForegroundColor DarkGray
Write-Host "  进度 TSV: $PROGRESS_TSV" -ForegroundColor DarkGray
