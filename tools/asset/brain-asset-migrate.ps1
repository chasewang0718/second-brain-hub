#Requires -Version 5.1
<#
.SYNOPSIS
    扫描 / 迁移外部资产到 D:\brain-assets\.

.DESCRIPTION
    三个模式:
      -DryRun     (默认) 只扫描生成 manifest, 不动任何文件
      -Execute    按 manifest 执行 (copy, 保留原文件)
      -Verify     只跑 manifest 的健康检查, 不改动

    流程:
      1. 加载黑名单 ~/.brain-exclude.txt
      2. 枚举 -Source 下所有文件
      3. 逐个匹配规则, 生成 manifest 行
      4. DryRun: 写 _migration/<job>-manifest.tsv 完事
      5. Execute: 按 manifest copy + 汇总报告

    规则 (Phase 2.2 纯规则版, 0 token):
      .jpg/.jpeg/.png/.gif/.bmp     → 10-photos/YYYY-MM/  (按 EXIF, fallback mtime)
      .heic                         → 10-photos/YYYY-MM/
      .mp4/.mov/.avi/.mkv/.webm     → 12-video/YYYY-MM/   (按 mtime)
      .m4a/.mp3/.wav/.flac/.ogg     → 13-audio/           (flat)
      .ttf/.otf/.woff/.woff2        → 11-fonts/           (flat)
      .zip/.rar/.7z/.tar.gz         → 14-archives/        (flat)
      .txt/.md/.rtf/.log<small>     → brain-inbox         (进 D:\brain\99-inbox\)
      .pdf                          → 99-inbox/           (Phase 2.3 AI 处理)
      .tex                          → brain-inbox (走 Tier A)
      .aux/.aae/.DS_Store/Thumbs.db → trash (标为删除, 不自动执行)
      其他                           → 98-staging/         (等 agent/用户手动决定)

.PARAMETER Source
    要扫描的源目录 (例如 "D:\BaiduSyncdisk").

.PARAMETER JobName
    任务标识, 用于 manifest 文件名. 默认用时间戳.

.PARAMETER DryRun
    默认行为. 只扫描生成 manifest.

.PARAMETER Execute
    按最近一份 manifest 执行实际迁移.

.PARAMETER ManifestPath
    指定 manifest 文件 (配合 -Execute / -Verify). 默认用最新的.

.EXAMPLE
    # Stage 1: 扫描 (0 token)
    .\brain-asset-migrate.ps1 -Source D:\BaiduSyncdisk -JobName baidu-2026-04

.EXAMPLE
    # Review manifest 后 execute
    .\brain-asset-migrate.ps1 -Execute -ManifestPath D:\brain-assets\_migration\baidu-2026-04-manifest.tsv
#>

[CmdletBinding()]
param(
    [Parameter(ParameterSetName='Scan')]
    [string]$Source,

    [Parameter(ParameterSetName='Scan')]
    [string]$JobName = "job-$(Get-Date -Format 'yyyyMMdd-HHmmss')",

    [Parameter(ParameterSetName='Scan')]
    [switch]$DryRun = $true,

    [Parameter(ParameterSetName='Execute')]
    [switch]$Execute,

    [Parameter(ParameterSetName='Verify')]
    [switch]$Verify,

    [Parameter(ParameterSetName='Execute')]
    [Parameter(ParameterSetName='Verify')]
    [string]$ManifestPath
)

# ============================================================
# 配置
# ============================================================
$ASSETS_ROOT = "D:\brain-assets"
$BRAIN_ROOT  = "D:\brain"
$MIGRATION_DIR = Join-Path $ASSETS_ROOT "_migration"
$EXCLUDE_FILE = "$env:USERPROFILE\.brain-exclude.txt"

if (-not (Test-Path $ASSETS_ROOT)) {
    Write-Host "❌ $ASSETS_ROOT 不存在, 请先建" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $MIGRATION_DIR)) {
    New-Item $MIGRATION_DIR -ItemType Directory -Force | Out-Null
}

# ============================================================
# 加载 Tier C 黑名单
# ============================================================
function Load-ExcludeList {
    if (-not (Test-Path $EXCLUDE_FILE)) {
        return @()
    }
    $lines = Get-Content $EXCLUDE_FILE -Encoding UTF8
    return $lines | ForEach-Object {
        $l = $_.Trim()
        if ($l -and -not $l.StartsWith("#")) { $l }
    } | Where-Object { $_ }
}

function Test-Excluded($path, $excludeList) {
    foreach ($rule in $excludeList) {
        $ruleNorm = $rule.Replace('/', '\').TrimEnd('\')
        $pathNorm = $path.Replace('/', '\')
        if ($pathNorm.StartsWith($ruleNorm, [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
        if ($pathNorm -like $rule) {
            return $true
        }
    }
    return $false
}

# ============================================================
# 照片 EXIF 日期提取 (fallback mtime)
# ============================================================
Add-Type -AssemblyName System.Drawing -ErrorAction SilentlyContinue
function Get-PhotoDate($file) {
    try {
        $img = [System.Drawing.Image]::FromFile($file.FullName)
        try {
            $prop = $img.GetPropertyItem(36867)  # DateTimeOriginal
            $raw = [System.Text.Encoding]::ASCII.GetString($prop.Value).Trim([char]0)
            $dt = [DateTime]::ParseExact($raw, "yyyy:MM:dd HH:mm:ss", $null)
            return @{ Date = $dt; Source = "exif" }
        }
        finally { $img.Dispose() }
    }
    catch {
        return @{ Date = $file.LastWriteTime; Source = "mtime" }
    }
}

# ============================================================
# 分类规则
# ============================================================
function Classify-File($file) {
    $ext = $file.Extension.ToLowerInvariant()

    # 照片
    if ($ext -in @('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic')) {
        $info = Get-PhotoDate $file
        $ym = $info.Date.ToString('yyyy-MM')
        return @{
            Rule     = 'photo'
            TargetDir = "10-photos\$ym"
            NewName   = $file.Name
            DateSource = $info.Source
            Action   = 'copy'
        }
    }
    # 视频
    if ($ext -in @('.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.m4v')) {
        $ym = $file.LastWriteTime.ToString('yyyy-MM')
        return @{
            Rule     = 'video'
            TargetDir = "12-video\$ym"
            NewName   = $file.Name
            DateSource = 'mtime'
            Action   = 'copy'
        }
    }
    # 音频
    if ($ext -in @('.m4a', '.mp3', '.wav', '.flac', '.ogg', '.aac', '.wma')) {
        return @{
            Rule     = 'audio'
            TargetDir = "13-audio"
            NewName   = $file.Name
            DateSource = '-'
            Action   = 'copy'
        }
    }
    # 字体
    if ($ext -in @('.ttf', '.otf', '.woff', '.woff2')) {
        return @{
            Rule     = 'font'
            TargetDir = "11-fonts"
            NewName   = $file.Name
            DateSource = '-'
            Action   = 'copy'
        }
    }
    # 压缩包
    if ($ext -in @('.zip', '.rar', '.7z', '.tgz', '.tar')) {
        return @{
            Rule     = 'archive'
            TargetDir = "14-archives"
            NewName   = $file.Name
            DateSource = '-'
            Action   = 'copy'
        }
    }
    # 文本 → Tier A (brain 仓)
    if ($ext -in @('.txt', '.md', '.rtf', '.tex')) {
        return @{
            Rule     = 'text'
            TargetDir = "__BRAIN_INBOX__"  # 特殊 sentinel
            NewName   = $file.Name
            DateSource = '-'
            Action   = 'copy-to-brain-inbox'
        }
    }
    # 垃圾 / 系统文件
    if ($ext -in @('.aae', '.aux', '.log', '.DS_Store', '.tmp', '.bak') -or
        $file.Name -in @('Thumbs.db', 'desktop.ini')) {
        return @{
            Rule     = 'trash'
            TargetDir = '-'
            NewName   = '-'
            DateSource = '-'
            Action   = 'trash-candidate'
        }
    }
    # PDF → inbox 等 Phase 2.3
    if ($ext -eq '.pdf') {
        return @{
            Rule     = 'pdf'
            TargetDir = "99-inbox"
            NewName   = $file.Name
            DateSource = '-'
            Action   = 'copy-to-assets-inbox'
        }
    }
    # 文档 (docx, xlsx, etc.)
    if ($ext -in @('.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt')) {
        return @{
            Rule     = 'document'
            TargetDir = "99-inbox"
            NewName   = $file.Name
            DateSource = '-'
            Action   = 'copy-to-assets-inbox'
        }
    }
    # 其他 → staging
    return @{
        Rule     = 'other'
        TargetDir = "98-staging"
        NewName   = $file.Name
        DateSource = '-'
        Action   = 'copy'
    }
}

# ============================================================
# SCAN 模式 (Stage 1)
# ============================================================
function Invoke-Scan {
    param([string]$src, [string]$job)

    if (-not (Test-Path $src)) {
        Write-Host "❌ 源目录不存在: $src" -ForegroundColor Red
        return
    }

    Write-Host "`n==== brain-asset Stage 1: 扫描 ====" -ForegroundColor Cyan
    Write-Host "源目录:   $src" -ForegroundColor DarkGray
    Write-Host "任务名:   $job" -ForegroundColor DarkGray

    $excludeList = Load-ExcludeList
    if ($excludeList.Count -gt 0) {
        Write-Host "黑名单:   $($excludeList.Count) 条规则 (from $EXCLUDE_FILE)" -ForegroundColor DarkGray
    }
    else {
        Write-Host "黑名单:   (空, 无 Tier C 排除)" -ForegroundColor DarkGray
    }

    $manifestFile = Join-Path $MIGRATION_DIR "$job-manifest.tsv"

    Write-Host "`n枚举文件中..." -ForegroundColor Cyan
    $allFiles = Get-ChildItem $src -Recurse -File -ErrorAction SilentlyContinue
    Write-Host "  发现 $($allFiles.Count) 个文件" -ForegroundColor DarkGray

    Write-Host "`n分类中..." -ForegroundColor Cyan
    $rows = @()
    $excludedCount = 0
    $i = 0
    foreach ($f in $allFiles) {
        $i++
        if ($i % 500 -eq 0) {
            Write-Host "  进度: $i / $($allFiles.Count)" -ForegroundColor DarkGray
        }

        if (Test-Excluded $f.FullName $excludeList) {
            $excludedCount++
            continue
        }

        $c = Classify-File $f
        $rows += [PSCustomObject]@{
            source_path    = $f.FullName
            size_kb        = [Math]::Round($f.Length / 1KB, 1)
            mtime          = $f.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
            ext            = $f.Extension.ToLowerInvariant()
            rule           = $c.Rule
            action         = $c.Action
            target_dir     = $c.TargetDir
            new_name       = $c.NewName
            date_source    = $c.DateSource
            note           = ''
        }
    }

    Write-Host "`n==== 分类汇总 ====" -ForegroundColor Cyan
    $rows | Group-Object rule | Sort-Object Count -Descending | ForEach-Object {
        $sz = [Math]::Round((($_.Group | Measure-Object size_kb -Sum).Sum) / 1024, 1)
        Write-Host ("  {0,-10} {1,6} 文件  {2,10} MB" -f $_.Name, $_.Count, $sz) -ForegroundColor Gray
    }
    if ($excludedCount -gt 0) {
        Write-Host "  (黑名单排除: $excludedCount)" -ForegroundColor DarkYellow
    }

    $rows | Export-Csv -Path $manifestFile -Delimiter "`t" -NoTypeInformation -Encoding UTF8

    Write-Host "`n✅ Manifest 已写入: " -ForegroundColor Green -NoNewline
    Write-Host $manifestFile -ForegroundColor Cyan
    Write-Host "`n下一步:" -ForegroundColor DarkGray
    Write-Host "  1. 用 Excel / VSCode 打开 manifest 检查" -ForegroundColor DarkGray
    Write-Host "  2. 手改任何 target_dir / action 不对的行" -ForegroundColor DarkGray
    Write-Host "  3. 执行: .\brain-asset-migrate.ps1 -Execute -ManifestPath '$manifestFile'" -ForegroundColor DarkGray
}

# ============================================================
# EXECUTE 模式 (Stage 3)
# ============================================================
function Invoke-Execute {
    param([string]$manifest)

    if (-not $manifest) {
        $manifest = Get-ChildItem $MIGRATION_DIR -Filter "*-manifest.tsv" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $manifest) {
            Write-Host "❌ 没找到 manifest, 请先 scan" -ForegroundColor Red; return
        }
        $manifest = $manifest.FullName
    }
    if (-not (Test-Path $manifest)) {
        Write-Host "❌ Manifest 不存在: $manifest" -ForegroundColor Red; return
    }

    Write-Host "`n==== brain-asset Stage 3: 执行迁移 ====" -ForegroundColor Cyan
    Write-Host "Manifest: $manifest" -ForegroundColor DarkGray

    $rows = Import-Csv -Path $manifest -Delimiter "`t" -Encoding UTF8
    Write-Host "共 $($rows.Count) 行" -ForegroundColor DarkGray

    $stats = @{
        copied = 0
        skipped = 0
        failed = 0
        trashMarked = 0
        toBrainInbox = 0
    }
    $logFile = $manifest.Replace('-manifest.tsv', '-execute.log')
    "=== Execute start $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $logFile -Encoding UTF8

    $i = 0
    foreach ($row in $rows) {
        $i++
        if ($i % 200 -eq 0) {
            Write-Host "  进度: $i / $($rows.Count) (copied=$($stats.copied), skipped=$($stats.skipped), failed=$($stats.failed))" -ForegroundColor DarkGray
        }

        if ($row.action -eq 'trash-candidate') {
            $stats.trashMarked++
            "TRASH-CANDIDATE`t$($row.source_path)" | Out-File $logFile -Append -Encoding UTF8
            continue
        }

        if (-not (Test-Path $row.source_path)) {
            $stats.skipped++
            "SOURCE-MISSING`t$($row.source_path)" | Out-File $logFile -Append -Encoding UTF8
            continue
        }

        # 决定目标根
        if ($row.target_dir -eq '__BRAIN_INBOX__') {
            $destRoot = Join-Path $BRAIN_ROOT "99-inbox"
            $stats.toBrainInbox++
        }
        else {
            $destRoot = Join-Path $ASSETS_ROOT $row.target_dir
        }

        if (-not (Test-Path $destRoot)) {
            New-Item -Path $destRoot -ItemType Directory -Force | Out-Null
        }
        $destPath = Join-Path $destRoot $row.new_name

        # 重名处理: 加 -YYYYMMDD-HHMMSS 后缀
        if (Test-Path $destPath) {
            $base = [System.IO.Path]::GetFileNameWithoutExtension($row.new_name)
            $ext  = [System.IO.Path]::GetExtension($row.new_name)
            $srcMtime = (Get-Item $row.source_path).LastWriteTime.ToString('yyyyMMdd-HHmmss')
            $destPath = Join-Path $destRoot "$base-$srcMtime$ext"
        }

        try {
            Copy-Item -Path $row.source_path -Destination $destPath -Force -ErrorAction Stop
            (Get-Item $destPath).LastWriteTime = (Get-Item $row.source_path).LastWriteTime
            $stats.copied++
            "OK`t$($row.source_path)`t→`t$destPath" | Out-File $logFile -Append -Encoding UTF8
        }
        catch {
            $stats.failed++
            "FAIL`t$($row.source_path)`t$($_.Exception.Message)" | Out-File $logFile -Append -Encoding UTF8
        }
    }

    "=== Execute done $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $logFile -Append -Encoding UTF8

    Write-Host "`n==== 执行完成 ====" -ForegroundColor Cyan
    Write-Host "  ✓ 已 copy 到 brain-assets:   $($stats.copied)" -ForegroundColor Green
    Write-Host "  📥 已 copy 到 brain 99-inbox: $($stats.toBrainInbox)" -ForegroundColor Cyan
    Write-Host "  🗑  垃圾候选 (仅标记):       $($stats.trashMarked)" -ForegroundColor DarkYellow
    Write-Host "  ⚠  源文件缺失:              $($stats.skipped)" -ForegroundColor DarkYellow
    Write-Host "  ❌ 失败:                     $($stats.failed)" -ForegroundColor Red
    Write-Host "`n日志: $logFile" -ForegroundColor DarkGray
    Write-Host "`n提醒: 原位置文件保留 (未删). 确认 7 天无问题后再手动清理.`n" -ForegroundColor Cyan
}

# ============================================================
# 入口
# ============================================================
if ($Execute) {
    Invoke-Execute -manifest $ManifestPath
}
elseif ($Verify) {
    Write-Host "Verify 模式尚未实现 (Phase 2.3 会加)" -ForegroundColor Yellow
}
else {
    if (-not $Source) {
        Write-Host "❌ 需要 -Source <路径>. 见 Get-Help .\brain-asset-migrate.ps1 -Examples" -ForegroundColor Red
        exit 1
    }
    Invoke-Scan -src $Source -job $JobName
}
