#Requires -Version 5.1
<#
.SYNOPSIS
    SHA256 扫 D:\brain-assets 找重复文件, 默认 dry-run.

.DESCRIPTION
    两遍扫描:
    1. 先按文件大小分组 (秒级), 只有大小一样的才需要算 hash
    2. 对 "大小相同" 的候选, 算 SHA256, 按 hash 归组
    再输出重复候选到 _migration/dedup-YYYY-MM-DD.tsv
    默认只生成报告, 不删任何文件.
#>

[CmdletBinding()]
param(
    [string]$AssetsRoot = "D:\brain-assets",
    [int]$MinSizeKB = 10,  # 小于 10KB 的小文件跳过 (算不出有意义的重复, 比如空 .gitkeep)
    [switch]$IncludeInbox  # 默认跳 99-inbox (批处理中, 易变)
)

$today = Get-Date -Format "yyyy-MM-dd"
$reportMd  = Join-Path $AssetsRoot "_migration\dedup-$today.md"
$reportTsv = Join-Path $AssetsRoot "_migration\dedup-$today.tsv"

Write-Host "`n==== brain-assets 去重扫描 $today ====" -ForegroundColor Cyan

# 收集所有文件
Write-Host "列文件..." -ForegroundColor DarkGray
$files = Get-ChildItem $AssetsRoot -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
    $_.FullName -notmatch '\\_migration\\' -and
    ($IncludeInbox -or $_.FullName -notmatch '\\99-inbox\\') -and
    $_.Length -ge ($MinSizeKB * 1KB)
}
Write-Host "  候选文件: $($files.Count) (大于 ${MinSizeKB}KB)" -ForegroundColor DarkGray

# 按大小分组
Write-Host "按大小分组..." -ForegroundColor Yellow
$sizeGroups = $files | Group-Object Length | Where-Object { $_.Count -gt 1 }
$toHash = ($sizeGroups | ForEach-Object { $_.Group }).Count
Write-Host "  疑似重复候选 (同大小): $toHash 个文件, 分 $($sizeGroups.Count) 组" -ForegroundColor DarkGray

if ($toHash -eq 0) {
    Write-Host "`n没找到任何潜在重复文件 (所有文件大小都唯一).`n" -ForegroundColor Green
    return
}

# 对候选算 SHA256
Write-Host "算 SHA256..." -ForegroundColor Yellow
$hashMap = @{}
$done = 0
foreach ($grp in $sizeGroups) {
    foreach ($f in $grp.Group) {
        $done++
        if ($done % 50 -eq 0) {
            Write-Host ("  [{0}/{1}] {2}" -f $done, $toHash, $f.Name) -ForegroundColor DarkGray
        }
        try {
            $h = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
        } catch {
            continue
        }
        if (-not $hashMap.ContainsKey($h)) { $hashMap[$h] = @() }
        $hashMap[$h] += $f
    }
}

# 过滤出真的重复的
$dupGroups = $hashMap.GetEnumerator() | Where-Object { $_.Value.Count -gt 1 }
Write-Host "`n找到 $($dupGroups.Count) 组真实重复." -ForegroundColor $(if ($dupGroups.Count -eq 0) { 'Green' } else { 'Yellow' })

if ($dupGroups.Count -eq 0) {
    Write-Host "没找到真实重复 (hash 无冲突).`n" -ForegroundColor Green
    return
}

# ============================================================
# 写 TSV (方便程序再消费)
# ============================================================
$tsvLines = [System.Collections.Generic.List[string]]::new()
$tsvLines.Add("hash`tsize_kb`tcount`tpath`tkeep_suggestion")
$totalDupSize = 0
$totalDupFiles = 0
foreach ($g in $dupGroups) {
    $sizeKb = [math]::Round($g.Value[0].Length / 1KB, 1)
    $totalDupFiles += ($g.Value.Count - 1)  # 每组只保留 1 个, 其他都是冗余
    $totalDupSize  += ($g.Value.Count - 1) * $g.Value[0].Length

    # 保留建议: 路径最短 / 名字最规整的那个
    $sorted = $g.Value | Sort-Object @{E = { $_.FullName.Length }}, @{E = { $_.Name }}
    $keep = $sorted[0]

    foreach ($f in $sorted) {
        $mark = if ($f.FullName -eq $keep.FullName) { 'KEEP' } else { 'DUP' }
        $tsvLines.Add(("{0}`t{1}`t{2}`t{3}`t{4}" -f $g.Key.Substring(0,12), $sizeKb, $g.Value.Count, $f.FullName, $mark))
    }
}

$tsvLines -join "`n" | Out-File $reportTsv -Encoding UTF8

# ============================================================
# 写 MD (人类可读)
# ============================================================
$md = [System.Collections.Generic.List[string]]::new()
$md.Add('---')
$md.Add('title: brain-assets 去重报告 ' + $today)
$md.Add('date: ' + $today)
$md.Add('tags: [dedup, housekeeping, auto-generated]')
$md.Add('---')
$md.Add('')
$md.Add('# brain-assets 去重候选 ' + $today)
$md.Add('')
$md.Add("扫了 **$($files.Count)** 个文件 (过滤掉 <${MinSizeKB}KB 的小文件$(if (-not $IncludeInbox) { ' 和 99-inbox/' })).")
$md.Add('')
$md.Add('## 汇总')
$md.Add('')
$md.Add("- 重复组数: **$($dupGroups.Count)**")
$md.Add("- 冗余文件数: **$totalDupFiles** (如全删可释放)")
$md.Add("- 冗余总大小: **$([math]::Round($totalDupSize / 1MB, 1)) MB**")
$md.Add('')
$md.Add('## 使用说明')
$md.Add('')
$md.Add('- 每组标 `KEEP` 的是建议保留 (路径最短/命名最规整的一个)')
$md.Add('- 标 `DUP` 的是冗余, 可考虑删')
$md.Add('- 默认不自动删, 人工 review 了再跑 `-Execute`')
$md.Add('')

$n = 0
foreach ($g in ($dupGroups | Sort-Object -Property @{E = { $_.Value[0].Length }} -Descending)) {
    $n++
    $sizeKb = [math]::Round($g.Value[0].Length / 1KB, 1)
    $md.Add("### 组 $n · $sizeKb KB × $($g.Value.Count) 份")
    $md.Add('')
    $sorted = $g.Value | Sort-Object @{E = { $_.FullName.Length }}, @{E = { $_.Name }}
    $keep = $sorted[0].FullName
    foreach ($f in $sorted) {
        $mark = if ($f.FullName -eq $keep) { '**KEEP**' } else { 'dup' }
        $md.Add('- ' + $mark + ' `' + $f.FullName + '`')
    }
    $md.Add('')
    if ($n -ge 200) {
        $md.Add('*(只显示前 200 组, 其他见 dedup-*.tsv)*')
        $md.Add('')
        break
    }
}

$md.Add('---')
$md.Add('')
$md.Add('*auto-generated by `brain-asset-dedup.ps1` (dry-run)*')

$md -join "`n" | Out-File $reportMd -Encoding UTF8

Write-Host "`n报告:" -ForegroundColor Green
Write-Host "  MD:  $reportMd"
Write-Host "  TSV: $reportTsv"
Write-Host "`n下一步: 人工看 MD 报告, 决定哪些要删, 再手动删或写执行脚本.`n" -ForegroundColor DarkYellow
