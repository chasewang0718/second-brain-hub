#Requires -Version 5.1
<#
.SYNOPSIS
    注册 E2 剩余 3 个任务:
      - BrainWeeklyReview (每周日 20:00)
      - BrainRelationshipAlerts (每天 08:30)
      - BrainBudgetTracker (每周一 08:45)
#>

[CmdletBinding()]
param(
    [switch]$Unregister,
    [switch]$RunNow
)

$scriptPath = Join-Path $PSScriptRoot 'brain-e2-task.ps1'
if (-not (Test-Path $scriptPath)) {
    Write-Error "找不到 $scriptPath"
    exit 1
}

$tasks = @(
    @{
        Name = 'BrainWeeklyReview'
        Description = 'E2 weekly review digest'
        Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '20:00'
        Args = "-NoProfile -WindowStyle Hidden -File `"$scriptPath`" -Task weekly-review"
        RunArgs = @('-Task', 'weekly-review')
    },
    @{
        Name = 'BrainRelationshipAlerts'
        Description = 'E2 relationship alerts digest'
        Trigger = New-ScheduledTaskTrigger -Daily -At '08:30'
        Args = "-NoProfile -WindowStyle Hidden -File `"$scriptPath`" -Task relationship-alerts -Days 45"
        RunArgs = @('-Task', 'relationship-alerts', '-Days', '45')
    },
    @{
        Name = 'BrainBudgetTracker'
        Description = 'E2 budget tracker digest'
        Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At '08:45'
        Args = "-NoProfile -WindowStyle Hidden -File `"$scriptPath`" -Task budget-tracker"
        RunArgs = @('-Task', 'budget-tracker')
    }
)

if ($Unregister) {
    foreach ($task in $tasks) {
        Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "已注销任务 $($task.Name)" -ForegroundColor Green
    }
    return
}

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

foreach ($task in $tasks) {
    if ($RunNow) {
        Write-Host "立即运行: $($task.Name)" -ForegroundColor Cyan
        & powershell -NoProfile -File $scriptPath @($task.RunArgs)
        continue
    }
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $task.Args
    Register-ScheduledTask -TaskName $task.Name `
        -Action $action -Trigger $task.Trigger -Settings $settings -Principal $principal `
        -Description $task.Description -Force | Out-Null
    Write-Host "已注册任务: $($task.Name)" -ForegroundColor Green
}

if (-not $RunNow) {
    Write-Host '查看:   Get-ScheduledTask -TaskName BrainWeeklyReview,BrainRelationshipAlerts,BrainBudgetTracker'
    Write-Host '注销:   ./register-brain-e2-tasks.ps1 -Unregister'
    Write-Host '冒烟:   ./register-brain-e2-tasks.ps1 -RunNow'
}
