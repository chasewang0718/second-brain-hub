#Requires -Version 5.1
<#
.SYNOPSIS
    在 Windows 任务计划程序里注册一次性任务:
    2026-04-26 09:00 自动清理 D:\BaiduSyncdisk\ 已迁移源文件.

.DESCRIPTION
    任务名: BrainAssetSourceCleanup-<job>
    触发:   指定日期一次性 (默认 Phase 2.2 完成 + 7 天)
    动作:   powershell -File brain-asset-source-cleanup.ps1

.EXAMPLE
    .\register-source-cleanup-task.ps1
    .\register-source-cleanup-task.ps1 -RunDate "2026-04-26 09:00"
    .\register-source-cleanup-task.ps1 -Remove
    .\register-source-cleanup-task.ps1 -RunNow
#>

param(
    [string]$TaskName = "BrainAssetSourceCleanup-Baidu2026-04",
    [string]$RunDate = "2026-04-26 09:00",
    [switch]$Remove,
    [switch]$RunNow
)

$SCRIPT_PATH = Join-Path $PSScriptRoot "brain-asset-source-cleanup.ps1"

if ($Remove) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "✅ 已注销任务: $TaskName" -ForegroundColor Green
    }
    catch {
        Write-Host "❌ 注销失败: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit
}

if ($RunNow) {
    Write-Host "立即手动运行一次 (测试)..." -ForegroundColor Cyan
    & powershell -NoProfile -File $SCRIPT_PATH -DryRun
    exit
}

if (-not (Test-Path $SCRIPT_PATH)) {
    Write-Host "❌ 找不到 $SCRIPT_PATH" -ForegroundColor Red; exit 1
}

# 解析 RunDate
try {
    $trigger_time = [DateTime]::ParseExact($RunDate, "yyyy-MM-dd HH:mm", $null)
}
catch {
    Write-Host "❌ RunDate 格式错: '$RunDate'. 应该是 'YYYY-MM-DD HH:MM'" -ForegroundColor Red; exit 1
}

# 已存在就先注销
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "♻️  已注销旧任务, 重新注册中..." -ForegroundColor Yellow
}

$action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$SCRIPT_PATH`""
$trigger  = New-ScheduledTaskTrigger -Once -At $trigger_time
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Phase 2.2 百度云迁移后 7 天自动清源 (一次性)" | Out-Null

Write-Host "✅ 已注册: $TaskName" -ForegroundColor Green
Write-Host "   触发时间: $trigger_time" -ForegroundColor DarkGray
Write-Host "   动作:     powershell -File $SCRIPT_PATH" -ForegroundColor DarkGray
Write-Host ""
Write-Host "查看状态:   Get-ScheduledTask -TaskName $TaskName" -ForegroundColor DarkCyan
Write-Host "立刻测试:   .\register-source-cleanup-task.ps1 -RunNow  (会 DryRun, 不真删)" -ForegroundColor DarkCyan
Write-Host "提前取消:   .\register-source-cleanup-task.ps1 -Remove" -ForegroundColor DarkCyan
