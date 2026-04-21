#Requires -Version 5.1
<#
.SYNOPSIS
    E1 常驻周期任务: 每周跑一轮 brain 低风险维护动作.
.DESCRIPTION
    执行内容 (均只读 / 幂等):
      1. brain identifiers-repair --kinds all
         - 存量 person_identifiers 大小写 / 号段归一, 冲突写入 merge_candidates
      2. brain cloud flush --dry-run
         - 看看 cursor_queue 里是否有待人工处理任务
      3. brain graph-build
         - 重建 Kuzu 只读视图 (F3 POC), 供 graph-fof / graph-shared-identifier
    每步独立 try/catch; 整体成功标准: 前两步 OK (第三步 Kuzu 可选).
.NOTES
    日志: D:\second-brain-assets\_runtime\logs\brain-weekly-maintenance-YYYYMMDD.log
    在 ROADMAP 中对应 E1; 由 tools/housekeeping/register-brain-weekly-maintenance.ps1 注册.
#>

[CmdletBinding()]
param(
    [switch]$SkipGraph,
    [string]$BrainRepo = 'C:\dev-projects\second-brain-hub\tools\py'
)

$ErrorActionPreference = 'Continue'
$logDir = 'D:\second-brain-assets\_runtime\logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$stamp  = Get-Date -Format 'yyyyMMdd'
$logPath = Join-Path $logDir ("brain-weekly-maintenance-$stamp.log")

function Write-Log {
    param([string]$Line)
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $entry = "$ts  $Line"
    Write-Host $entry
    Add-Content -Path $logPath -Value $entry -Encoding UTF8
}

function Invoke-BrainStep {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string[]]$Args
    )
    Write-Log "[$Name] start"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $raw = & python -m uv run --directory $BrainRepo brain @Args 2>&1 | Out-String
        $exit = $LASTEXITCODE
        $sw.Stop()
        Add-Content -Path $logPath -Value $raw -Encoding UTF8
        Write-Log "[$Name] done exit=$exit elapsed=$([Math]::Round($sw.Elapsed.TotalSeconds,1))s"
        return [PSCustomObject]@{Name=$Name; ExitCode=$exit; Raw=$raw}
    } catch {
        $sw.Stop()
        Write-Log "[$Name] error: $($_.Exception.Message)"
        return [PSCustomObject]@{Name=$Name; ExitCode=-1; Raw=$_.Exception.Message}
    }
}

Write-Log '=== brain weekly maintenance start ==='

$results = @()
$results += Invoke-BrainStep -Name 'identifiers-repair' -Args @('identifiers-repair','--kinds','all')
$results += Invoke-BrainStep -Name 'cloud-flush-dry-run' -Args @('cloud','flush','--dry-run')
if (-not $SkipGraph) {
    # Cheap path: only rebuild when DuckDB is newer (or --max-age-hours
    # triggers). On a quiet week this is a sub-second no-op; on a busy
    # one it's the same ~7s full rebuild we used to do unconditionally.
    $results += Invoke-BrainStep -Name 'graph-rebuild-if-stale' `
        -Args @('graph-rebuild-if-stale','--max-age-hours','168')
    # Graph → T3 merge queue sync. Default stays dry-run: we surface
    # the count in the log, require human review before actually
    # inserting pending candidates.
    $results += Invoke-BrainStep -Name 'merge-candidates-sync-graph-dryrun' `
        -Args @('merge-candidates','sync-from-graph','--dry-run')
}

$failed = @($results | Where-Object { $_.ExitCode -ne 0 })
if ($failed.Count -gt 0) {
    Write-Log "=== brain weekly maintenance FAILED: $($failed.Count)/$($results.Count) step(s) ==="
    $failed | ForEach-Object { Write-Log "  - $($_.Name) exit=$($_.ExitCode)" }
    exit 1
}

Write-Log "=== brain weekly maintenance OK ($($results.Count) steps) ==="
exit 0
