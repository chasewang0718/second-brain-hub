#Requires -Version 5.1
<#
.SYNOPSIS
    Telemetry 日志分析 - 出成本/准确率/升云率报告.

.DESCRIPTION
    读 telemetry/logs/*.jsonl, 按指定时间范围聚合, 输出到 stdout.
    默认读最近 7 天.

.PARAMETER Days
    近 N 天 (默认 7).

.PARAMETER Month
    指定月份 "YYYY-MM" (优先于 -Days).

.PARAMETER Task
    只分析指定 task (可多次: -Task pdf-classify,inbox-text-route).

.PARAMETER Format
    输出格式: text (默认) / json / markdown.

.EXAMPLE
    .\analyze.ps1                        # 近 7 天概览
    .\analyze.ps1 -Days 30               # 近 30 天
    .\analyze.ps1 -Month 2026-04         # 整个 4 月
    .\analyze.ps1 -Task pdf-classify     # 只看 PDF 分类
    .\analyze.ps1 -Format markdown > report.md
#>

[CmdletBinding()]
param(
    [int]$Days = 7,
    [string]$Month,
    [string[]]$Task,
    [ValidateSet('text','json','markdown')] [string]$Format = 'text'
)

$ErrorActionPreference = 'Stop'

$logsDir = Join-Path $PSScriptRoot 'logs'
if (-not (Test-Path $logsDir)) {
    Write-Host "[!] logs dir not found: $logsDir" -ForegroundColor Yellow
    Write-Host "    (no telemetry recorded yet)" -ForegroundColor DarkGray
    return
}

# 确定时间范围
if ($Month) {
    $fromDate = [datetime]"$Month-01"
    $toDate = $fromDate.AddMonths(1).AddSeconds(-1)
}
else {
    $toDate = (Get-Date).ToUniversalTime()
    $fromDate = $toDate.AddDays(-$Days)
}

# 读所有相关日志文件
# 时间解析用 DateTimeOffset 保留时区信息 (避免 Z 后缀被当本地时间)
$allEntries = @()
Get-ChildItem $logsDir -Filter '*.jsonl' | ForEach-Object {
    Get-Content $_.FullName -Encoding UTF8 | ForEach-Object {
        if ($_ -match '^\s*$') { return }
        try {
            $entry = $_ | ConvertFrom-Json
            $entryTs = [DateTimeOffset]::Parse($entry.ts).UtcDateTime
            if ($entryTs -ge $fromDate -and $entryTs -le $toDate) {
                if ($Task -and $entry.task -notin $Task) { return }
                $allEntries += $entry
            }
        } catch {
            Write-Warning "parse fail: $_"
        }
    }
}

if ($allEntries.Count -eq 0) {
    Write-Host "[!] no entries in range $($fromDate.ToString('yyyy-MM-dd')) .. $($toDate.ToString('yyyy-MM-dd'))" -ForegroundColor Yellow
    return
}

# 聚合
$byTask = $allEntries | Group-Object task
$totalCost = ($allEntries | Where-Object { $_.cost_usd } | Measure-Object -Property cost_usd -Sum).Sum
$cloudCount = ($allEntries | Where-Object { $_.executor -eq 'cloud' }).Count
$localCount = ($allEntries | Where-Object { $_.executor -eq 'local' }).Count
$escalatedCount = @($allEntries | Where-Object { $_.escalated }).Count
$schemaFailCount = @($allEntries | Where-Object { -not $_.schema_valid }).Count

# ============================================================
# 输出
# ============================================================
$report = [ordered]@{
    range      = "$($fromDate.ToString('yyyy-MM-dd')) .. $($toDate.ToString('yyyy-MM-dd'))"
    total_calls = $allEntries.Count
    local_calls = $localCount
    cloud_calls = $cloudCount
    local_pct   = if ($allEntries.Count) { [math]::Round($localCount / $allEntries.Count * 100, 1) } else { 0 }
    escalated   = $escalatedCount
    escalation_rate_pct = if ($localCount) { [math]::Round($escalatedCount / $localCount * 100, 1) } else { 0 }
    schema_fails = $schemaFailCount
    total_cost_usd = [math]::Round($totalCost, 3)
    by_task = $byTask | ForEach-Object {
        $entries = $_.Group
        $avgConf = ($entries | Where-Object { $_.confidence } | Measure-Object -Property confidence -Average).Average
        $cost = ($entries | Where-Object { $_.cost_usd } | Measure-Object -Property cost_usd -Sum).Sum
        [ordered]@{
            task = $_.Name
            count = $_.Count
            avg_confidence = if ($avgConf) { [math]::Round($avgConf, 3) } else { $null }
            cost_usd = [math]::Round($cost, 3)
            local_pct = if ($_.Count) { [math]::Round((($entries | Where-Object { $_.executor -eq 'local' }).Count) / $_.Count * 100, 1) } else { 0 }
        }
    }
}

switch ($Format) {
    'json' {
        $report | ConvertTo-Json -Depth 4
    }
    'markdown' {
        Write-Output "# Telemetry Report"
        Write-Output ""
        Write-Output "**Range**: $($report.range)"
        Write-Output ""
        Write-Output "## Summary"
        Write-Output ""
        Write-Output "| Metric | Value |"
        Write-Output "|---|---|"
        Write-Output "| Total calls | $($report.total_calls) |"
        Write-Output "| Local / Cloud | $($report.local_calls) / $($report.cloud_calls) ($($report.local_pct)% local) |"
        Write-Output "| Escalated | $($report.escalated) ($($report.escalation_rate_pct)% of local) |"
        Write-Output "| Schema fails | $($report.schema_fails) |"
        Write-Output "| Cloud cost | `$$($report.total_cost_usd) USD |"
        Write-Output ""
        Write-Output "## By Task"
        Write-Output ""
        Write-Output "| Task | Count | Avg Confidence | Local % | Cost USD |"
        Write-Output "|---|---|---|---|---|"
        foreach ($t in $report.by_task) {
            Write-Output "| $($t.task) | $($t.count) | $($t.avg_confidence) | $($t.local_pct)% | `$$($t.cost_usd) |"
        }
    }
    default {  # text
        Write-Host "=== Telemetry $($report.range) ===" -ForegroundColor Cyan
        Write-Host ("  Total calls:     {0}" -f $report.total_calls)
        Write-Host ("  Local / Cloud:   {0} / {1} ({2}% local)" -f $report.local_calls, $report.cloud_calls, $report.local_pct)
        Write-Host ("  Escalated:       {0} ({1}% of local)" -f $report.escalated, $report.escalation_rate_pct)
        Write-Host ("  Schema fails:    {0}" -f $report.schema_fails)
        Write-Host ("  Cloud cost:      `${0} USD" -f $report.total_cost_usd)
        Write-Host ""
        Write-Host "=== By Task ===" -ForegroundColor Cyan
        foreach ($t in $report.by_task) {
            Write-Host ("  {0,-22} {1,4} calls  avg_conf={2}  local={3}%  cost=`${4}" -f `
                $t.task, $t.count, $t.avg_confidence, $t.local_pct, $t.cost_usd)
        }
    }
}
