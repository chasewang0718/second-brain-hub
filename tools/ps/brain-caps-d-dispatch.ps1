# =============================================================================
# brain-caps-d-dispatch.ps1
#
# Caps+D (AHK) → PowerShell gsave 的统一分派逻辑。
# 三件套：PDF / image / audio → brain *-inbox-ingest --path <file>
# 兜底：    text                → 走旧 gsave 文本分支 (paste-*.md)
#
# 设计约束:
#   - 懒加载 Windows.Forms (调用一次 LoadWithPartialName 后即在当前 session 常驻)
#   - 整段 Try/Catch 隔离, 分派失败 → 降级到文本分支, 不丢数据
#   - 单一入口函数 Invoke-BrainCapsDSave;  user profile dot-sources 本文件即可
#   - 真正的文件 copy + pointer card 交给 Python CLI, PS 只做协议 / 分派
#
# 使用示例 (在用户 PowerShell profile 里):
#   . "C:\dev-projects\second-brain-hub\tools\ps\brain-caps-d-dispatch.ps1"
#   function gsave { Invoke-BrainCapsDSave @args }
# =============================================================================

# 扩展名 → brain 子命令的映射表 (大小写不敏感; 以 `. ` 开头)
$script:BrainCapsDDispatchMap = @{
    # PDF
    '.pdf'  = 'pdf-inbox-ingest'
    # 图像 (与 brain_agents.image_inbox.SUPPORTED_EXT 对齐)
    '.png'  = 'image-inbox-ingest'
    '.jpg'  = 'image-inbox-ingest'
    '.jpeg' = 'image-inbox-ingest'
    '.webp' = 'image-inbox-ingest'
    '.bmp'  = 'image-inbox-ingest'
    '.tif'  = 'image-inbox-ingest'
    '.tiff' = 'image-inbox-ingest'
    # 音频 (与 brain_agents.audio_inbox.SUPPORTED_EXT 对齐)
    '.mp3'  = 'audio-inbox-ingest'
    '.wav'  = 'audio-inbox-ingest'
    '.m4a'  = 'audio-inbox-ingest'
    '.flac' = 'audio-inbox-ingest'
    '.ogg'  = 'audio-inbox-ingest'
    '.oga'  = 'audio-inbox-ingest'
    '.webm' = 'audio-inbox-ingest'
    '.aac'  = 'audio-inbox-ingest'
    '.opus' = 'audio-inbox-ingest'
}

# 预计算: 按子命令分组, 便于单次批量调用 (一次 Python 启动一个文件组)
function Get-BrainCapsDHandler {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$Path
    )
    $ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    if ($script:BrainCapsDDispatchMap.ContainsKey($ext)) {
        return [PSCustomObject]@{
            Extension  = $ext
            Subcommand = $script:BrainCapsDDispatchMap[$ext]
            Supported  = $true
        }
    }
    return [PSCustomObject]@{
        Extension  = $ext
        Subcommand = $null
        Supported  = $false
    }
}

# 获取剪贴板中的 file drop 列表; 失败返回 $null 而非抛出, 让调用方降级.
function Get-BrainCapsDFileList {
    [CmdletBinding()]
    param()
    try {
        [void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms')
    } catch {
        return $null
    }
    try {
        if (-not [System.Windows.Forms.Clipboard]::ContainsFileDropList()) {
            return $null
        }
        $drop = [System.Windows.Forms.Clipboard]::GetFileDropList()
        if (-not $drop -or $drop.Count -eq 0) {
            return $null
        }
        $out = New-Object System.Collections.Generic.List[string]
        foreach ($p in $drop) {
            if ($p -and (Test-Path -LiteralPath $p -PathType Leaf)) {
                $out.Add([string]$p)
            }
        }
        if ($out.Count -eq 0) { return $null }
        return $out.ToArray()
    } catch {
        return $null
    }
}

# 实际分派: 把同扩展名/子命令的文件汇成一次 brain 调用.
# 返回: 每个文件一条 [PSCustomObject]@{Path; Handler; ExitCode; Raw}
function Invoke-BrainCapsDDispatch {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$Files,
        [string]$BrainRepo = 'C:\dev-projects\second-brain-hub\tools\py',
        [switch]$WhatIf
    )
    $groups = @{}
    $unsupported = @()
    foreach ($f in $Files) {
        $h = Get-BrainCapsDHandler -Path $f
        if (-not $h.Supported) {
            $unsupported += [PSCustomObject]@{Path=$f; Reason="unsupported_ext:$($h.Extension)"}
            continue
        }
        if (-not $groups.ContainsKey($h.Subcommand)) {
            $groups[$h.Subcommand] = New-Object System.Collections.Generic.List[string]
        }
        $groups[$h.Subcommand].Add($f)
    }

    $results = New-Object System.Collections.Generic.List[object]
    foreach ($sub in $groups.Keys) {
        $paths = $groups[$sub]
        $args = New-Object System.Collections.Generic.List[string]
        $args.Add('-m'); $args.Add('uv'); $args.Add('run')
        $args.Add('--directory'); $args.Add($BrainRepo)
        $args.Add('brain'); $args.Add($sub)
        foreach ($p in $paths) {
            $args.Add('--path'); $args.Add($p)
        }
        if ($WhatIf) {
            Write-Host "[whatif] python $($args -join ' ')" -ForegroundColor DarkGray
            foreach ($p in $paths) {
                $results.Add([PSCustomObject]@{Path=$p; Subcommand=$sub; ExitCode=0; Raw='[whatif]'})
            }
            continue
        }
        $raw = & python @args 2>&1 | Out-String
        $exit = $LASTEXITCODE
        foreach ($p in $paths) {
            $results.Add([PSCustomObject]@{Path=$p; Subcommand=$sub; ExitCode=$exit; Raw=$raw})
        }
        if ($exit -eq 0 -and -not $WhatIf) {
            $tmp = [System.IO.Path]::GetTempFileName()
            try {
                $detailObj = @{ subcommand = $sub; paths = @($paths | ForEach-Object { $_.ToString() }) }
                $detailJson = $detailObj | ConvertTo-Json -Compress -Depth 6
                [System.IO.File]::WriteAllText($tmp, $detailJson, [System.Text.UTF8Encoding]::new($false))
                $targs = @(
                    '-m', 'uv', 'run', '--directory', $BrainRepo,
                    'brain', 'telemetry-append',
                    '--source', 'caps-d-dispatch',
                    '--event', 'file-inbox-ingest',
                    '--detail-file', $tmp
                )
                & python @targs 2>$null | Out-Null
            } finally {
                if (Test-Path -LiteralPath $tmp) {
                    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }
    foreach ($u in $unsupported) {
        $results.Add([PSCustomObject]@{Path=$u.Path; Subcommand=$null; ExitCode=-1; Raw=$u.Reason})
    }
    return $results.ToArray()
}

# 主入口. 返回布尔: $true = 已按文件分支处理完毕; $false = 未检测到文件, 调用方应走文本分支.
function Invoke-BrainCapsDSave {
    [CmdletBinding()]
    param(
        [string]$BrainRepo = 'C:\dev-projects\second-brain-hub\tools\py',
        [switch]$WhatIf
    )
    $files = Get-BrainCapsDFileList
    if (-not $files) {
        return $false
    }
    Write-Host "📎 Caps+D: detected $($files.Count) file(s) on clipboard, dispatching..." -ForegroundColor Cyan
    $results = Invoke-BrainCapsDDispatch -Files $files -BrainRepo $BrainRepo -WhatIf:$WhatIf
    foreach ($r in $results) {
        if ($r.Subcommand) {
            $color = if ($r.ExitCode -eq 0) { 'Green' } else { 'Yellow' }
            Write-Host ("   [{0,-18}] exit={1} {2}" -f $r.Subcommand, $r.ExitCode, $r.Path) -ForegroundColor $color
        } else {
            Write-Host ("   [skip              ] {0}  ({1})" -f $r.Path, $r.Raw) -ForegroundColor DarkYellow
        }
    }
    return $true
}
