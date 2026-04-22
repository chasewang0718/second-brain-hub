#Requires -Version 5.1
<#
.SYNOPSIS
    E2 通用任务 runner：weekly-review / relationship-alerts / budget-tracker。
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('weekly-review', 'relationship-alerts', 'budget-tracker')]
    [string]$Task,
    [int]$Days = 45,
    [string]$BrainRepo = 'C:\dev-projects\second-brain-hub\tools\py',
    [string]$PythonExe = 'C:\dev-projects\second-brain-hub\tools\py\.venv\Scripts\python.exe'
)

$ErrorActionPreference = 'Continue'
$logDir = 'D:\second-brain-assets\_runtime\logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$stamp = Get-Date -Format 'yyyyMMdd'
$logPath = Join-Path $logDir ("brain-$Task-$stamp.log")
$contentRoot = 'D:\second-brain-content'

function Write-Log {
    param([string]$Line)
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $entry = "$ts  $Line"
    Write-Host $entry
    Add-Content -Path $logPath -Value $entry -Encoding UTF8
}

function Write-HubAlert {
    param(
        [string]$TaskName,
        [string]$Message
    )
    try {
        $journalDir = Join-Path $contentRoot '04-journal'
        if (-not (Test-Path $journalDir)) {
            New-Item -ItemType Directory -Path $journalDir -Force | Out-Null
        }
        $journalPath = Join-Path $journalDir ((Get-Date).ToString('yyyy-MM-dd') + '.md')
        if (-not (Test-Path $journalPath)) {
            $header = @(
                '---',
                "date: $((Get-Date).ToString('yyyy-MM-dd'))",
                'type: journal',
                '---',
                '',
                "# Journal · $((Get-Date).ToString('yyyy-MM-dd'))",
                ''
            )
            Set-Content -Path $journalPath -Value $header -Encoding UTF8
        }
        $line = "- [hub-alert] e2 task failed · task=$TaskName · ts=$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) · detail=$Message"
        Add-Content -Path $journalPath -Value $line -Encoding UTF8
    } catch {
        Write-Log "hub-alert append failed: $($_.Exception.Message)"
    }
}

function Invoke-Brain {
    param([string[]]$CliArgs)
    $savedPyPath = $env:PYTHONPATH
    try {
        Push-Location $BrainRepo
        $srcPath = Join-Path $BrainRepo 'src'
        $env:PYTHONPATH = if ($savedPyPath) { "$srcPath;$savedPyPath" } else { $srcPath }
        $raw = & $PythonExe -m brain_cli.main @CliArgs 2>&1 | Out-String
        $exit = $LASTEXITCODE
        Add-Content -Path $logPath -Value $raw -Encoding UTF8
        return [PSCustomObject]@{ ExitCode = $exit; Raw = $raw }
    } catch {
        return [PSCustomObject]@{ ExitCode = -1; Raw = $_.Exception.Message }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $savedPyPath
    }
}

Write-Log "=== brain e2 task start: $Task ==="
$cliArgs = @($Task)
if ($Task -eq 'relationship-alerts') {
    $cliArgs += @('--days', [string]$Days)
}
$result = Invoke-Brain -CliArgs $cliArgs
if ($result.ExitCode -ne 0) {
    Write-Log "=== brain e2 task FAILED: $Task exit=$($result.ExitCode) ==="
    Write-HubAlert -TaskName $Task -Message "exit=$($result.ExitCode)"
    exit 1
}

# Phase A6 Sprint 3: weekly review also refreshes derived metrics and
# rebuilds rolling topics + weekly digest so people cards stay <= 7d fresh.
if ($Task -eq 'weekly-review') {
    Write-Log '[weekly-review] phase A6: recompute person metrics'
    $metricsResult = Invoke-Brain -CliArgs @('person-metrics', 'recompute', '--all')
    if ($metricsResult.ExitCode -ne 0) {
        Write-Log "[weekly-review] person-metrics recompute FAILED exit=$($metricsResult.ExitCode) (continuing)"
        Write-HubAlert -TaskName $Task -Message "person-metrics recompute exit=$($metricsResult.ExitCode)"
    }

    Write-Log '[weekly-review] phase A6: rebuild person digests (topics_30d + weekly_digest)'
    $digestResult = Invoke-Brain -CliArgs @('person-digest', 'rebuild', '--all', '--weekly-days', '7', '--topics-days', '30')
    if ($digestResult.ExitCode -ne 0) {
        Write-Log "[weekly-review] person-digest rebuild FAILED exit=$($digestResult.ExitCode) (continuing)"
        Write-HubAlert -TaskName $Task -Message "person-digest rebuild exit=$($digestResult.ExitCode)"
    }

    # Phase A6 Sprint 4: refresh AI tier suggestions (never auto-applies over
    # a human-set fact). This keeps the "AI suggestion" line on people cards
    # aligned with the latest metrics.
    Write-Log '[weekly-review] phase A6: refresh tier suggestions (no --apply)'
    $tierResult = Invoke-Brain -CliArgs @('tier', 'suggest', '--all')
    if ($tierResult.ExitCode -ne 0) {
        Write-Log "[weekly-review] tier suggest FAILED exit=$($tierResult.ExitCode) (continuing)"
        Write-HubAlert -TaskName $Task -Message "tier suggest exit=$($tierResult.ExitCode)"
    }

    Write-Log '[weekly-review] run people eval trend snapshot'
    $savedPyPath = $env:PYTHONPATH
    try {
        Push-Location $BrainRepo
        $srcPath = Join-Path $BrainRepo 'src'
        $env:PYTHONPATH = if ($savedPyPath) { "$srcPath;$savedPyPath" } else { $srcPath }
        $trendRaw = & $PythonExe scripts/eval_people_trend.py 2>&1 | Out-String
        $trendExit = $LASTEXITCODE
        Add-Content -Path $logPath -Value $trendRaw -Encoding UTF8
        if ($trendExit -ne 0) {
            Write-Log "[weekly-review] people eval trend FAILED exit=$trendExit"
            Write-HubAlert -TaskName $Task -Message "weekly-review people eval trend exit=$trendExit"
            exit 1
        }

        Write-Log '[weekly-review] render people eval trend markdown'
        $trendSummaryRaw = & $PythonExe scripts/eval_people_trend_summary.py 2>&1 | Out-String
        $trendSummaryExit = $LASTEXITCODE
        Add-Content -Path $logPath -Value $trendSummaryRaw -Encoding UTF8
        if ($trendSummaryExit -ne 0) {
            Write-Log "[weekly-review] people eval trend summary FAILED exit=$trendSummaryExit"
            Write-HubAlert -TaskName $Task -Message "weekly-review people eval trend summary exit=$trendSummaryExit"
            exit 1
        }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $savedPyPath
    }
}

Write-Log "=== brain e2 task OK: $Task ==="
exit 0
