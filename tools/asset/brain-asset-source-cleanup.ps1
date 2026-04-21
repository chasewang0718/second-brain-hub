#Requires -Version 5.1
<#
.SYNOPSIS
    按 manifest 清理已成功迁移的源文件 (7 天验收期后自动跑, 或手动).

.DESCRIPTION
    把 Stage 3 成功 copy 过的源文件从 D:\BaiduSyncdisk\ 删掉.
    为防止误删, 每个文件先过三道安全检查:
      1. 源文件仍存在 (未被用户手动清过)
      2. 目标 (brain-assets/) 对应文件存在
      3. 源/目标文件大小一致 (快速完整性校验)
    三条全过才删; 任何一条不满足就跳过并记日志.

    触发方式:
      - Task Scheduler 一次性任务 (2026-04-26 09:00)
      - 或手动: powershell -File brain-asset-source-cleanup.ps1

.PARAMETER ManifestPath
    指定 manifest. 默认用 _migration 下最新一份.

.PARAMETER ExecuteLogPath
    指定 execute.log (用来认定"已成功 copy"的 OK 行). 默认同 manifest 前缀.

.PARAMETER DryRun
    默认 false (真删). 加 -DryRun 只打印不删.

.PARAMETER DeleteEmptyDirs
    清完文件后, 顺手删掉源端空目录 (默认 true, 提高清洁度).

.NOTES
    - 日志: D:\second-brain-assets\_migration\<job>-cleanup.log
    - 失败也不中断, 最后出汇总
#>

[CmdletBinding()]
param(
    [string]$ManifestPath,
    [string]$ExecuteLogPath,
    [switch]$DryRun,
    [bool]$DeleteEmptyDirs = $true
)

$ASSETS_ROOT = "D:\second-brain-assets"
$MIGRATION_DIR = Join-Path $ASSETS_ROOT "_migration"
$BRAIN_ROOT = "D:\second-brain-content"

# ============================================================
# 定位 manifest
# ============================================================
if (-not $ManifestPath) {
    $latest = Get-ChildItem $MIGRATION_DIR -Filter "*-manifest.tsv" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { Write-Host "❌ 找不到 manifest" -ForegroundColor Red; exit 1 }
    $ManifestPath = $latest.FullName
}
if (-not (Test-Path $ManifestPath)) { Write-Host "❌ manifest 不存在: $ManifestPath" -ForegroundColor Red; exit 1 }

$jobBase = [System.IO.Path]::GetFileNameWithoutExtension($ManifestPath) -replace "-manifest$", ""
if (-not $ExecuteLogPath) {
    $ExecuteLogPath = Join-Path $MIGRATION_DIR "$jobBase-execute.log"
}
$cleanupLog = Join-Path $MIGRATION_DIR "$jobBase-cleanup.log"

Write-Host "`n==== brain-asset Stage 4: 源清理 ====" -ForegroundColor Cyan
Write-Host "Manifest:    $ManifestPath" -ForegroundColor DarkGray
Write-Host "Execute log: $ExecuteLogPath" -ForegroundColor DarkGray
Write-Host "Cleanup log: $cleanupLog" -ForegroundColor DarkGray
if ($DryRun) { Write-Host "模式:        DRY-RUN (只看不删)" -ForegroundColor Yellow } else { Write-Host "模式:        EXECUTE (真删)" -ForegroundColor Green }

# ============================================================
# 从 execute.log 读取 "OK" 行建立源→目标映射
# ============================================================
$okMap = @{}
if (Test-Path $ExecuteLogPath) {
    Get-Content $ExecuteLogPath -Encoding UTF8 | ForEach-Object {
        if ($_ -like "OK`t*") {
            $parts = $_ -split "`t"
            if ($parts.Count -ge 4) {
                $src = $parts[1]; $dst = $parts[3]
                $okMap[$src] = $dst
            }
        }
    }
    Write-Host "execute.log 中 OK 行: $($okMap.Count)" -ForegroundColor DarkGray
}
else {
    Write-Host "⚠️  execute.log 不存在, 改用 manifest 直接派生 (稍不安全)" -ForegroundColor Yellow
    $rows = Import-Csv $ManifestPath -Delimiter "`t" -Encoding UTF8
    foreach ($r in $rows) {
        if ($r.action -in 'copy', 'copy-to-assets-inbox') {
            $destRoot = Join-Path $ASSETS_ROOT $r.target_dir
            $dst = Join-Path $destRoot $r.new_name
            $okMap[$r.source_path] = $dst
        }
    }
    Write-Host "  (从 manifest 派生 $($okMap.Count) 条)" -ForegroundColor DarkGray
}

# ============================================================
# 逐个校验 + 删除
# ============================================================
"=== cleanup start $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $cleanupLog -Encoding UTF8
"# 模式: $(if ($DryRun) {'DRY-RUN'} else {'EXECUTE'})" | Out-File $cleanupLog -Append -Encoding UTF8

$stats = @{
    deleted      = 0
    srcMissing   = 0
    dstMissing   = 0
    sizeMismatch = 0
    failed       = 0
}
$sourceDirs = [System.Collections.Generic.HashSet[string]]::new()

$i = 0
foreach ($kv in $okMap.GetEnumerator()) {
    $i++
    if ($i % 500 -eq 0) {
        Write-Host "  进度: $i / $($okMap.Count) (删=$($stats.deleted), 失败=$($stats.failed))" -ForegroundColor DarkGray
    }

    $src = $kv.Key; $dst = $kv.Value

    if (-not (Test-Path -LiteralPath $src)) {
        $stats.srcMissing++
        "SKIP-SRC-GONE`t$src" | Out-File $cleanupLog -Append -Encoding UTF8
        continue
    }

    if (-not (Test-Path -LiteralPath $dst)) {
        $stats.dstMissing++
        "SKIP-DST-MISSING`t$src`t$dst" | Out-File $cleanupLog -Append -Encoding UTF8
        continue
    }

    try {
        $srcSize = (Get-Item -LiteralPath $src).Length
        $dstSize = (Get-Item -LiteralPath $dst).Length
        if ($srcSize -ne $dstSize) {
            $stats.sizeMismatch++
            "SKIP-SIZE-MISMATCH`t$src`t$srcSize!=$dstSize" | Out-File $cleanupLog -Append -Encoding UTF8
            continue
        }
    }
    catch {
        $stats.failed++
        "FAIL-STAT`t$src`t$($_.Exception.Message)" | Out-File $cleanupLog -Append -Encoding UTF8
        continue
    }

    $parentDir = Split-Path $src -Parent
    [void]$sourceDirs.Add($parentDir)

    if ($DryRun) {
        $stats.deleted++
        "WOULD-DELETE`t$src" | Out-File $cleanupLog -Append -Encoding UTF8
    }
    else {
        try {
            Remove-Item -LiteralPath $src -Force -ErrorAction Stop
            $stats.deleted++
            "DELETED`t$src" | Out-File $cleanupLog -Append -Encoding UTF8
        }
        catch {
            $stats.failed++
            "FAIL-DELETE`t$src`t$($_.Exception.Message)" | Out-File $cleanupLog -Append -Encoding UTF8
        }
    }
}

# ============================================================
# 清空目录 (可选)
# ============================================================
$emptyDirsDeleted = 0
if (-not $DryRun -and $DeleteEmptyDirs) {
    # 反复扫 BaiduSyncdisk, 删所有空目录 (最多 5 轮避免死循环)
    for ($r = 0; $r -lt 5; $r++) {
        $empty = Get-ChildItem "D:\BaiduSyncdisk" -Recurse -Directory -ErrorAction SilentlyContinue |
                 Where-Object { -not (Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue) }
        if (-not $empty) { break }
        foreach ($d in $empty) {
            try {
                Remove-Item -LiteralPath $d.FullName -Force -ErrorAction Stop
                $emptyDirsDeleted++
                "DELETED-DIR`t$($d.FullName)" | Out-File $cleanupLog -Append -Encoding UTF8
            }
            catch { }
        }
    }
}

"=== cleanup done $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $cleanupLog -Append -Encoding UTF8

# ============================================================
# 汇总
# ============================================================
Write-Host "`n==== 完成 ====" -ForegroundColor Cyan
Write-Host ("  删除文件:     {0}" -f $stats.deleted) -ForegroundColor Green
Write-Host ("  跳过-源已失踪: {0}" -f $stats.srcMissing) -ForegroundColor DarkYellow
Write-Host ("  跳过-目标缺失: {0}" -f $stats.dstMissing) -ForegroundColor DarkYellow
Write-Host ("  跳过-大小不一致: {0}" -f $stats.sizeMismatch) -ForegroundColor Red
Write-Host ("  删除失败:     {0}" -f $stats.failed) -ForegroundColor Red
if ($emptyDirsDeleted -gt 0) {
    Write-Host ("  清理空目录:   {0}" -f $emptyDirsDeleted) -ForegroundColor DarkCyan
}
Write-Host "`n详细日志: $cleanupLog`n" -ForegroundColor DarkGray
