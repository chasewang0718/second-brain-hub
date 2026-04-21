#Requires -Version 5.1
<#
.SYNOPSIS
    Phase 2.3 pilot: 选 N 个 PDF, 逐个调 cursor-agent 生成 Tier A 指针卡 + 移 PDF 到 Tier B 目录.

.DESCRIPTION
    - 默认挑 10 个 PDF (3 小 + 4 中 + 3 大), 避开 > 100MB 的怪物
    - 对每个 PDF 单独起一个 cursor-agent session (隔离, 好测 cost)
    - 全程日志 + 结构化 JSON 结果, 方便事后复盘

.PARAMETER Count
    pilot 处理的 PDF 数量. 默认 10.

.PARAMETER MaxSizeMB
    跳过超过这么大的 PDF (避免 1 个占 context 把 pilot 搞崩). 默认 100.

.PARAMETER PdfList
    可选: 直接指定要处理的 PDF 路径列表 (跳过自动挑选).

.PARAMETER SourceDir
    默认 D:\second-brain-assets\99-inbox\

.PARAMETER DryRun
    默认 false. 加 -DryRun 只打印要发送的 prompt, 不真的调 agent.
#>

[CmdletBinding()]
param(
    [int]$Count = 10,
    [int]$MaxSizeMB = 100,
    [string[]]$PdfList,
    [string]$PdfListFile,
    [string]$SourceDir = "D:\second-brain-assets\99-inbox",
    [switch]$DryRun
)

$AGENT_CMD    = "C:\Users\chase\AppData\Local\cursor-agent\agent.cmd"
$BRAIN_ROOT   = "D:\second-brain-content"
$ASSETS_ROOT  = "D:\second-brain-assets"
$PILOT_LOG    = Join-Path $ASSETS_ROOT "_migration\phase2.3-pilot.log"
$PILOT_RESULT = Join-Path $ASSETS_ROOT "_migration\phase2.3-pilot-results.tsv"

if (-not (Test-Path $AGENT_CMD)) {
    Write-Host "❌ cursor-agent CLI 未安装: $AGENT_CMD" -ForegroundColor Red; exit 1
}

# ============================================================
# 选样本
# ============================================================
if ($PdfListFile -and (Test-Path $PdfListFile)) {
    $lines = Get-Content $PdfListFile -Encoding UTF8 | Where-Object { $_.Trim() -ne '' -and -not $_.StartsWith('#') }
    $picked = $lines | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object { Get-Item -LiteralPath $_ }
}
elseif ($PdfList) {
    $picked = $PdfList | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object { Get-Item -LiteralPath $_ }
}
else {
    $all = Get-ChildItem $SourceDir -Filter "*.pdf" -File | Where-Object { $_.Length -le $MaxSizeMB * 1MB }
    $sorted = $all | Sort-Object Length

    $smallCount  = [Math]::Floor($Count * 0.3)
    $largeCount  = [Math]::Floor($Count * 0.3)
    $mediumCount = $Count - $smallCount - $largeCount

    $small  = $sorted | Select-Object -First $smallCount
    $large  = $sorted | Select-Object -Last $largeCount
    $midStart = [int]($sorted.Count / 2 - $mediumCount / 2)
    $medium = $sorted | Select-Object -Skip $midStart -First $mediumCount

    $picked = @($small) + @($medium) + @($large) | Select-Object -Unique
}

if ($picked.Count -eq 0) {
    Write-Host "❌ 没选出样本" -ForegroundColor Red; exit 1
}

Write-Host "`n==== Phase 2.3 Pilot ($($picked.Count) PDFs) ====" -ForegroundColor Cyan
$picked | ForEach-Object {
    $sz = [Math]::Round($_.Length/1KB, 1)
    $unit = "KB"
    if ($sz -gt 1024) { $sz = [Math]::Round($_.Length/1MB, 1); $unit = "MB" }
    "  [{0,6} {1}] {2}" -f $sz, $unit, $_.Name
}

if ($DryRun) {
    Write-Host "`nDry-run, 结束." -ForegroundColor Yellow
    exit 0
}

# ============================================================
# Prompt 模板 (每 PDF 一次调用)
# ============================================================
function Get-Prompt($pdfPath, $sizeMB) {
    # 用简单明确的 prompt, 避免 agent 误解为"背景说明"
    $p = @"
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
- 荷兰 Inburgering -> Tier A: D:\second-brain-content\07-life\education\   Tier B: D:\second-brain-assets\07-life\education\
- 儿童学习 -> Tier A: D:\second-brain-content\07-life\kids-learning\       Tier B: D:\second-brain-assets\07-life\kids-learning\
- 长书/技术 -> Tier A: D:\second-brain-content\01-concepts\books\          Tier B: D:\second-brain-assets\16-books\
- LaTeX项目 -> Tier A: D:\second-brain-content\03-projects\<proj>\        Tier B: D:\second-brain-assets\03-projects\<proj>\
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
3-6 句中文, 说清楚这份 PDF 是关于什么, 核心信息是什么.

## 关键词
- <关键事实1, 便于 brain-ask 搜索>
- <关键事实2>
- ...

## 我的备注
(留空)

第6步: 做完以上 5 步后, 用一行输出总结, 必须以 PILOT-RESULT 开头, tab 分隔, 6 个字段:

PILOT-RESULT<TAB><slug><TAB><指针卡路径 D:\second-brain-content\...><TAB><Tier B 新位置 D:\second-brain-assets\...><TAB><类别><TAB><标题>

示例 (<TAB> 是真实 tab 字符):
PILOT-RESULT	factuur-li-mei-2024-320	D:\second-brain-content\07-life\finance\factuur-li-mei-2024-320.md	D:\second-brain-assets\07-life\finance\factuur-li-mei-2024-320.pdf	发票账单	Li Mei 摄影摄像发票 €320 (2024-09)

严格禁令:
- 不要 git add / commit / push
- 不要处理其他 PDF, 只处理这一份
- 不要改 00-memory/ AGENTS.md .gitignore
- 不要写 log 文件
- 不要问问题, 按协议直接做
"@
    return $p
}

# ============================================================
# 执行
# ============================================================
"=== Phase 2.3 pilot start $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $PILOT_LOG -Encoding UTF8
"pdf_path`tsize_mb`tstatus`telapsed_s`tslug`tcard_path`tnew_asset_path`tcategory`ttitle" | Out-File $PILOT_RESULT -Encoding UTF8

$i = 0
foreach ($pdf in $picked) {
    $i++
    $sizeMB = [Math]::Round($pdf.Length / 1MB, 2)
    Write-Host "`n[$i/$($picked.Count)] " -NoNewline -ForegroundColor Cyan
    Write-Host "$($pdf.Name) " -NoNewline
    Write-Host "(${sizeMB} MB)" -ForegroundColor DarkGray

    "`n=== [$i/$($picked.Count)] $($pdf.FullName) (${sizeMB} MB) ===" | Out-File $PILOT_LOG -Append -Encoding UTF8

    $prompt = Get-Prompt -pdfPath $pdf.FullName -sizeMB $sizeMB
    $startTime = Get-Date
    try {
        $output = & $AGENT_CMD -p --force --trust --workspace $BRAIN_ROOT $prompt 2>&1 | Out-String
        $elapsed = [Math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
        $output | Out-File $PILOT_LOG -Append -Encoding UTF8

        # 解析 PILOT-RESULT 行
        $resultLine = ($output -split "`r?`n") | Where-Object { $_ -match '^PILOT-RESULT' } | Select-Object -Last 1
        if ($resultLine) {
            $parts = $resultLine -split "`t"
            $slug     = if ($parts.Count -gt 1) { $parts[1] } else { "?" }
            $cardPath = if ($parts.Count -gt 2) { $parts[2] } else { "?" }
            $newPath  = if ($parts.Count -gt 3) { $parts[3] } else { "?" }
            $category = if ($parts.Count -gt 4) { $parts[4] } else { "?" }
            $title    = if ($parts.Count -gt 5) { $parts[5] } else { "?" }
            "$($pdf.FullName)`t$sizeMB`tOK`t$elapsed`t$slug`t$cardPath`t$newPath`t$category`t$title" | Out-File $PILOT_RESULT -Append -Encoding UTF8
            Write-Host "    ✅ $elapsed s → $category | $slug" -ForegroundColor Green
        }
        else {
            "$($pdf.FullName)`t$sizeMB`tNO-RESULT-LINE`t$elapsed`t`t`t`t`t" | Out-File $PILOT_RESULT -Append -Encoding UTF8
            Write-Host "    ⚠️  $elapsed s, 没解析到 PILOT-RESULT 行" -ForegroundColor Yellow
        }
    }
    catch {
        $elapsed = [Math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
        "$($pdf.FullName)`t$sizeMB`tERROR`t$elapsed`t`t`t`t`t$($_.Exception.Message)" | Out-File $PILOT_RESULT -Append -Encoding UTF8
        Write-Host "    ❌ $elapsed s, 异常: $($_.Exception.Message)" -ForegroundColor Red
        $_.Exception.Message | Out-File $PILOT_LOG -Append -Encoding UTF8
    }
}

"`n=== Phase 2.3 pilot done $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $PILOT_LOG -Append -Encoding UTF8

Write-Host "`n==== Pilot 完成 ====" -ForegroundColor Cyan
Write-Host "  日志:   $PILOT_LOG" -ForegroundColor DarkGray
Write-Host "  结果:   $PILOT_RESULT" -ForegroundColor DarkGray
