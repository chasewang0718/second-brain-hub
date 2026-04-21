#Requires -Version 5.1
<#
.SYNOPSIS
    从 _escalation/*.processed.json 提炼 few-shot 候选.

.DESCRIPTION
    作用:
      - 扫描已处理的 escalation 结果
      - 把每条转成 few-shot 候选 JSON
      - 输出到 prompts/few-shot/pdf/harvested/

    默认 DryRun: 只打印将生成多少条, 不写文件.
#>

[CmdletBinding()]
param(
    [string]$EscalationDir = "",
    [string]$DestDir = "",
    [int]$MaxItems = 0,
    [switch]$DryRun = $true
)

$ErrorActionPreference = "Stop"

$HUB_ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)  # second-brain-hub/
$configLoader = Join-Path $HUB_ROOT "tools\lib\config-loader.ps1"
if (Test-Path $configLoader) {
    . $configLoader
}

function Get-ConfigOrDefault {
    param(
        [string]$File,
        [string]$Key,
        $DefaultValue
    )
    if (Get-Command Get-BrainConfig -ErrorAction SilentlyContinue) {
        try { return (Get-BrainConfig -File $File -Key $Key) } catch {}
    }
    return $DefaultValue
}

if ([string]::IsNullOrWhiteSpace($EscalationDir)) {
    $EscalationDir = Get-ConfigOrDefault -File "paths" -Key "paths.escalation_dir" -DefaultValue "D:\second-brain-assets\_escalation"
}
if ([string]::IsNullOrWhiteSpace($DestDir)) {
    $DestDir = Join-Path $HUB_ROOT "prompts\few-shot\pdf\harvested"
}

if (-not (Test-Path $EscalationDir)) {
    Write-Host "[!] escalation 目录不存在: $EscalationDir" -ForegroundColor Yellow
    exit 0
}

$files = @(Get-ChildItem -Path $EscalationDir -Filter "*.processed.json" -File -ErrorAction SilentlyContinue)
if ($MaxItems -gt 0) {
    $files = $files | Select-Object -First $MaxItems
}

Write-Host "找到 processed 文件: $($files.Count)" -ForegroundColor Cyan
if ($files.Count -eq 0) {
    Write-Host "没有可 harvest 的输入, 退出." -ForegroundColor Yellow
    exit 0
}

if (-not $DryRun -and -not (Test-Path $DestDir)) {
    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
}

$ok = 0
$skip = 0
$fail = 0

foreach ($f in $files) {
    try {
        $obj = Get-Content -Path $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json

        # 兼容不同结构:
        # 1) cloud 输出标准: { input: {...}, output: {...} }
        # 2) 直接补全字段: { user_input: "...", expected_output: {...} }
        # 3) 兜底: 从 local_attempt/raw_output 组一个弱样本
        $userInput = $null
        $expectedOutput = $null

        if ($obj.user_input -and $obj.expected_output) {
            $userInput = $obj.user_input
            $expectedOutput = $obj.expected_output
        } elseif ($obj.input -and $obj.output) {
            $userInput = ($obj.input | ConvertTo-Json -Depth 8 -Compress)
            $expectedOutput = $obj.output
        } elseif ($obj.local_attempt -and $obj.local_attempt.raw_output) {
            $userInput = "source_file=$($obj.source_file); source_hash=$($obj.source_hash); reason=$($obj.reason)"
            try {
                $expectedOutput = ($obj.local_attempt.raw_output | ConvertFrom-Json -ErrorAction Stop)
            } catch {
                $skip++
                continue
            }
        } else {
            $skip++
            continue
        }

        $candidate = [ordered]@{
            user_input      = $userInput
            expected_output = $expectedOutput
            metadata        = @{
                source_file = $f.Name
                source_path = $f.FullName
                harvested_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                task = "pdf-classify"
            }
        }

        $base = [System.IO.Path]::GetFileNameWithoutExtension($f.Name).Replace(".processed", "")
        $outName = "{0}-fewshot.json" -f $base
        $outPath = Join-Path $DestDir $outName

        if ($DryRun) {
            Write-Host ("DRYRUN -> {0}" -f $outPath) -ForegroundColor DarkGray
            $ok++
            continue
        }

        $candidate | ConvertTo-Json -Depth 12 | Out-File -FilePath $outPath -Encoding UTF8
        $ok++
    } catch {
        Write-Host ("[X] 失败: {0} ({1})" -f $f.Name, $_.Exception.Message) -ForegroundColor Red
        $fail++
    }
}

Write-Host ""
Write-Host "=== harvest 完成 ===" -ForegroundColor Cyan
Write-Host ("  ok:   {0}" -f $ok)
Write-Host ("  skip: {0}" -f $skip)
Write-Host ("  fail: {0}" -f $fail)
Write-Host ("  dryrun: {0}" -f $DryRun)
if (-not $DryRun) {
    Write-Host ("  output: {0}" -f $DestDir)
}

