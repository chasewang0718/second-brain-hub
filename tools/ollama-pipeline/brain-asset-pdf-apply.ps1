#Requires -Version 5.1
<#
.SYNOPSIS
    把 Ollama 产出的 JSON proposal 落盘: 移 PDF -> Tier B + 写 Tier A 指针卡 + git commit (brain).

.DESCRIPTION
    流程:
        1. 读所有 proposal JSON (跳过 qa-rejected.tsv 里标记为 reject 的)
        2. 对每个 proposal:
            a. 如果 Tier B 目标已有同名文件, 加 -01 后缀
            b. 移 PDF: 99-inbox -> tier_b_dir
            c. 生成 frontmatter + 摘要 Markdown, 写到 D:\brain\<tier_a_dir>\<slug>.md
            d. 写 sha256 + 实际 size
        3. 本轮全部 apply 完, git add/commit to D:\brain (一次 commit)
        4. 成功的 proposal 移到 _migration/ollama-output/applied/
        5. 失败的留在原位置, 记录到 apply-fail.tsv

.PARAMETER ProposalDir
    默认 D:\brain-assets\_migration\ollama-output

.PARAMETER MaxItems
    最多 apply N 份, 默认 0=全部

.PARAMETER DryRun
    预览要做的动作, 不实际改文件

.PARAMETER SkipRejected
    默认 true: 跳过 qa-rejected.tsv 里 verdict=reject 的

.PARAMETER SkipNeedsFix
    默认 false: needs-fix 的也照 apply (因为小错);  true 则也跳

.PARAMETER IncludeLowConf
    默认 false: 跳 confidence < 0.7 的; true 则强制 apply
#>

[CmdletBinding()]
param(
    [string]$ProposalDir = "D:\brain-assets\_migration\ollama-output",
    [int]$MaxItems = 0,
    [switch]$DryRun,
    [bool]$SkipRejected = $true,
    [bool]$SkipNeedsFix = $false,
    [switch]$IncludeLowConf,
    [switch]$NoGitCommit
)

$ErrorActionPreference = 'Stop'

$BRAIN = "D:\brain"
$ASSETS = "D:\brain-assets"

if (-not (Test-Path $ProposalDir)) { throw "proposal 目录不存在: $ProposalDir" }
$appliedDir = Join-Path $ProposalDir "applied"
if (-not (Test-Path $appliedDir) -and -not $DryRun) { New-Item -ItemType Directory -Path $appliedDir -Force | Out-Null }

# 读 QA rejected 表
$rejectedShas = @{}
$qaRej = Join-Path $ProposalDir "qa-rejected.tsv"
if (Test-Path $qaRej) {
    Get-Content $qaRej -Encoding UTF8 | Select-Object -Skip 1 | ForEach-Object {
        $parts = $_ -split "`t"
        if ($parts.Count -ge 4) {
            $rejectedShas[$parts[0]] = $parts[3]  # sha12 -> verdict
        }
    }
}

$applyFailTsv = Join-Path $ProposalDir "apply-fail.tsv"
if (-not (Test-Path $applyFailTsv) -and -not $DryRun) {
    "sha12`tfilename`treason`ttimestamp" | Out-File $applyFailTsv -Encoding UTF8
}

function Get-UniqueSlugPath {
    param([string]$Dir, [string]$Slug, [string]$Ext)
    $p = Join-Path $Dir "$Slug$Ext"
    if (-not (Test-Path $p)) { return @{ Path = $p; Slug = $Slug } }
    for ($n = 2; $n -lt 100; $n++) {
        $candSlug = "$Slug-$('{0:d2}' -f $n)"
        $p = Join-Path $Dir "$candSlug$Ext"
        if (-not (Test-Path $p)) { return @{ Path = $p; Slug = $candSlug } }
    }
    throw "slug 冲突超限: $Slug"
}

function Format-Frontmatter {
    param($c, $ProposalMeta, $ActualSha, $ActualSize, $NewAssetPath, $SourceOrig)
    $size = if ($ActualSize -ge 1MB) { "{0:N2} MB" -f ($ActualSize / 1MB) } elseif ($ActualSize -ge 1KB) { "{0} KB" -f [int]($ActualSize / 1KB) } else { "$ActualSize B" }
    $tagsStr = '[' + (($c.tags | ForEach-Object { $_ }) -join ', ') + ']'
    $lines = @(
        "---"
        "title: $($c.title_zh)"
        "asset_type: pdf"
        "asset_path: $NewAssetPath"
        "asset_size: $size"
        "asset_sha256: $ActualSha"
        "source_original_path: $SourceOrig"
        "created: $(Get-Date -Format 'yyyy-MM-dd')"
        "tags: $tagsStr"
    )
    if ($c.sensitive) { $lines += "sensitive: true" }
    if ($c.page_count) { $lines += "pages: $($c.page_count)" }
    if ($c.language) { $lines += "language: $($c.language)" }
    $lines += "pipeline: ollama-local-v1"
    $lines += "model: $($ProposalMeta.model)"
    $lines += "confidence: $($c.confidence)"
    $lines += "---"
    return $lines -join "`r`n"
}

function Format-CardBody {
    param($c)
    $body = @(
        ""
        "# $($c.title_zh)"
        ""
        "## AI 摘要"
        ""
        $c.summary_zh
        ""
        "## 关键词"
        ""
        ($c.tags -join ', ')
        ""
        "## 我的备注"
        ""
        "（由本地 Qwen2.5 生成, 如需修改请直接编辑此 md）"
    )
    if ($c.related_hints -and $c.related_hints.Count -gt 0) {
        $body += ""
        $body += "## 相关"
        $body += ""
        foreach ($h in $c.related_hints) {
            $body += "- [[$h]]"
        }
    }
    return $body -join "`r`n"
}

# ============================================================
# 主循环
# ============================================================

$proposals = @(Get-ChildItem $ProposalDir -Filter "*.json" -File | Where-Object {
    $_.Name -notmatch '^(qa-|applied)' -and $_.BaseName -ne 'needs-review'
})
Write-Host "Proposal 总数: $($proposals.Count)"

$stats = @{ APPLIED = 0; SKIP_REJECT = 0; SKIP_LOW_CONF = 0; SKIP_NEEDS_FIX = 0; FAIL = 0; SKIP_NO_SOURCE = 0 }
$processed = 0

foreach ($pFile in $proposals) {
    if ($MaxItems -gt 0 -and $processed -ge $MaxItems) { break }
    $processed++

    try {
        $prop = Get-Content $pFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Host "[X] 解析 proposal 失败: $($pFile.Name)" -ForegroundColor Red
        $stats.FAIL++
        continue
    }
    $c = $prop.classification

    # 过滤: rejected
    if ($SkipRejected -and $rejectedShas.ContainsKey($prop.sha12) -and $rejectedShas[$prop.sha12] -eq 'reject') {
        Write-Host "  skip reject: $($prop.source_filename)" -ForegroundColor DarkYellow
        $stats.SKIP_REJECT++
        continue
    }
    if ($SkipNeedsFix -and $rejectedShas.ContainsKey($prop.sha12) -and $rejectedShas[$prop.sha12] -eq 'needs-fix') {
        $stats.SKIP_NEEDS_FIX++
        continue
    }
    # 过滤: 低置信
    if ($c.confidence -lt 0.7 -and -not $IncludeLowConf) {
        $stats.SKIP_LOW_CONF++
        continue
    }

    $src = $prop.source_fullpath
    if (-not (Test-Path $src)) {
        Write-Host "  [X] 源文件不在: $src" -ForegroundColor Red
        if (-not $DryRun) {
            "$($prop.sha12)`t$($prop.source_filename)`tno-source`t$(Get-Date -Format o)" | Add-Content $applyFailTsv -Encoding UTF8
        }
        $stats.SKIP_NO_SOURCE++
        continue
    }

    # 目标路径
    $tierBAbs = Join-Path $ASSETS $c.tier_b_dir
    $tierAAbs = Join-Path $BRAIN $c.tier_a_dir
    if (-not $DryRun) {
        if (-not (Test-Path $tierBAbs)) { New-Item -ItemType Directory -Path $tierBAbs -Force | Out-Null }
        if (-not (Test-Path $tierAAbs)) { New-Item -ItemType Directory -Path $tierAAbs -Force | Out-Null }
    }

    $pdfTarget = Get-UniqueSlugPath -Dir $tierBAbs -Slug $c.slug -Ext ".pdf"
    $mdTarget = Join-Path $tierAAbs "$($pdfTarget.Slug).md"
    if ((Test-Path $mdTarget) -and -not $DryRun) {
        # md 也冲突, 换后缀 (理论上 pdf slug 唯一了 md 也唯一)
        $mdTarget = Join-Path $tierAAbs "$($pdfTarget.Slug)-card.md"
    }

    Write-Host ("-> {0,-18} {1}" -f $c.category, $pdfTarget.Slug) -ForegroundColor Cyan
    Write-Host ("    {0} -> {1}" -f $prop.source_filename, $pdfTarget.Path) -ForegroundColor DarkGray

    if ($DryRun) {
        $stats.APPLIED++
        continue
    }

    # 1. 移 PDF + 算真实 sha256
    try {
        Move-Item -LiteralPath $src -Destination $pdfTarget.Path -ErrorAction Stop
    } catch {
        Write-Host "    [X] 移动失败: $_" -ForegroundColor Red
        "$($prop.sha12)`t$($prop.source_filename)`tmove-fail: $_`t$(Get-Date -Format o)" | Add-Content $applyFailTsv -Encoding UTF8
        $stats.FAIL++
        continue
    }

    $actualHash = (Get-FileHash -Algorithm SHA256 -Path $pdfTarget.Path).Hash.Substring(0, 12).ToLower()
    $actualSize = (Get-Item $pdfTarget.Path).Length

    # 2. 写 md 指针卡
    $fm = Format-Frontmatter -c $c -ProposalMeta $prop -ActualSha $actualHash -ActualSize $actualSize -NewAssetPath $pdfTarget.Path -SourceOrig $src
    $body = Format-CardBody -c $c
    $md = $fm + "`r`n" + $body + "`r`n"
    $md | Out-File -FilePath $mdTarget -Encoding UTF8

    # 3. 把 proposal json 挪到 applied/
    Move-Item -LiteralPath $pFile.FullName -Destination (Join-Path $appliedDir $pFile.Name) -Force

    $stats.APPLIED++
}

Write-Host ""
Write-Host "=== Apply 完成 ===" -ForegroundColor Cyan
Write-Host ("  applied:       {0}" -f $stats.APPLIED)
Write-Host ("  skip reject:   {0}" -f $stats.SKIP_REJECT)
Write-Host ("  skip low-conf: {0}" -f $stats.SKIP_LOW_CONF)
Write-Host ("  skip needs-fix:{0}" -f $stats.SKIP_NEEDS_FIX)
Write-Host ("  skip no source:{0}" -f $stats.SKIP_NO_SOURCE)
Write-Host ("  fail:          {0}" -f $stats.FAIL)

if (-not $DryRun -and -not $NoGitCommit -and $stats.APPLIED -gt 0) {
    Write-Host ""
    Write-Host "Git commit to D:\brain ..." -ForegroundColor Yellow
    Push-Location $BRAIN
    try {
        git add . | Out-Null
        $msg = "ollama-pipeline: apply $($stats.APPLIED) PDF proposals`n`nmodel: $((Get-Content $proposals[0].FullName | ConvertFrom-Json).model)`nlow-conf-skipped: $($stats.SKIP_LOW_CONF)`nrejected-skipped: $($stats.SKIP_REJECT)"
        git commit -m $msg 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  commit OK" -ForegroundColor Green
        } else {
            Write-Host "  commit 失败或无变化" -ForegroundColor DarkYellow
        }
    }
    finally { Pop-Location }
}

Write-Host ""
Write-Host "applied proposals 归档: $appliedDir"
Write-Host "失败列表:             $applyFailTsv"
