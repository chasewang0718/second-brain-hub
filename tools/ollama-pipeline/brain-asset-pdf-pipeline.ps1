#Requires -Version 5.1
<#
.SYNOPSIS
    PDF 本地分类 pipeline 三步一条龙: worker -> QA -> apply.

.DESCRIPTION
    模式:
        -Smoke      : 3 份, 不写盘 (检查 Ollama 通不通)
        -Pilot      : 10 份, 写 proposal + QA 抽查 + 人工 review 前暂停
        -Production : 全部, worker -> QA 抽查 (15%) -> 通过则 apply 高置信, 低置信留人工
#>

[CmdletBinding()]
param(
    [switch]$Smoke,
    [switch]$Pilot,
    [switch]$Production,
    [int]$MaxItems = 0,
    [string]$Model = "qwen2.5:14b-instruct"
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$worker = Join-Path $root "brain-asset-pdf-local.ps1"
$qa = Join-Path $root "brain-asset-pdf-qa.ps1"
$apply = Join-Path $root "brain-asset-pdf-apply.ps1"

if (-not $Smoke -and -not $Pilot -and -not $Production) {
    Write-Host "请指定模式: -Smoke | -Pilot | -Production" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  -Smoke       : 3 份干跑 (不写盘), 验证 Ollama + pdftotext 链路"
    Write-Host "  -Pilot       : 10 份 (默认) 全流程, 停在 apply 前等人 review"
    Write-Host "  -Production  : 全部 (或 -MaxItems N), 自动 apply 高置信, 低置信进待审池"
    exit 0
}

if ($Smoke) {
    Write-Host "=== SMOKE (3 份 dry-run) ===" -ForegroundColor Cyan
    & $worker -MaxItems 3 -DryRun -Model $Model
    exit $LASTEXITCODE
}

if ($Pilot) {
    $n = if ($MaxItems -gt 0) { $MaxItems } else { 10 }
    Write-Host "=== PILOT ($n 份) ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[1/3] Worker: 跑 $n 份生成 proposal ..." -ForegroundColor Yellow
    & $worker -Model $Model -MaxItems $n
    if ($LASTEXITCODE -ne 0) { Write-Host "worker 失败"; exit 1 }
    Write-Host ""
    Write-Host "[2/3] QA: 全部抽查 ..." -ForegroundColor Yellow
    & $qa -SamplePercent 100 -MaxItems $n
    Write-Host ""
    Write-Host "[3/3] 暂停: 请 review QA report, 满意后手动跑:" -ForegroundColor Green
    Write-Host "      & `"$apply`""
    exit 0
}

if ($Production) {
    Write-Host "=== PRODUCTION ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[1/3] Worker: 跑全部 inbox PDF ..." -ForegroundColor Yellow
    if ($MaxItems -gt 0) {
        & $worker -Model $Model -MaxItems $MaxItems
    } else {
        & $worker -Model $Model
    }
    if ($LASTEXITCODE -ne 0) { Write-Host "worker 失败"; exit 1 }
    Write-Host ""
    Write-Host "[2/3] QA 抽查 15% + 高风险类全抽 ..." -ForegroundColor Yellow
    & $qa -SamplePercent 15
    Write-Host ""
    Write-Host "[3/3] Apply (跳 reject + 低置信, 含 needs-fix) ..." -ForegroundColor Yellow
    & $apply
    Write-Host ""
    Write-Host "完成. 低置信/rejected 留在 ollama-output/, 可后续人工审。" -ForegroundColor Green
}
