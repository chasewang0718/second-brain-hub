#Requires -Version 5.1
<#
.SYNOPSIS
    QA 抽查: 从本地 Ollama 产出的 JSON proposals 里随机抽, 调 cursor-agent 做质检员打分.

.DESCRIPTION
    抽查策略 (默认):
        - 随机抽 N% (默认 15%)
        - 低置信 (<0.7) 的 100% 抽
        - 重点类型 (tax, identity, housing) 100% 抽
        - 其他按比例抽
    每份交给 cursor-agent 看 {原 PDF 文件名 + proposal JSON + 真实 pdftotext 文本前 2000 字}, 回一个评分 JSON:
        {
          "verdict": "ok|needs-fix|reject",
          "issues": ["category-wrong", "slug-collision", ...],
          "suggested_fix": { ... 局部修正字段 ... },
          "notes": "简短评语"
        }
    所有 QA 结果写到 _migration/ollama-output/qa-report-YYYY-MM-DD.md, 失败的进 qa-rejected.tsv.

.PARAMETER ProposalDir
    _migration/ollama-output 目录

.PARAMETER SamplePercent
    常规抽查比例, 默认 15

.PARAMETER AuditorCmd
    调用 cursor-agent 的命令, 默认 "cursor-agent"

.PARAMETER MaxItems
    最多抽查 N 份, 默认 0=不限

.EXAMPLE
    # 默认 15% 抽查
    .\brain-asset-pdf-qa.ps1

.EXAMPLE
    # 抽 20 份做 pilot QA
    .\brain-asset-pdf-qa.ps1 -MaxItems 20
#>

[CmdletBinding()]
param(
    [string]$ProposalDir = "D:\brain-assets\_migration\ollama-output",
    [int]$SamplePercent = 15,
    [string]$AuditorCmd = "cursor-agent",
    [int]$MaxItems = 0,
    [switch]$SkipLowConfAll,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# ============================================================
# 前置
# ============================================================

if (-not (Test-Path $ProposalDir)) { throw "proposal 目录不存在: $ProposalDir" }

try {
    $null = & $AuditorCmd --version 2>$null
} catch {
    Write-Host "[X]  找不到 $AuditorCmd, 默认 QA 会跳过; 可指定 -AuditorCmd" -ForegroundColor Red
    exit 1
}

$highRiskCats = @("tax","identity","housing","medical","contract","bank-statement")

$allJson = Get-ChildItem $ProposalDir -Filter "*.json" -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '^qa-' -and $_.BaseName -ne 'needs-review' }
Write-Host "Proposal 总数: $($allJson.Count)"

# 分层抽样
$proposals = @()
foreach ($f in $allJson) {
    try {
        $p = Get-Content $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $proposals += [PSCustomObject]@{ File = $f; Data = $p }
    } catch {
        Write-Host "  [X] 解析失败: $($f.Name)" -ForegroundColor Red
    }
}

$toAudit = [System.Collections.ArrayList]@()
foreach ($p in $proposals) {
    $reason = $null
    if ($p.Data.classification.confidence -lt 0.7 -and -not $SkipLowConfAll) {
        $reason = "low-confidence"
    } elseif ($highRiskCats -contains $p.Data.classification.category) {
        $reason = "high-risk-category"
    } elseif ((Get-Random -Minimum 0 -Maximum 100) -lt $SamplePercent) {
        $reason = "random-sample"
    }
    if ($reason) { [void]$toAudit.Add([PSCustomObject]@{ Proposal = $p; Reason = $reason }) }
}
if ($MaxItems -gt 0 -and $toAudit.Count -gt $MaxItems) {
    $toAudit = $toAudit | Select-Object -First $MaxItems
}

Write-Host "将 QA 抽查 $($toAudit.Count) 份"
Write-Host ""
if ($DryRun) {
    $toAudit | ForEach-Object {
        Write-Host ("  {0,-20}  {1}  ({2})" -f $_.Reason, $_.Proposal.Data.sha12, $_.Proposal.Data.source_filename)
    }
    Write-Host ""
    Write-Host "(DryRun, 不调 agent)"
    exit 0
}

$today = Get-Date -Format "yyyy-MM-dd"
$reportMd = Join-Path $ProposalDir "qa-report-$today.md"
$rejectedTsv = Join-Path $ProposalDir "qa-rejected.tsv"
if (-not (Test-Path $rejectedTsv)) {
    "sha12`tfilename`tcategory`tverdict`tissues`ttimestamp" | Out-File $rejectedTsv -Encoding UTF8
}

$mdLines = [System.Collections.ArrayList]@()
[void]$mdLines.Add("---")
[void]$mdLines.Add("title: QA Report — 本地 Ollama PDF 分类抽查 $today")
[void]$mdLines.Add("generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
[void]$mdLines.Add("total_proposals: $($proposals.Count)")
[void]$mdLines.Add("audited: $($toAudit.Count)")
[void]$mdLines.Add("---")
[void]$mdLines.Add("")
[void]$mdLines.Add("# QA Report — 本地 Ollama PDF 分类抽查")
[void]$mdLines.Add("")

$verdictCount = @{ ok = 0; "needs-fix" = 0; reject = 0; "audit-fail" = 0 }
$i = 0
foreach ($item in $toAudit) {
    $i++
    $p = $item.Proposal
    $pdfPath = $p.Data.source_fullpath
    if (-not (Test-Path $pdfPath)) {
        Write-Host "[$i/$($toAudit.Count)] 源文件不在: $pdfPath" -ForegroundColor Red
        continue
    }

    # 抽实际 pdftotext 文本 (4000 字) 给 auditor 看
    $tmp = [System.IO.Path]::GetTempFileName()
    & pdftotext -l 8 -layout $pdfPath $tmp 2>$null
    $realText = Get-Content $tmp -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    Remove-Item $tmp -ErrorAction SilentlyContinue
    if (-not $realText) { $realText = "(pdftotext 抽不到文本)" }
    if ($realText.Length -gt 3000) { $realText = $realText.Substring(0, 3000) }

    $proposalJson = $p.Data.classification | ConvertTo-Json -Depth 10 -Compress

    $auditorPrompt = @"
你是「Chase 的第二大脑」PDF 分类的质检员 (auditor)。

下面是本地 Qwen2.5 模型生成的一份 PDF 分类 proposal, 以及对应 PDF 的实际文本抽样。
请评估 proposal 是否合格, 输出**严格 JSON** (无 markdown):

{
  "verdict": "ok | needs-fix | reject",
  "issues": ["category-wrong", "slug-collision", "summary-inaccurate", "sensitive-miss", "tier-path-wrong", ...],
  "suggested_fix": {
    // 只列需要改的字段, 不改的不写
    "category": "...",
    "summary_zh": "...",
    ...
  },
  "notes": "1-2 句评语"
}

评分标准:
- verdict=ok  : category + slug + 隐私判断都对, 摘要基本准确
- verdict=needs-fix : 有小错 (slug/tags/少一条隐私 flag), 但大方向对
- verdict=reject : category 错了, 或摘要严重偏离, 或隐私漏标

--- proposal JSON ---
$proposalJson

--- 真实 PDF 文件名 ---
$($p.Data.source_filename)

--- pdftotext 实际抽到文本 (前 3000 字) ---
$realText

只输出一个 JSON 对象。
"@

    Write-Host "[$i/$($toAudit.Count)] $($p.Data.sha12) -> $($p.Data.classification.category) ... " -NoNewline
    $t0 = Get-Date
    $audPrompt = $auditorPrompt -replace '"', '\"'
    try {
        $audResp = & $AuditorCmd --print --output-format=json -p "$audPrompt" 2>$null
        if ($LASTEXITCODE -ne 0) { throw "cursor-agent exit $LASTEXITCODE" }
    } catch {
        Write-Host "audit-fail ($_)" -ForegroundColor Red
        $verdictCount."audit-fail"++
        continue
    }
    $ms = [int]((Get-Date) - $t0).TotalMilliseconds

    # audResp 是 cursor-agent --output-format=json 包装后的, 里面 .result 字段是真实回答
    try {
        $agentOut = $audResp | ConvertFrom-Json
        $innerJsonText = $agentOut.result
        # 尝试提取 JSON 对象 (有时 agent 会加文字前缀)
        if ($innerJsonText -match '(?s)\{.*\}') { $innerJsonText = $Matches[0] }
        $verdict = $innerJsonText | ConvertFrom-Json
    } catch {
        Write-Host "parse-fail" -ForegroundColor Red
        $verdictCount."audit-fail"++
        continue
    }

    Write-Host ("{0} ({1}ms)" -f $verdict.verdict, $ms) -ForegroundColor $(switch ($verdict.verdict) { "ok" {"Green"}; "needs-fix" {"Yellow"}; default {"Red"} })

    $verdictCount[$verdict.verdict]++

    [void]$mdLines.Add("## [$i] $($p.Data.source_filename)")
    [void]$mdLines.Add("")
    [void]$mdLines.Add("- **sha12**: ``$($p.Data.sha12)``")
    [void]$mdLines.Add("- **reason**: $($item.Reason)")
    [void]$mdLines.Add("- **category**: $($p.Data.classification.category)  |  **slug**: ``$($p.Data.classification.slug)``")
    [void]$mdLines.Add("- **confidence**: $($p.Data.classification.confidence)")
    [void]$mdLines.Add("- **verdict**: **$($verdict.verdict)**")
    if ($verdict.issues) { [void]$mdLines.Add("- **issues**: $(($verdict.issues) -join ', ')") }
    if ($verdict.notes) { [void]$mdLines.Add("- **notes**: $($verdict.notes)") }
    if ($verdict.suggested_fix) {
        [void]$mdLines.Add("- **suggested_fix**:")
        [void]$mdLines.Add("  ``````json")
        [void]$mdLines.Add("  $($verdict.suggested_fix | ConvertTo-Json -Depth 10 -Compress)")
        [void]$mdLines.Add("  ``````")
    }
    [void]$mdLines.Add("")

    if ($verdict.verdict -eq "reject" -or $verdict.verdict -eq "needs-fix") {
        $issueStr = if ($verdict.issues) { ($verdict.issues) -join ',' } else { '' }
        "$($p.Data.sha12)`t$($p.Data.source_filename)`t$($p.Data.classification.category)`t$($verdict.verdict)`t$issueStr`t$(Get-Date -Format o)" | Add-Content $rejectedTsv -Encoding UTF8
    }
}

# 写 report 头部统计
$totAudited = $toAudit.Count
$okPct = if ($totAudited -gt 0) { [Math]::Round(100 * $verdictCount.ok / $totAudited, 1) } else { 0 }

$summary = @(
    "## 总览",
    "",
    "- 总 proposal: **$($proposals.Count)**",
    "- 抽查: **$totAudited**",
    "- ok: **$($verdictCount.ok)** ($okPct%)",
    "- needs-fix: $($verdictCount."needs-fix")",
    "- reject: $($verdictCount.reject)",
    "- audit-fail: $($verdictCount."audit-fail")",
    "",
    "## 判断",
    ""
)
if ($okPct -ge 90) {
    $summary += "- [OK] **通过率 $okPct% >= 90%**: 可以 apply 全部 proposal"
} elseif ($okPct -ge 75) {
    $summary += "- [!]️ **通过率 $okPct%**: 建议先修 needs-fix, reject 的人工复查"
} else {
    $summary += "- [X] **通过率 $okPct% < 75%**: 不建议 apply, 调整 prompt/few-shot 后重跑"
}
$summary += ""

$finalMd = $mdLines[0..5] + $summary + $mdLines[6..($mdLines.Count - 1)]
$finalMd -join "`r`n" | Out-File $reportMd -Encoding UTF8

Write-Host ""
Write-Host "=== QA 完成 ===" -ForegroundColor Cyan
Write-Host "  ok:           $($verdictCount.ok) ($okPct%)"
Write-Host "  needs-fix:    $($verdictCount."needs-fix")"
Write-Host "  reject:       $($verdictCount.reject)"
Write-Host "  audit-fail:   $($verdictCount."audit-fail")"
Write-Host ""
Write-Host "Report: $reportMd"
Write-Host "Rejected list: $rejectedTsv"
