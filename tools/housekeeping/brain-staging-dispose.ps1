#Requires -Version 5.1
<#
.SYNOPSIS
    处置 D:\brain-assets\98-staging\ 113 个杂项 (L1 删除 + L2 聚类归档 + L3 候选).

.DESCRIPTION
    按 3 层处理:
      L1 规则删 (0 token): 游戏/fmt cache/synctex.gz/空文件/时间戳重复版本
      L2 规则聚类归档 (0 token): VBASync/ING/Anki/Python/LaTeX figures/InDesign+TIF
      L3 候选池输出 (给 agent 用): 不确定归属的少数

    每一步 dry-run 默认打开 (只记录不动), 加 -Execute 才真动.

.PARAMETER Execute
    真执行 (删 + 移). 默认 DryRun.

.PARAMETER SkipL1
    跳过 L1 (删).

.PARAMETER SkipL2
    跳过 L2 (聚类归档).
#>

[CmdletBinding()]
param(
    [switch]$Execute,
    [switch]$SkipL1,
    [switch]$SkipL2
)

$STAGING   = "D:\brain-assets\98-staging"
$ASSETS    = "D:\brain-assets"
$LOG       = Join-Path $ASSETS "_migration\98-staging-dispose.log"
$L3_LIST   = Join-Path $ASSETS "_migration\98-staging-l3-agent-list.txt"

$mode = if ($Execute) { "EXECUTE" } else { "DRY-RUN" }
"=== 98-staging dispose start $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$mode] ===" | Out-File $LOG -Encoding UTF8

Write-Host "`n==== 98-staging dispose [$mode] ====" -ForegroundColor Cyan

$stats = @{ deleted = 0; moved = 0; skipped = 0; failed = 0; l3 = 0 }

function Do-Delete($path, $reason) {
    if (-not (Test-Path -LiteralPath $path)) { return }
    if ($Execute) {
        try {
            Remove-Item -LiteralPath $path -Force -ErrorAction Stop
            "DELETE`t$reason`t$path" | Out-File $LOG -Append -Encoding UTF8
            $script:stats.deleted++
        }
        catch {
            "FAIL-DELETE`t$reason`t$path`t$($_.Exception.Message)" | Out-File $LOG -Append -Encoding UTF8
            $script:stats.failed++
        }
    }
    else {
        "WOULD-DELETE`t$reason`t$path" | Out-File $LOG -Append -Encoding UTF8
        $script:stats.deleted++
    }
}

function Do-Move($src, $destDir, $reason, $newName) {
    if (-not (Test-Path -LiteralPath $src)) { return }
    if (-not $newName) { $newName = Split-Path $src -Leaf }
    $dest = Join-Path $destDir $newName
    if ($Execute) {
        try {
            if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
            # 重名处理
            if (Test-Path -LiteralPath $dest) {
                $base = [System.IO.Path]::GetFileNameWithoutExtension($newName)
                $ext  = [System.IO.Path]::GetExtension($newName)
                $ts   = Get-Date -Format "yyyyMMdd-HHmmss"
                $dest = Join-Path $destDir "$base-$ts$ext"
            }
            Move-Item -LiteralPath $src -Destination $dest -Force -ErrorAction Stop
            "MOVE`t$reason`t$src`t=>`t$dest" | Out-File $LOG -Append -Encoding UTF8
            $script:stats.moved++
        }
        catch {
            "FAIL-MOVE`t$reason`t$src`t$($_.Exception.Message)" | Out-File $LOG -Append -Encoding UTF8
            $script:stats.failed++
        }
    }
    else {
        "WOULD-MOVE`t$reason`t$src`t=>`t$dest" | Out-File $LOG -Append -Encoding UTF8
        $script:stats.moved++
    }
}

# ============================================================
# L1: 规则删
# ============================================================
if (-not $SkipL1) {
    Write-Host "`n[L1] 规则清垃圾" -ForegroundColor Yellow

    # 1a. 游戏 (exe + apk + 游戏相关 reg)
    @(
        "植物大战僵尸杂交版v3.2.1安装程序.exe",
        "Plants_Vs_Zombies_V1.0.0.1051_CN_V2.exe",
        "植物大战僵尸修改器.exe",
        "（下载我）植物大战僵尸.apk",
        "【运行后打开游戏】窗口白屏卡死.reg"
    ) | ForEach-Object {
        Do-Delete (Join-Path $STAGING $_) "game-installer"
    }

    # 1b. LaTeX format cache (.fmt) - 可重建
    Get-ChildItem $STAGING -Filter "*.fmt" -File | ForEach-Object {
        Do-Delete $_.FullName "latex-fmt-cache-regeneratable"
    }

    # 1c. synctex.gz - LaTeX 编译产物, 可重建
    Get-ChildItem $STAGING -Filter "*.synctex*.gz" -File | ForEach-Object {
        Do-Delete $_.FullName "synctex-regeneratable"
    }

    # 1d. 空文件
    Get-ChildItem $STAGING -File | Where-Object { $_.Length -eq 0 } | ForEach-Object {
        Do-Delete $_.FullName "empty-file"
    }

    # 1e. ._00_ 孤儿备份
    Get-ChildItem $STAGING -File | Where-Object { $_.Name -like "*._00_" } | ForEach-Object {
        Do-Delete $_.FullName "orphan-backup"
    }

    # 1f. 早教资源库 URL 快捷方式 (大抵失效链接)
    Get-ChildItem $STAGING -Filter "*.url" -File | ForEach-Object {
        Do-Delete $_.FullName "stale-url-shortcut"
    }

    # 1g. 带 -YYYYMMDD-HHMMSS 时间戳的多版本: 同名有无时间戳版就留无时间戳的, 删带时间戳的
    # (安全做法: 只删 "base-YYYYMMDD-HHMMSS.ext" 模式, 且同目录存在 "base.ext")
    $tsPattern = '^(?<base>.+)-(?<ts>\d{8}-\d{6})(?<ext>\.[^.]+)$'
    Get-ChildItem $STAGING -File | Where-Object { $_.Name -match $tsPattern } | ForEach-Object {
        $m = [regex]::Match($_.Name, $tsPattern)
        $baseName = $m.Groups['base'].Value + $m.Groups['ext'].Value
        $baseCandidate = Join-Path $STAGING $baseName
        if (Test-Path -LiteralPath $baseCandidate) {
            Do-Delete $_.FullName "timestamp-duplicate-of:$baseName"
        }
    }

    # 1h. " copy" 后缀的 Python 重复
    Get-ChildItem $STAGING -Filter "* copy.py" -File | ForEach-Object {
        $baseName = $_.Name -replace ' copy\.py$', '.py'
        $baseCandidate = Join-Path $STAGING $baseName
        if (Test-Path -LiteralPath $baseCandidate) {
            Do-Delete $_.FullName "manual-copy-duplicate-of:$baseName"
        }
    }

    # 1i. "_冲突文件_" (百度云的冲突版本)
    Get-ChildItem $STAGING -File | Where-Object { $_.Name -match '_冲突文件_' } | ForEach-Object {
        Do-Delete $_.FullName "baidu-conflict-file"
    }
}

# ============================================================
# L2: 聚类归档
# ============================================================
if (-not $SkipL2) {
    Write-Host "`n[L2] 聚类归档" -ForegroundColor Yellow

    # 2a. VBASync VBA 项目 (cls + bas + frm + frx + ini + xla)
    # VBASync.ini 证实这是 VBASync 项目, 还带 Excel2LaTeX.xla
    $vbaDir = Join-Path $ASSETS "03-projects\vba-excel2latex-legacy"
    $vbaExts = @('*.cls', '*.bas', '*.frm', '*.frx', '*.ini', '*.xla')
    $vbaFiles = $vbaExts | ForEach-Object { Get-ChildItem $STAGING -Filter $_ -File }
    foreach ($f in $vbaFiles) {
        Do-Move $f.FullName $vbaDir "vbasync-excel2latex-project"
    }

    # 2b. ING 银行对账 (.940 + 对应命名的 .xml + 对应命名的 .csv)
    $ingDir = Join-Path $ASSETS "07-life\finance\bank-statements\ing"
    Get-ChildItem $STAGING -Filter "NL12INGB*" -File | ForEach-Object {
        Do-Move $_.FullName $ingDir "ing-bank-statement"
    }

    # 2c. Anki 学荷语词汇
    $ankiDir = Join-Path $ASSETS "07-life\dutch-inburgering\anki"
    @(
        "anki.csv",
        "woorden.csv",
        "Anki for Chase woorden.csv"
    ) | ForEach-Object {
        $p = Join-Path $STAGING $_
        if (Test-Path -LiteralPath $p) {
            Do-Move $p $ankiDir "anki-dutch-vocab"
        }
    }

    # 2d. clients.csv (看名字是客户名单)
    $bizDir = Join-Path $ASSETS "07-life\business"
    $p = Join-Path $STAGING "clients.csv"
    if (Test-Path -LiteralPath $p) {
        Do-Move $p $bizDir "client-list"
    }

    # 2e. LaTeX figures (eps + emf)
    # eps 是 logo (rug 大学 logo), emf 是 Word 矢量图 (image*.emf)
    # 先归到 03-projects/latex-assets/ 等后续 L3 决定具体哪个项目
    $latexAssetsDir = Join-Path $ASSETS "03-projects\latex-assets"
    Get-ChildItem $STAGING -Filter "*.eps" -File | ForEach-Object {
        Do-Move $_.FullName (Join-Path $latexAssetsDir "logos") "latex-logo-eps"
    }
    Get-ChildItem $STAGING -Filter "*.emf" -File | ForEach-Object {
        Do-Move $_.FullName (Join-Path $latexAssetsDir "figures-emf") "latex-figure-emf"
    }

    # 2f. Python 工具脚本 (去重后)
    # LaTeX 工具: process_tex, myfig_converter, hanging_references → latex-assets/tools/
    # Invoice_Generator → 03-projects/chase-photo-video-productions/tools/
    # s6_to_s7_clipboard → ? 未知, 放 staging 给 L3 agent 看
    $latexToolsDir = Join-Path $latexAssetsDir "tools"
    @('process_tex.py', 'process_tex_v2.py', 'myfig_converter.py', 'hanging_references.py') | ForEach-Object {
        $p = Join-Path $STAGING $_
        if (Test-Path -LiteralPath $p) { Do-Move $p $latexToolsDir "latex-python-tool" }
    }

    $invoiceDir = Join-Path $ASSETS "03-projects\chase-photo-video-productions\tools"
    $p = Join-Path $STAGING "Invoice_Generator.py"
    if (Test-Path -LiteralPath $p) { Do-Move $p $invoiceDir "invoice-generator-py" }

    # 2g. InDesign 设计文件 + 大 TIF
    $designDir = Join-Path $ASSETS "17-design\indesign"
    Get-ChildItem $STAGING -Filter "*.indd" -File | ForEach-Object {
        Do-Move $_.FullName $designDir "indesign-document"
    }
    # 封面.tif (206 MB) 看名字是设计封面
    $tifCover = Join-Path $STAGING "封面.tif"
    if (Test-Path -LiteralPath $tifCover) {
        Do-Move $tifCover $designDir "tif-cover-design"
    }

    # 2h. ctbbl (AutoCAD block list, 可能跟设计一起)
    $p = Join-Path $STAGING "Block Lists from CHASE的台式机.ctbbl"
    if (Test-Path -LiteralPath $p) {
        Do-Move $p (Join-Path $designDir "autocad") "autocad-block-list"
    }
}

# ============================================================
# L3: 剩下的就是候选池 (agent 处理)
# ============================================================
Write-Host "`n[L3] 剩余候选池 (agent 用)" -ForegroundColor Yellow
$remaining = Get-ChildItem $STAGING -Recurse -File
$remaining | ForEach-Object { $_.FullName } | Out-File $L3_LIST -Encoding UTF8
$stats.l3 = $remaining.Count

Write-Host "`n==== 汇总 [$mode] ====" -ForegroundColor Cyan
Write-Host ("  L1 删除:       {0}" -f $stats.deleted) -ForegroundColor Red
Write-Host ("  L2 归档:       {0}" -f $stats.moved) -ForegroundColor Green
Write-Host ("  L3 剩余 (agent):{0}" -f $stats.l3) -ForegroundColor Yellow
Write-Host ("  失败:          {0}" -f $stats.failed) -ForegroundColor DarkRed
Write-Host "`n日志: $LOG" -ForegroundColor DarkGray
Write-Host "L3 列表: $L3_LIST" -ForegroundColor DarkGray

"=== end $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') deleted=$($stats.deleted) moved=$($stats.moved) l3=$($stats.l3) failed=$($stats.failed) ===" | Out-File $LOG -Append -Encoding UTF8
