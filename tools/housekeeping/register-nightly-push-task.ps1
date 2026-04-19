#Requires -Version 5.1
<#
.SYNOPSIS
    注册 Windows 任务计划程序: 每晚 22:00 跑 brain-nightly-push.ps1.
.DESCRIPTION
    任务名: BrainNightlyPush
    trigger: 每天 22:00
    action:  powershell -NoProfile -File brain-nightly-push.ps1
    只在用户登录且网络可用时跑.
#>

[CmdletBinding()]
param(
    [string]$Time = "22:00",
    [switch]$Unregister,
    [switch]$RunNow
)

$TaskName = "BrainNightlyPush"
$scriptPath = Join-Path $PSScriptRoot "brain-nightly-push.ps1"

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
    Write-Host "立即运行任务..." -ForegroundColor Cyan
    & powershell -NoProfile -File $scriptPath
    return
}

$action    = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -File `"$scriptPath`""
$trigger   = New-ScheduledTaskTrigger -Daily -At $Time
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RunOnlyIfNetworkAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "每晚 $Time 自动把 D:\brain 和 second-brain-hub 推到 GitHub" `
    -Force | Out-Null

Write-Host "已注册任务: $TaskName (每天 $Time)" -ForegroundColor Green
Write-Host "查看: Get-ScheduledTask -TaskName $TaskName"
Write-Host "立即跑: ./register-nightly-push-task.ps1 -RunNow"
Write-Host "注销: ./register-nightly-push-task.ps1 -Unregister"
