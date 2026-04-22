#Requires -Version 5.1
<#
.SYNOPSIS
    注册 WeChat 只读巡检任务（每天 21:30）。
#>

[CmdletBinding()]
param(
    [string]$Time = '21:30',
    [switch]$Unregister,
    [switch]$RunNow
)

$TaskName = 'BrainWechatInspect'
$scriptPath = Join-Path $PSScriptRoot 'brain-wechat-inspect.ps1'
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
    Write-Host "立即运行: $TaskName" -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath
    return
}

$taskArgs = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArgs
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Daily readonly wechat ingest inspection (preflight + post-checks)" `
    -Force | Out-Null

Write-Host "已注册任务: $TaskName (每天 $Time)" -ForegroundColor Green
Write-Host "查看:   Get-ScheduledTask -TaskName $TaskName"
Write-Host "立即跑: ./register-brain-wechat-inspect.ps1 -RunNow"
Write-Host "注销:   ./register-brain-wechat-inspect.ps1 -Unregister"
