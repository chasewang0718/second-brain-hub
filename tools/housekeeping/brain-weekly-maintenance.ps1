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
      3. brain ingest-log-recent --days 14 --limit 10
         - B-ING-0 健康检查: 读最近结构化 ingest JSONL (只读; 无日记仅 count=0)
      4. brain graph-rebuild-if-stale --max-age-hours 168
         - 重建 Kuzu 只读视图 (F3 POC), 供 graph-fof / graph-shared-identifier
      5. brain merge-candidates sync-from-graph --dry-run
         - 图 → T3 队列预览 (proposed 数写进日志, 不落盘)
      6. (可选) brain merge-candidates sync-from-graph --apply --auto-apply-min-score X
         - 仅当 -AutoApplyMinScore > 0 时启用. X >= 0.95 只自动合并 phone 级
           高置信对; 更低会把 email/wxid (0.92-0.93) 也吞进去, 不推荐.
    每步独立 try/catch; 整体成功标准: 步骤 1-3 OK (图步骤随 -SkipGraph 旁路).
.NOTES
    日志: D:\second-brain-assets\_runtime\logs\brain-weekly-maintenance-YYYYMMDD.log
    在 ROADMAP 中对应 E1; 由 tools/housekeeping/register-brain-weekly-maintenance.ps1 注册.
#>

[CmdletBinding()]
param(
    [switch]$SkipGraph,
    # Default 0 = opt-out: weekly task only runs the dry-run preview.
    # 推荐值 0.95: 只自动合并 phone 级高置信 (默认 phone=0.95, email=0.92,
    # wxid=0.93, 默认分 0.6, 所以 0.95 等价于 "仅自动合 phone").
    [double]$AutoApplyMinScore = 0.0,
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
    $savedPyPath = $env:PYTHONPATH
    try {
        Push-Location $BrainRepo
        $srcPath = Join-Path $BrainRepo 'src'
        $env:PYTHONPATH = if ($savedPyPath) { "$srcPath;$savedPyPath" } else { $srcPath }
        # Plain ``python -m brain_cli.main`` — no uv requirement (matches dev machines
        # where ``uv`` is not installed).
        $raw = & python -m brain_cli.main @Args 2>&1 | Out-String
        $exit = $LASTEXITCODE
        $sw.Stop()
        Add-Content -Path $logPath -Value $raw -Encoding UTF8
        Write-Log "[$Name] done exit=$exit elapsed=$([Math]::Round($sw.Elapsed.TotalSeconds,1))s"
        return [PSCustomObject]@{Name=$Name; ExitCode=$exit; Raw=$raw}
    } catch {
        $sw.Stop()
        Write-Log "[$Name] error: $($_.Exception.Message)"
        return [PSCustomObject]@{Name=$Name; ExitCode=-1; Raw=$_.Exception.Message}
    } finally {
        Pop-Location
        $env:PYTHONPATH = $savedPyPath
    }
}

Write-Log '=== brain weekly maintenance start ==='

$results = @()
$results += Invoke-BrainStep -Name 'identifiers-repair' -Args @('identifiers-repair','--kinds','all')
$results += Invoke-BrainStep -Name 'cloud-flush-dry-run' -Args @('cloud','flush','--dry-run')
$results += Invoke-BrainStep -Name 'ingest-log-recent-health' `
    -Args @('ingest-log-recent','--days','14','--limit','10')
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
    # Optional auto-apply step. Runs only when the registrar passes
    # -AutoApplyMinScore > 0; high-confidence pairs get merged
    # immediately, the rest stay pending for human review.
    if ($AutoApplyMinScore -gt 0) {
        $scoreStr = $AutoApplyMinScore.ToString([System.Globalization.CultureInfo]::InvariantCulture)
        $results += Invoke-BrainStep -Name "merge-candidates-sync-graph-apply@$scoreStr" `
            -Args @('merge-candidates','sync-from-graph','--apply','--auto-apply-min-score',$scoreStr)
    }
}

$failed = @($results | Where-Object { $_.ExitCode -ne 0 })
if ($failed.Count -gt 0) {
    Write-Log "=== brain weekly maintenance FAILED: $($failed.Count)/$($results.Count) step(s) ==="
    $failed | ForEach-Object { Write-Log "  - $($_.Name) exit=$($_.ExitCode)" }
    exit 1
}

Write-Log "=== brain weekly maintenance OK ($($results.Count) steps) ==="
exit 0
