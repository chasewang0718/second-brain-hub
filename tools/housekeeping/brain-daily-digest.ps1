#Requires -Version 5.1
<#
.SYNOPSIS
    E2 日报任务: 生成 daily digest（桌面 + 日志可追溯）。
.DESCRIPTION
    调用:
      python -m brain_cli.main daily-digest

    输出:
      - digest markdown: 由 CLI 内部写入 content_root/08-indexes/digests/
      - runner log: D:\second-brain-assets\_runtime\logs\brain-daily-digest-YYYYMMDD.log

    约束:
      - 仅执行只读查询 + 生成摘要，不修改核心结构化数据。
      - 若失败，退出码 != 0，便于 Task Scheduler 告警。
#>

[CmdletBinding()]
param(
    [string]$BrainRepo = 'C:\dev-projects\second-brain-hub\tools\py'
)

$ErrorActionPreference = 'Continue'
$logDir = 'D:\second-brain-assets\_runtime\logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$stamp  = Get-Date -Format 'yyyyMMdd'
$logPath = Join-Path $logDir ("brain-daily-digest-$stamp.log")

function Write-Log {
    param([string]$Line)
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $entry = "$ts  $Line"
    Write-Host $entry
    Add-Content -Path $logPath -Value $entry -Encoding UTF8
}

function Invoke-Brain {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Args
    )
    Write-Log "[$Name] start"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $savedPyPath = $env:PYTHONPATH
    try {
        Push-Location $BrainRepo
        $srcPath = Join-Path $BrainRepo 'src'
        $env:PYTHONPATH = if ($savedPyPath) { "$srcPath;$savedPyPath" } else { $srcPath }
        $raw = & python -m brain_cli.main @Args 2>&1 | Out-String
        $exit = $LASTEXITCODE
        $sw.Stop()
        Add-Content -Path $logPath -Value $raw -Encoding UTF8
        Write-Log "[$Name] done exit=$exit elapsed=$([Math]::Round($sw.Elapsed.TotalSeconds,1))s"
        return [PSCustomObject]@{ Name = $Name; ExitCode = $exit; Raw = $raw }
    } catch {
        $sw.Stop()
        Write-Log "[$Name] error: $($_.Exception.Message)"
        return [PSCustomObject]@{ Name = $Name; ExitCode = -1; Raw = $_.Exception.Message }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $savedPyPath
    }
}

Write-Log '=== brain daily digest start ==='
$result = Invoke-Brain -Name 'daily-digest' -Args @('daily-digest')
if ($result.ExitCode -ne 0) {
    Write-Log "=== brain daily digest FAILED exit=$($result.ExitCode) ==="
    exit 1
}
Write-Log '=== brain daily digest OK ==='
exit 0

