#Requires -Version 5.1
<#
.SYNOPSIS
    注册 Windows Task Scheduler 任务: 每天指定时间跑 brain-daily-digest.ps1.
.DESCRIPTION
    任务名: BrainDailyDigest
    trigger: 每天 (默认 07:00)
    action:  powershell -NoProfile -File brain-daily-digest.ps1
.PARAMETER Time
    HH:mm, 默认 07:00
.PARAMETER Unregister
    注销任务
.PARAMETER RunNow
    立即跑一次 (不注册)
#>

[CmdletBinding()]
param(
    [string]$Time = '07:00',
    [switch]$Unregister,
    [switch]$RunNow
)

$TaskName = 'BrainDailyDigest'
$scriptPath = Join-Path $PSScriptRoot 'brain-daily-digest.ps1'

if (-not (Test-Path $scriptPath)) {
    Write-Error "找不到 $scriptPath"
    exit 1
}

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已注销任务 $TaskName" -ForegroundColor Green
    return
}

if ($RunNow) {
    Write-Host '立即运行任务 (不注册)...' -ForegroundColor Cyan
    & powershell -NoProfile -File $scriptPath
    return
}

$taskArgs = "-NoProfile -WindowStyle Hidden -File `"$scriptPath`""
$action    = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArgs
$trigger   = New-ScheduledTaskTrigger -Daily -At $Time
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable `
             -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
             -RunOnlyIfNetworkAvailable `
             -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "每天 $Time 生成 brain daily digest (E2)" `
    -Force | Out-Null

Write-Host "已注册任务: $TaskName (每天 $Time)" -ForegroundColor Green
Write-Host "查看:   Get-ScheduledTask -TaskName $TaskName"
Write-Host "立即跑: ./register-brain-daily-digest.ps1 -RunNow"
Write-Host "注销:   ./register-brain-daily-digest.ps1 -Unregister"

