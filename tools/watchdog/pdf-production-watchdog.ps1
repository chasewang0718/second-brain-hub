#Requires -Version 5.1
<#
.SYNOPSIS
    Watchdog for `brain-asset-pdf-pipeline.ps1 -Production`.
    Detects crashes + stalls, auto-restarts (max 3), notifies via toast+beep.

.DESCRIPTION
    Responsibility boundary (L1 自动重启, 不改代码):
        - Monitor: 60s poll of PID + log mtime
        - Restart: 直接调 pipeline -Production (worker 天然幂等: sha12 skip)
        - Notify : Windows toast + beep + alert log
        - Heartbeat: 每 30min 写状态文件, 白天可查
        - NOT allowed: 改脚本代码, git commit, call 云端模型

    Detection rules:
        - PID dead + log 无 "=== 完成 ===" → 视为 crash, 重启 (若 < MaxRestarts)
        - PID live + log > StallMinutes 无新写 → 视为 stalled, 发 warn toast (不杀)
        - Log 出现 "^完成\." → 视为成功, 发 done toast, 退出 watchdog

.PARAMETER PidFile
    pipeline 的 PID 文件, 默认 D:\brain-assets\_migration\ollama-production.pid

.PARAMETER MaxRestarts
    最多自动重启次数, 默认 3

.PARAMETER StallMinutes
    log 无更新多久算卡住, 默认 5 分钟

.PARAMETER CheckIntervalSec
    轮询间隔, 默认 60 秒

.EXAMPLE
    # 独立进程启动:
    Start-Process powershell.exe -ArgumentList @(
        '-NoProfile','-File',
        'C:\dev-projects\second-brain-hub\tools\watchdog\pdf-production-watchdog.ps1'
    ) -WindowStyle Hidden
#>

[CmdletBinding()]
param(
    [string]$PidFile = 'D:\brain-assets\_migration\ollama-production.pid',
    [int]$MaxRestarts = 3,
    [int]$StallMinutes = 5,
    [int]$CheckIntervalSec = 60,
    [string]$WatchdogDir = 'D:\brain-assets\_migration\_watchdog',
    [string]$PipelineScript = 'C:\dev-projects\second-brain-hub\tools\ollama-pipeline\brain-asset-pdf-pipeline.ps1'
)

$ErrorActionPreference = 'Continue'

. "$PSScriptRoot\notify.ps1"

if (-not (Test-Path $WatchdogDir)) { New-Item -ItemType Directory -Path $WatchdogDir -Force | Out-Null }
$alertLog     = Join-Path $WatchdogDir 'alerts.log'
$heartbeatFile = Join-Path $WatchdogDir 'heartbeat.txt'
$stateFile    = Join-Path $WatchdogDir 'state.json'
$wdLog        = Join-Path $WatchdogDir "watchdog-$(Get-Date -Format yyyyMMdd-HHmmss).log"

function Write-WdLog {
    param([string]$Msg, [string]$Color = 'White')
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $Msg"
    Write-Host $line -ForegroundColor $Color
    try { $line | Add-Content -Path $wdLog -Encoding UTF8 } catch {}
}

function Read-PipelineState {
    $pidInfo = Get-Content $PidFile -Raw -ErrorAction SilentlyContinue
    if (-not $pidInfo) { return $null }
    $parts = ($pidInfo -split "`t")
    $pidNum = [int]($parts[0].Trim())
    $logPath = if ($parts.Count -ge 3) { $parts[2].Trim() } else { $null }
    return @{ Pid = $pidNum; LogPath = $logPath }
}

function Get-Progress {
    param([string]$LogPath)
    if (-not $LogPath -or -not (Test-Path $LogPath)) { return @{ N = 0; Total = 0; Done = $false } }
    $lines = Get-Content $LogPath -ErrorAction SilentlyContinue
    $last = ($lines | Select-String '^\[(\d+)/(\d+)\]' | Select-Object -Last 1)
    $n = 0; $total = 0
    if ($last) {
        $n = [int]$last.Matches[0].Groups[1].Value
        $total = [int]$last.Matches[0].Groups[2].Value
    }
    # 成功标志: pipeline 末尾的 "完成. 低置信/rejected..."
    $done = [bool]($lines | Select-String '^完成\.')
    return @{ N = $n; Total = $total; Done = $done }
}

function Restart-Pipeline {
    Write-WdLog "自动重启 pipeline -Production ..." Yellow
    $ts = Get-Date -Format yyyyMMdd-HHmmss
    $newStdout = "D:\brain-assets\_migration\ollama-production-$ts.log"
    $newStderr = "D:\brain-assets\_migration\ollama-production-$ts.err"
    $proc = Start-Process powershell.exe `
        -ArgumentList @(
            '-NoProfile','-ExecutionPolicy','Bypass',
            '-File', $PipelineScript,
            '-Production'
        ) `
        -RedirectStandardOutput $newStdout `
        -RedirectStandardError $newStderr `
        -WindowStyle Hidden `
        -PassThru
    "$($proc.Id)`t$ts`t$newStdout" | Out-File $PidFile -Encoding UTF8
    Write-WdLog "新 PID: $($proc.Id), log: $newStdout" Green
    return $proc.Id
}

# ---- 主循环 ----
$restartCount = 0
$lastHeartbeat = [DateTime]::MinValue
$startedAt = Get-Date

Write-WdLog "=== PDF Production Watchdog 启动 ===" Cyan
Write-WdLog "  PidFile         : $PidFile"
Write-WdLog "  MaxRestarts     : $MaxRestarts"
Write-WdLog "  StallMinutes    : $StallMinutes"
Write-WdLog "  CheckInterval   : $CheckIntervalSec s"
Write-WdLog "  WatchdogDir     : $WatchdogDir"

Send-BrainAlert -Title 'Watchdog 上岗' `
                -Message "盯 PDF production. 最多自动重启 $MaxRestarts 次, 卡 $StallMinutes min 记 log." `
                -Severity info -AlertLogFile $alertLog -Popup $false

while ($true) {
    $state = Read-PipelineState
    if (-not $state) {
        Write-WdLog "!! PidFile 读不到: $PidFile" Red
        Start-Sleep -Seconds $CheckIntervalSec
        continue
    }

    $proc = Get-Process -Id $state.Pid -ErrorAction SilentlyContinue
    $progress = Get-Progress -LogPath $state.LogPath
    $now = Get-Date

    # log mtime
    $logMtime = $null
    if ($state.LogPath -and (Test-Path $state.LogPath)) {
        $logMtime = (Get-Item $state.LogPath).LastWriteTime
    }
    $sinceWriteMin = if ($logMtime) { [math]::Round(($now - $logMtime).TotalMinutes, 1) } else { -1 }

    # ---- 成功分支 (最终结局 → 弹窗) ----
    if ($progress.Done) {
        $elapsedHr = [math]::Round(($now - $startedAt).TotalHours, 2)
        Send-BrainAlert -Title 'PDF Production 完成' `
            -Message "共 $($progress.N)/$($progress.Total), 用时 $elapsedHr 小时, 重启 $restartCount 次. 去跑 QA+apply." `
            -Severity done -AlertLogFile $alertLog -Popup $true
        Write-WdLog "=== 完成, 退出 watchdog ===" Green
        @{ exit_reason = 'success'; n = $progress.N; total = $progress.Total; restarts = $restartCount; ended_at = $now.ToString('o') } `
            | ConvertTo-Json | Out-File $stateFile -Encoding UTF8
        break
    }

    # ---- 进程死分支 ----
    if (-not $proc) {
        Write-WdLog "!! PID $($state.Pid) DEAD (进度 $($progress.N)/$($progress.Total))" Red

        if ($restartCount -ge $MaxRestarts) {
            # 最终结局 → 弹窗 (早上解锁会看到)
            Send-BrainAlert -Title 'PDF Production 崩了 (已耗尽重启)' `
                -Message "PID $($state.Pid) 死, 已重启 $restartCount/$MaxRestarts 次, 停止自动重启. 进度 $($progress.N)/$($progress.Total). 查看 alerts.log 和 $($state.LogPath)." `
                -Severity alert -AlertLogFile $alertLog -Popup $true
            @{ exit_reason = 'max_restarts_exceeded'; n = $progress.N; total = $progress.Total; restarts = $restartCount; ended_at = $now.ToString('o') } `
                | ConvertTo-Json | Out-File $stateFile -Encoding UTF8
            Write-WdLog "=== 耗尽重启额度, watchdog 退出 (等人工) ===" Red
            break
        }

        $restartCount++
        # 中途事件 → 只记 log, 不弹窗 (睡觉时不打扰)
        Send-BrainAlert -Title "PDF Production 崩, 自动重启 $restartCount/$MaxRestarts" `
            -Message "PID $($state.Pid) 死于 $($progress.N)/$($progress.Total). 正在重启." `
            -Severity warn -AlertLogFile $alertLog -Popup $false

        try {
            $newPid = Restart-Pipeline
            Start-Sleep -Seconds 10  # 给新进程站稳的时间
            $newProc = Get-Process -Id $newPid -ErrorAction SilentlyContinue
            if ($newProc) {
                Write-WdLog "  重启后 PID $newPid 活着" Green
            } else {
                Write-WdLog "  !! 重启后进程立刻退出, 5 秒后轮询会再 crash 路径处理" Red
            }
        } catch {
            # 重启失败是中途事件 (下次轮询会再试), 只记 log
            Send-BrainAlert -Title '重启本身失败' `
                -Message "Start-Process 抛异常: $_" -Severity alert -AlertLogFile $alertLog -Popup $false
            Write-WdLog "重启失败: $_" Red
        }

        Start-Sleep -Seconds $CheckIntervalSec
        continue
    }

    # ---- 进程活着, 但检查是否卡住 (中途事件 → 只记 log) ----
    if ($sinceWriteMin -gt $StallMinutes) {
        Write-WdLog "!? PID $($state.Pid) 活但卡住: log $sinceWriteMin 分钟没动, 进度 $($progress.N)/$($progress.Total)" Yellow
        Send-BrainAlert -Title "PDF Production 疑卡住" `
            -Message "PID $($state.Pid) 活, 但 log $sinceWriteMin 分钟没更新. 进度 $($progress.N)/$($progress.Total)." `
            -Severity warn -AlertLogFile $alertLog -Popup $false
    }

    # ---- 心跳 (每 30 min) ----
    if (($now - $lastHeartbeat).TotalMinutes -ge 30) {
        $hb = @{
            ts = $now.ToString('o')
            pid = $state.Pid
            alive = $true
            progress = "$($progress.N)/$($progress.Total)"
            log_path = $state.LogPath
            log_age_min = $sinceWriteMin
            restarts_so_far = $restartCount
            uptime_hr = [math]::Round(($now - $startedAt).TotalHours, 2)
        }
        $hb | ConvertTo-Json | Out-File $heartbeatFile -Encoding UTF8
        Write-WdLog "♥ heartbeat: $($progress.N)/$($progress.Total), log_age ${sinceWriteMin}m, restarts=$restartCount" DarkCyan
        $lastHeartbeat = $now
    }

    Start-Sleep -Seconds $CheckIntervalSec
}
