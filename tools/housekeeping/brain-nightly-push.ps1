#Requires -Version 5.1
<#
.SYNOPSIS
    每晚 22:00 自动把 D:\brain 和 second-brain-hub 的本地 commit 推到 GitHub.

.DESCRIPTION
    安全策略:
    - 只 push, 不 commit (commit 由人 / agent 主动触发)
    - 只 push 当前分支, 不 --force
    - 无未推送 commit 就静默跳过
    - 日志写到 D:\brain\.brain-nightly-push.log (.gitignore 已忽略)
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$logPath = "D:\brain\.brain-nightly-push.log"
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Log($line) {
    $msg = "[$ts] $line"
    Add-Content -Path $logPath -Value $msg -Encoding UTF8
    Write-Host $msg
}

function Push-Repo($repoPath) {
    if (-not (Test-Path $repoPath)) {
        Log "SKIP $repoPath (不存在)"
        return
    }
    Push-Location $repoPath
    try {
        $ahead = git rev-list "@{u}..HEAD" --count 2>$null
        if (-not $ahead -or $ahead -eq 0) {
            Log "OK $repoPath 无未推送 commit"
            return
        }
        Log "PUSH $repoPath ($ahead commits ahead)"
        $pushOut = git push 2>&1
        if ($LASTEXITCODE -eq 0) {
            Log "  -> success"
        } else {
            Log "  -> FAIL: $pushOut"
        }
    } catch {
        Log "ERROR $repoPath : $_"
    } finally {
        Pop-Location
    }
}

Log "==== brain nightly push ===="
Push-Repo "D:\brain"
Push-Repo "C:\dev-projects\second-brain-hub"
Log "==== done ===="
Log ""
