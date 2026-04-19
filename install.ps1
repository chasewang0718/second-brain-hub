#Requires -Version 5.1
<#
.SYNOPSIS
    second-brain-hub 新机器一键部署脚本.

.DESCRIPTION
    1. 把 tools/Microsoft.PowerShell_profile.ps1.reference 复制到 $PROFILE (UTF-8 BOM)
    2. 在 Windows 启动目录创建 AHK 脚本的快捷方式 (指向 tools/ahk/)
    3. (可选) 立即启动两个 AHK 脚本
    4. 注册 BrainWeeklyReport 任务计划程序 (每周日 21:00 自动生成周报)

.NOTES
    前提:
      - PowerShell 5.1+ (Windows 自带)
      - 执行策略 RemoteSigned: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
      - AutoHotkey v2 已装: winget install AutoHotkey.AutoHotkey

    在任何工作目录都可以运行, 脚本内部用自身路径定位资源.
#>

[CmdletBinding()]
param(
    [switch]$SkipStartupShortcuts,
    [switch]$SkipLaunch,
    [switch]$SkipWeeklyTask
)

# ============================================================
# 定位
# ============================================================
$REPO_ROOT = $PSScriptRoot
$AHK_SRC = Join-Path $REPO_ROOT "tools\ahk"
$PROFILE_SRC = Join-Path $REPO_ROOT "tools\Microsoft.PowerShell_profile.ps1.reference"
$STARTUP_DIR = [Environment]::GetFolderPath("Startup")
$AHK_EXE = "C:\Program Files\AutoHotkey\v2\AutoHotkey.exe"

Write-Host "`n==== second-brain-hub install ====" -ForegroundColor Cyan
Write-Host "仓库路径: $REPO_ROOT" -ForegroundColor DarkGray
Write-Host ""

# ============================================================
# 1. 检查依赖
# ============================================================
if (-not (Test-Path $AHK_EXE)) {
    Write-Host "❌ 未找到 AutoHotkey v2: $AHK_EXE" -ForegroundColor Red
    Write-Host "   先运行: winget install --id=AutoHotkey.AutoHotkey" -ForegroundColor Yellow
    exit 1
}
Write-Host "✓ AutoHotkey v2 已装" -ForegroundColor Green

# ============================================================
# 2. 部署 PowerShell Profile (UTF-8 with BOM)
# ============================================================
Write-Host "`n[1/3] 部署 PowerShell Profile" -ForegroundColor Cyan
$profileDir = Split-Path $PROFILE
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    Write-Host "  创建目录: $profileDir" -ForegroundColor DarkGray
}
$raw = [System.IO.File]::ReadAllText($PROFILE_SRC, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($PROFILE, $raw, [System.Text.UTF8Encoding]::new($true))
Write-Host "  ✓ Profile 已复制到 $PROFILE (UTF-8 BOM)" -ForegroundColor Green

# ============================================================
# 3. 启动目录快捷方式
# ============================================================
if (-not $SkipStartupShortcuts) {
    Write-Host "`n[2/3] 创建启动目录快捷方式" -ForegroundColor Cyan
    $shell = New-Object -ComObject WScript.Shell

    $shortcuts = @(
        @{ Name = "Chase202602.ahk"; Script = "Chase202602.ahk" },
        @{ Name = "gsave-hotkey.ahk"; Script = "gsave-hotkey.ahk" }
    )

    foreach ($s in $shortcuts) {
        $lnkPath = Join-Path $STARTUP_DIR "$($s.Name).lnk"
        $ahkPath = Join-Path $AHK_SRC $s.Script
        $sc = $shell.CreateShortcut($lnkPath)
        $sc.TargetPath = $AHK_EXE
        $sc.Arguments = "`"$ahkPath`""
        $sc.WorkingDirectory = $AHK_SRC
        $sc.Description = "second-brain-hub: $($s.Script)"
        $sc.Save()
        Write-Host "  ✓ $lnkPath → $ahkPath" -ForegroundColor Green
    }
}
else {
    Write-Host "`n[2/3] (已跳过启动目录快捷方式)" -ForegroundColor DarkGray
}

# ============================================================
# 4. 启动 AHK 脚本
# ============================================================
if (-not $SkipLaunch) {
    Write-Host "`n[3/3] 启动 AHK 脚本" -ForegroundColor Cyan

    Get-Process AutoHotkey64 -ErrorAction SilentlyContinue | ForEach-Object {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
        if ($cmdline -match "Chase202602\.ahk" -or $cmdline -match "gsave-hotkey\.ahk") {
            Write-Host "  停止旧进程 PID=$($_.Id)" -ForegroundColor DarkYellow
            Stop-Process -Id $_.Id -Force
        }
    }
    Start-Sleep -Milliseconds 300

    Start-Process $AHK_EXE -ArgumentList "`"$AHK_SRC\Chase202602.ahk`""
    Start-Process $AHK_EXE -ArgumentList "`"$AHK_SRC\gsave-hotkey.ahk`""
    Start-Sleep -Milliseconds 500

    $running = Get-Process AutoHotkey64 -ErrorAction SilentlyContinue
    Write-Host "  ✓ 已启动 $($running.Count) 个 AHK 进程" -ForegroundColor Green
}
else {
    Write-Host "`n[3/3] (已跳过启动)" -ForegroundColor DarkGray
}

# ============================================================
# 5. 注册周报任务计划程序 (BrainWeeklyReport, 每周日 21:00)
# ============================================================
if (-not $SkipWeeklyTask) {
    Write-Host "`n[4/4] 注册周报任务 (BrainWeeklyReport, 每周日 21:00)" -ForegroundColor Cyan
    $registerScript = Join-Path $REPO_ROOT "tools\health\register-weekly-task.ps1"
    if (Test-Path $registerScript) {
        try {
            & $registerScript | Out-Null
            Write-Host "  ✓ 任务已注册 (查看: Get-ScheduledTask BrainWeeklyReport)" -ForegroundColor Green
        }
        catch {
            Write-Host "  ⚠️  注册失败: $($_.Exception.Message)" -ForegroundColor Yellow
            Write-Host "     可事后手动跑: $registerScript" -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host "  ⚠️  找不到 $registerScript, 跳过" -ForegroundColor Yellow
    }
}
else {
    Write-Host "`n[4/4] (已跳过周报任务注册)" -ForegroundColor DarkGray
}

Write-Host "`n==== 部署完成 ====" -ForegroundColor Cyan
Write-Host "下一步:" -ForegroundColor DarkGray
Write-Host "  1. 打开新 PowerShell 窗口 (Profile 自动加载, 可用 gsave / ginbox / brain-ask / g-ask)" -ForegroundColor DarkGray
Write-Host "  2. 测试热键: CapsLock+D (先往剪贴板放内容)" -ForegroundColor DarkGray
Write-Host "  3. 测试 Chase202602: Tab+W / CapsLock+S / ;mail" -ForegroundColor DarkGray
Write-Host "  4. 登录 cursor-agent: agent login (首次必须, 不然 agent 类函数不工作)" -ForegroundColor DarkGray
Write-Host ""
