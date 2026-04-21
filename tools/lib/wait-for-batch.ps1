#Requires -Version 5.1
<#
.SYNOPSIS
    守护 Phase 2.3 批处理 PID, 结束后自动跑 overview-cards dry-run.

.DESCRIPTION
    循环 check Phase 2.3 PID 是否还活着:
    - 活着: 继续等 (默认每 5 分钟看一次)
    - 死了: 日志记录, 然后跑 brain-asset-overview-cards.ps1 (dry-run, 0 token)
      生成候选清单给用户 review, 用户决定是否 -Execute.

    watcher 本身很轻: 只是个 sleep + Get-Process loop.
    watcher 日志: D:\second-brain-content\.brain-watcher.log (gitignore 已忽略)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [int]$WatchPid,
    [string]$NextScript = "C:\dev-projects\second-brain-hub\tools\asset\brain-asset-overview-cards.ps1",
    [int]$PollSeconds = 300  # 5 min
)

$logPath = "D:\second-brain-content\.brain-watcher.log"

function Log($line) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logPath -Value "[$ts] $line" -Encoding UTF8
}

Log "==== watcher start, watching PID $WatchPid ===="

while ($true) {
    $p = Get-Process -Id $WatchPid -ErrorAction SilentlyContinue
    if (-not $p) {
        Log "PID $WatchPid 已退出, 启动下一任务: $NextScript"
        break
    }
    Start-Sleep -Seconds $PollSeconds
}

# PID 死了, 启动 overview dry-run
try {
    Log "run $NextScript (dry-run, MaxItems=20)"
    $out = & powershell -NoProfile -File $NextScript -MaxItems 20 2>&1 | Out-String
    Log "overview output:"
    Add-Content -Path $logPath -Value $out -Encoding UTF8
    Log "overview dry-run 完成, 用户可看报告后手动 -Execute"
} catch {
    Log "FAIL running overview: $_"
}

Log "==== watcher end ===="
