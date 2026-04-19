#Requires -Version 5.1
<#
.SYNOPSIS
    Reusable notification helpers: Windows toast + audio beep.
    Designed to be dot-sourced by watchdogs, batch jobs, etc.

.EXAMPLE
    . .\notify.ps1
    Show-BrainToast -Title "Production done" -Message "655/655 OK"
    Invoke-BrainBeep -Pattern 'alert'   # loud multi-tone, for waking user
    Invoke-BrainBeep -Pattern 'done'    # pleasant two-tone
#>

function Show-BrainToast {
    <#
    .SYNOPSIS
        Windows 10+ toast via native WinRT API. No 3rd-party module.
        Silently falls back to nothing on systems without WinRT.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$Title,
        [Parameter(Mandatory)] [string]$Message,
        [string]$AppId = 'Brain.SecondBrainHub'
    )
    try {
        $escTitle = [System.Security.SecurityElement]::Escape($Title)
        $escMsg   = [System.Security.SecurityElement]::Escape($Message)
        $xml = @"
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>$escTitle</text>
            <text>$escMsg</text>
        </binding>
    </visual>
</toast>
"@
        [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]
        [void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime]
        $xmlDoc = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xmlDoc.LoadXml($xml)
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xmlDoc)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show($toast)
        return $true
    } catch {
        Write-Warning "Toast 失败 (WinRT 不可用?): $_"
        return $false
    }
}

function Invoke-BrainBeep {
    <#
    .SYNOPSIS
        Audio alert. Patterns:
          - 'alert' : 3 loud tones, for crashes (tries to wake user)
          - 'warn'  : 2 medium tones, for stall warnings
          - 'done'  : 2 pleasant tones, for completion
    #>
    [CmdletBinding()]
    param([ValidateSet('alert','warn','done')] [string]$Pattern = 'alert')

    $tones = switch ($Pattern) {
        'alert' { @(@(1200,400), @(800,400), @(1200,400), @(800,400), @(1200,600)) }
        'warn'  { @(@(900,300), @(700,300)) }
        'done'  { @(@(700,200), @(1000,400)) }
    }

    try {
        foreach ($t in $tones) {
            [console]::Beep($t[0], $t[1])
            Start-Sleep -Milliseconds 80
        }
        return $true
    } catch {
        # [console]::Beep may fail in GUI-only contexts. Fallback: system sound.
        try {
            $wav = if ($Pattern -eq 'done') {
                "$env:WINDIR\Media\tada.wav"
            } else {
                "$env:WINDIR\Media\Alarm01.wav"
            }
            if (Test-Path $wav) {
                $player = New-Object Media.SoundPlayer $wav
                $player.PlaySync()
            }
            return $true
        } catch {
            Write-Warning "Beep + SoundPlayer 都失败: $_"
            return $false
        }
    }
}

function Send-BrainAlert {
    <#
    .SYNOPSIS
        Combined toast + audio + log-file append. Main entry point for watchdogs.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$Title,
        [Parameter(Mandatory)] [string]$Message,
        [ValidateSet('alert','warn','done','info')] [string]$Severity = 'alert',
        [string]$AlertLogFile
    )

    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] [$Severity] $Title`n           $Message"
    Write-Host $line -ForegroundColor $(switch ($Severity) {
        'alert' { 'Red' }; 'warn' { 'Yellow' }; 'done' { 'Green' }; default { 'Cyan' }
    })

    if ($AlertLogFile) {
        try { $line | Add-Content -Path $AlertLogFile -Encoding UTF8 } catch {}
    }

    [void](Show-BrainToast -Title $Title -Message $Message)

    if ($Severity -ne 'info') {
        $beepPattern = switch ($Severity) {
            'alert' { 'alert' }; 'warn' { 'warn' }; 'done' { 'done' }
        }
        [void](Invoke-BrainBeep -Pattern $beepPattern)
    }
}
