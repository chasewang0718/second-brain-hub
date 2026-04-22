#Requires -Version 5.1
<#
.SYNOPSIS
    WeChat ingest 预设执行器（含 helper 会话策略）。

.DESCRIPTION
    预设模式:
      - default: 与当前 CLI 默认一致（不包含 helper 会话）
      - helper-no-person: 包含 helper 会话，但不绑定到 person
      - helper-link-person: 包含 helper 会话，并绑定到 person
      - helper-blacklist: 包含 helper 会话扫描，但显式黑名单 filehelper

    apply 模式会先执行:
      brain ingest-backup-now --label <auto>
#>

[CmdletBinding()]
param(
    [ValidateSet('default', 'helper-no-person', 'helper-link-person', 'helper-blacklist')]
    [string]$Mode = 'default',
    [switch]$Apply,
    [switch]$SkipPreflightDryRun,
    [int]$MaxWouldInsert = 200,
    [string]$DecoderDir = 'C:\dev-projects\wechat-decoder',
    [string]$Since = '',
    [string]$PythonExe = 'C:\dev-projects\second-brain-hub\tools\py\.venv\Scripts\python.exe',
    [string]$BrainRepo = 'C:\dev-projects\second-brain-hub\tools\py',
    [string[]]$ExtraWhitelist = @(),
    [switch]$RunPostChecks
)

$ErrorActionPreference = 'Stop'

function Invoke-Brain {
    param([string[]]$CliArgs)
    Push-Location $BrainRepo
    try {
        & $PythonExe -m brain_cli.main @CliArgs
        if ($LASTEXITCODE -ne 0) {
            throw "brain command failed: $($CliArgs -join ' ')"
        }
    } finally {
        Pop-Location
    }
}

function Invoke-BrainCapture {
    param([string[]]$CliArgs)
    Push-Location $BrainRepo
    try {
        $raw = & $PythonExe -m brain_cli.main @CliArgs 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            throw "brain command failed: $($CliArgs -join ' ')`n$raw"
        }
        return $raw
    } finally {
        Pop-Location
    }
}

function Invoke-PostChecks {
    param([string]$SelectedMode)
    Write-Host "Running post-checks..." -ForegroundColor Cyan
    $days = "2"
    $logRaw = Invoke-BrainCapture -CliArgs @('ingest-log-recent', '--source', 'wechat', '--days', $days, '--limit', '5')
    Write-Output $logRaw.Trim()

    $dryRunArgs = @('wechat-sync', '--decoder-dir', $DecoderDir, '--dry-run')
    if ($Since.Trim()) {
        $dryRunArgs += @('--since', $Since.Trim())
    }
    switch ($SelectedMode) {
        'helper-no-person' {
            $dryRunArgs += @('--include-helper-chats', '--chat-whitelist', 'filehelper', '--helper-chat-mode', 'no-person')
        }
        'helper-link-person' {
            $dryRunArgs += @('--include-helper-chats', '--chat-whitelist', 'filehelper', '--helper-chat-mode', 'link-person')
        }
        'helper-blacklist' {
            $dryRunArgs += @('--include-helper-chats', '--chat-blacklist', 'filehelper')
        }
    }
    foreach ($cid in @($ExtraWhitelist)) {
        if ($cid -and $cid.Trim()) {
            $dryRunArgs += @('--chat-whitelist', $cid.Trim())
        }
    }
    $idempotentRaw = Invoke-BrainCapture -CliArgs $dryRunArgs
    Write-Output $idempotentRaw.Trim()

    Push-Location (Split-Path (Split-Path $BrainRepo -Parent) -Parent)
    try {
        & $PythonExe tools/py/tests/eval_people.py
        if ($LASTEXITCODE -ne 0) {
            throw "post-check failed: eval_people.py"
        }
        & $PythonExe tools/py/scripts/eval_people_trend.py
        if ($LASTEXITCODE -ne 0) {
            throw "post-check failed: eval_people_trend.py"
        }
        & $PythonExe tools/py/scripts/eval_people_trend_summary.py
        if ($LASTEXITCODE -ne 0) {
            throw "post-check failed: eval_people_trend_summary.py"
        }
        & $PythonExe tools/py/scripts/relationship_deltas_report.py
        if ($LASTEXITCODE -ne 0) {
            throw "post-check failed: relationship_deltas_report.py"
        }
        & $PythonExe tools/py/scripts/v6_gate_report.py
        if ($LASTEXITCODE -ne 0) {
            throw "post-check failed: v6_gate_report.py"
        }
        & $PythonExe tools/py/scripts/whatsapp_lid_residue_report.py
        if ($LASTEXITCODE -ne 0) {
            throw "post-check failed: whatsapp_lid_residue_report.py"
        }
        & $PythonExe tools/py/scripts/v6_gate_watch.py
        if ($LASTEXITCODE -ne 0) {
            throw "post-check failed: v6_gate_watch.py"
        }
        & $PythonExe tools/py/scripts/v6_flip_roadmap_if_ready.py
        if ($LASTEXITCODE -ne 0) {
            throw "post-check failed: v6_flip_roadmap_if_ready.py"
        }
        Invoke-Brain -CliArgs @('people-render', '--all', '--since-days', '45', '--limit', '2000')
        if ($LASTEXITCODE -ne 0) {
            throw "post-check failed: people-render"
        }
    } finally {
        Pop-Location
    }
    Write-Host "Post-checks completed." -ForegroundColor Green
}

$wechatArgs = @('wechat-sync', '--decoder-dir', $DecoderDir)
if ($Since.Trim()) {
    $wechatArgs += @('--since', $Since.Trim())
}

switch ($Mode) {
    'default' {
        # keep default behavior
    }
    'helper-no-person' {
        $wechatArgs += @('--include-helper-chats', '--chat-whitelist', 'filehelper', '--helper-chat-mode', 'no-person')
    }
    'helper-link-person' {
        $wechatArgs += @('--include-helper-chats', '--chat-whitelist', 'filehelper', '--helper-chat-mode', 'link-person')
    }
    'helper-blacklist' {
        $wechatArgs += @('--include-helper-chats', '--chat-blacklist', 'filehelper')
    }
}
foreach ($cid in @($ExtraWhitelist)) {
    if ($cid -and $cid.Trim()) {
        $wechatArgs += @('--chat-whitelist', $cid.Trim())
    }
}

if (-not $SkipPreflightDryRun) {
    $preflightArgs = @($wechatArgs + @('--dry-run'))
    Write-Host "Running preflight dry-run: $Mode" -ForegroundColor Cyan
    $preflightRaw = Invoke-BrainCapture -CliArgs $preflightArgs
    $preflightRaw.Trim() | Write-Output
    try {
        $preflight = $preflightRaw | ConvertFrom-Json
    } catch {
        throw "preflight JSON parse failed; abort apply"
    }
    $wouldInsert = 0
    foreach ($chat in @($preflight.chats)) {
        if ($null -ne $chat.would_insert) {
            $wouldInsert += [int]$chat.would_insert
        }
    }
    Write-Host "Preflight would_insert total: $wouldInsert (limit=$MaxWouldInsert)" -ForegroundColor Yellow
    if ($Apply -and $wouldInsert -gt $MaxWouldInsert) {
        throw "aborted: would_insert=$wouldInsert exceeds MaxWouldInsert=$MaxWouldInsert"
    }
} else {
    Write-Host "Preflight dry-run skipped by flag." -ForegroundColor Yellow
}

if ($Apply) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $label = "wechat-$Mode-$stamp"
    Write-Host "Creating backup snapshot: $label" -ForegroundColor Cyan
    Invoke-Brain -CliArgs @('ingest-backup-now', '--label', $label)
    Write-Host "Running apply mode: $Mode" -ForegroundColor Cyan
    Invoke-Brain -CliArgs $wechatArgs
} else {
    Write-Host "Dry-run only mode complete (preflight already executed)." -ForegroundColor Green
}

if ($RunPostChecks) {
    Invoke-PostChecks -SelectedMode $Mode
}
