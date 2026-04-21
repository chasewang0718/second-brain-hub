#Requires -Version 5.1
<#
.SYNOPSIS
    注册 Windows Task Scheduler 任务: 每周日 23:00 跑 brain-weekly-maintenance.ps1.
.DESCRIPTION
    任务名: BrainWeeklyMaintenance
    trigger: 每周 Sunday 23:00
    action:  powershell -NoProfile -File brain-weekly-maintenance.ps1

    首次运行前建议用 -RunNow 手动过一遍, 看 $logPath 是否正常写入.
.PARAMETER Time
    HH:mm, 默认 23:00
.PARAMETER DayOfWeek
    默认 Sunday
.PARAMETER RunNow
    立即跑一次 (不注册)
.PARAMETER Unregister
    注销任务
.PARAMETER AutoApplyMinScore
    传给 brain-weekly-maintenance.ps1 的 -AutoApplyMinScore. 默认 0 = 关闭自动合并,
    只跑 dry-run 预览. 推荐 0.95 = 仅 phone 级自动合并 (email / wxid 的 0.92-0.93
    仍留 pending 等人工 accept). 更低的阈值会把 email / wxid 也吞进去, 不推荐.
#>

[CmdletBinding()]
param(
    [string]$Time = '23:00',
    [string]$DayOfWeek = 'Sunday',
    [switch]$Unregister,
    [switch]$RunNow,
    [double]$AutoApplyMinScore = 0.0
)

$TaskName = 'BrainWeeklyMaintenance'
$scriptPath = Join-Path $PSScriptRoot 'brain-weekly-maintenance.ps1'

if (-not (Test-Path $scriptPath)) {
    Write-Error "找不到 $scriptPath"
    exit 1
}

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已注销任务 $TaskName" -ForegroundColor Green
    return
}

$scoreStr = $AutoApplyMinScore.ToString([System.Globalization.CultureInfo]::InvariantCulture)

if ($RunNow) {
    Write-Host "立即运行任务 (不注册)... AutoApplyMinScore=$scoreStr" -ForegroundColor Cyan
    & powershell -NoProfile -File $scriptPath -AutoApplyMinScore $AutoApplyMinScore
    return
}

$taskArgs = "-NoProfile -WindowStyle Hidden -File `"$scriptPath`" -AutoApplyMinScore $scoreStr"
$action   = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArgs
$trigger   = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable `
              -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "每周 $DayOfWeek $Time 跑 brain identifiers-repair / cloud flush --dry-run / graph-build" `
    -Force | Out-Null

Write-Host "已注册任务: $TaskName (每周 $DayOfWeek $Time, AutoApplyMinScore=$scoreStr)" -ForegroundColor Green
Write-Host "查看:   Get-ScheduledTask -TaskName $TaskName"
Write-Host "立即跑: ./register-brain-weekly-maintenance.ps1 -RunNow"
Write-Host "启用自动合 phone 对: ./register-brain-weekly-maintenance.ps1 -AutoApplyMinScore 0.95"
Write-Host "注销:   ./register-brain-weekly-maintenance.ps1 -Unregister"
