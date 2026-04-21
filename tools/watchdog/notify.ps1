#Requires -Version 5.1
<#
.SYNOPSIS
    Silent notification helpers: Windows MessageBox only, no sound.

.DESCRIPTION
    设计意图: 用户睡觉时不要被打扰. 所有通知:
        - 无声音 (无 beep, 无系统音)
        - MessageBox 是非阻塞的 (另起 PS 进程弹, 不卡 watchdog)
        - 屏幕锁着不会强行点亮, 早上解锁才看到

.EXAMPLE
    . .\notify.ps1
    Send-BrainAlert -Title "PDF Production 完成" -Message "654/655, 重启 0 次"
#>

function Show-BrainMessageBox {
    <#
    .SYNOPSIS
        静默 MessageBox (icon=None = 无系统音). 非阻塞: 启子进程显示, 主 watchdog 继续跑.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$Title,
        [Parameter(Mandatory)] [string]$Message
    )
    try {
        # 经过转义的单引号, 避免 $Message 含 ' 时 PS 命令串崩
        $escTitle = $Title -replace "'", "''"
        $escMsg   = $Message -replace "'", "''"
        $cmd = "Add-Type -AssemblyName PresentationFramework; " +
               "`$null = [System.Windows.MessageBox]::Show('$escMsg','$escTitle','OK','None')"
        Start-Process powershell.exe `
            -ArgumentList @('-NoProfile','-WindowStyle','Hidden','-Command', $cmd) `
            -WindowStyle Hidden | Out-Null
        return $true
    } catch {
        Write-Warning "MessageBox 失败: $_"
        return $false
    }
}

function Send-BrainAlert {
    <#
    .SYNOPSIS
        静默通知: MessageBox + alert log. 永不发声.

    .PARAMETER Popup
        若 $false, 只写 alert log, 不弹 MessageBox (中途事件用).
        若 $true (默认), 同时弹 MessageBox (最终结局用).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$Title,
        [Parameter(Mandatory)] [string]$Message,
        [ValidateSet('alert','warn','done','info')] [string]$Severity = 'alert',
        [string]$AlertLogFile,
        [bool]$Popup = $true
    )

    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] [$Severity] $Title`n           $Message"
    Write-Host $line -ForegroundColor $(switch ($Severity) {
        'alert' { 'Red' }; 'warn' { 'Yellow' }; 'done' { 'Green' }; default { 'Cyan' }
    })

    if ($AlertLogFile) {
        try { $line | Add-Content -Path $AlertLogFile -Encoding UTF8 } catch {}
    }

    if ($Popup) {
        [void](Show-BrainMessageBox -Title $Title -Message $Message)
    }
}
