#Requires -Version 5.1
<#
.SYNOPSIS
    WeChat 只读巡检任务（不 apply）。

.DESCRIPTION
    固定执行:
      wechat-ingest-preset.ps1 -Mode helper-no-person -RunPostChecks

    作用:
      - preflight dry-run
      - ingest 日志核对
      - 幂等 dry-run 核对
      - A5 eval + 趋势刷新
      - `brain people-render --all` 刷新 06-people/by-person（Obsidian 可读卡）
#>

[CmdletBinding()]
param(
    [string]$PresetScript = 'C:\dev-projects\second-brain-hub\tools\housekeeping\wechat-ingest-preset.ps1'
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path $PresetScript)) {
    Write-Error "找不到 $PresetScript"
    exit 1
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $PresetScript -Mode helper-no-person -RunPostChecks
if ($LASTEXITCODE -ne 0) {
    exit 1
}
exit 0
