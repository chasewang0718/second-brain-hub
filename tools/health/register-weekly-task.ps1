#Requires -Version 5.1
<#
.SYNOPSIS
    注册 / 注销 Windows 任务计划程序中的 brain 周报任务.

.DESCRIPTION
    任务名: BrainWeeklyReport
    触发:   每周日 21:00
    动作:   powershell -NoProfile -File brain-weekly-report.ps1
    账号:   当前用户 (无需 admin, 用户登录时才运行)

.EXAMPLE
    .\register-weekly-task.ps1           # 注册 (默认)
    .\register-weekly-task.ps1 -Remove   # 注销
    .\register-weekly-task.ps1 -RunNow   # 立即手动运行一次 (测试)
#>

param(
    [switch]$Remove,
    [switch]$RunNow
)

$TASK_NAME   = "BrainWeeklyReport"
$SCRIPT_PATH = Join-Path $PSScriptRoot "brain-weekly-report.ps1"

if (-not (Test-Path $SCRIPT_PATH)) {
    Write-Host "❌ 找不到 $SCRIPT_PATH" -ForegroundColor Red
    exit 1
}

# -------- 注销 --------
if ($Remove) {
    $existing = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
        Write-Host "✅ 已注销任务: $TASK_NAME" -ForegroundColor Green
    }
    else {
        Write-Host "⚠️  任务不存在: $TASK_NAME" -ForegroundColor Yellow
    }
    return
}

# -------- 立即运行 --------
if ($RunNow) {
    Write-Host "▶️  立即手动运行周报任务 (测试)..." -ForegroundColor Cyan
    powershell -NoProfile -ExecutionPolicy Bypass -File $SCRIPT_PATH
    Write-Host "✅ 运行完成, 看日志: Get-Content D:\second-brain-content\.brain-weekly.log -Tail 30" -ForegroundColor Green
    return
}

# -------- 注册 --------
$existing = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "⚠️  任务 $TASK_NAME 已存在, 先删除再重建" -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$SCRIPT_PATH`""

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "21:00"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TASK_NAME `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "brain 周报自动生成 (每周日 21:00). 调用 cursor-agent 分析本周 git 活动 + journal, 写入 04-journal/weekly/." | Out-Null

Write-Host "✅ 已注册任务: $TASK_NAME" -ForegroundColor Green
Write-Host "   下次运行: 每周日 21:00 (可在 taskschd.msc 查看)" -ForegroundColor DarkGray
Write-Host "   测试运行: .\register-weekly-task.ps1 -RunNow" -ForegroundColor DarkGray
Write-Host "   注销任务: .\register-weekly-task.ps1 -Remove" -ForegroundColor DarkGray
