#Requires -Version 5.1
<#
.SYNOPSIS
    对 brain-assets 的叶子目录补 "集群总览卡" (Tier A README/overview), 让 Tier B 内容进入可搜索索引.

.DESCRIPTION
    扫 D:\second-brain-assets 找出叶子目录 (包含 >= MinFiles 个文件的目录):
    - 如果 Tier A 对应目录已经有 README.md 或 overview.md, 跳
    - 否则让 cursor-agent 采样 3-5 个文件名 (不读内容, 省 token), 生成 overview.md

    默认 dry-run: 只列出候选, 不真调 agent.
    -Execute: 真跑 agent 生成卡 (吃 token, 每张约 1-3k).
    -MaxItems: 单次最多处理几个目录, 默认 5.
#>

[CmdletBinding()]
param(
    [string]$AssetsRoot = "D:\second-brain-assets",
    [string]$BrainRoot  = "D:\second-brain-content",
    [int]$MinFiles = 3,
    [int]$MaxItems = 5,
    [switch]$Execute
)

$today = Get-Date -Format "yyyy-MM-dd"
$logDir = Join-Path $AssetsRoot "_migration"
$log    = Join-Path $logDir "overview-cards-$today.log"

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

Write-Host "`n==== Tier A overview-card 补全 ====" -ForegroundColor Cyan

# 扫 brain-assets 所有子目录 (跳 _migration / 99-inbox / 98-staging)
$dirs = Get-ChildItem $AssetsRoot -Recurse -Directory -ErrorAction SilentlyContinue | Where-Object {
    $_.FullName -notmatch '\\_migration($|\\)' -and
    $_.FullName -notmatch '\\99-inbox($|\\)' -and
    $_.FullName -notmatch '\\98-staging($|\\)'
}

$candidates = [System.Collections.ArrayList]@()
foreach ($d in $dirs) {
    $files = Get-ChildItem $d.FullName -File -ErrorAction SilentlyContinue
    if ($files.Count -lt $MinFiles) { continue }

    # Tier A 对应目录
    $rel = $d.FullName.Substring($AssetsRoot.Length).TrimStart('\')
    # brain-assets 特殊映射: 10-photos -> 07-life/photos, 11-fonts -> 02-snippets/fonts, 等
    # 保守起见, 先用 1:1 映射: brain\<rel>
    $tierA = Join-Path $BrainRoot $rel

    $readmeA = Join-Path $tierA "README.md"
    $overviewA = Join-Path $tierA "overview.md"
    if ((Test-Path $readmeA) -or (Test-Path $overviewA)) { continue }

    [void]$candidates.Add([PSCustomObject]@{
        TierBDir  = $d.FullName
        TierADir  = $tierA
        FileCount = $files.Count
        Sample    = ($files | Select-Object -First 5 | ForEach-Object { $_.Name })
        TotalMB   = [math]::Round((($files | Measure-Object Length -Sum).Sum) / 1MB, 1)
    })
}

$candidates = $candidates | Sort-Object { -$_.FileCount }

Write-Host "候选叶子目录: $($candidates.Count) (每个有 >= $MinFiles 个文件)" -ForegroundColor Yellow
Write-Host "本次处理上限: $MaxItems" -ForegroundColor Yellow
Write-Host ""

if (-not $Execute) {
    Write-Host "=== DRY RUN (前 $MaxItems 个候选) ===" -ForegroundColor DarkYellow
    foreach ($c in ($candidates | Select-Object -First $MaxItems)) {
        Write-Host "  $($c.TierBDir)"
        Write-Host "    -> $($c.TierADir)"
        Write-Host "    $($c.FileCount) 文件, $($c.TotalMB) MB, 样本: $($c.Sample -join ', ')"
        Write-Host ""
    }
    Write-Host "加 -Execute 真跑 agent 生成卡 (吃 token).`n" -ForegroundColor DarkYellow
    return
}

# 真执行
$agentBin = "$env:LOCALAPPDATA\cursor-agent\agent.exe"
if (-not (Test-Path $agentBin)) {
    $agentBin = "agent"  # 期望在 PATH 里
}

function Get-OverviewPrompt($tierBDir, $tierADir, $fileCount, $sample) {
    $sampleText = ($sample | ForEach-Object { "  - $_" }) -join "`n"
    return @"
任务: 给下面这批文件生成一张总览卡 (overview.md)

Tier B 目录 (只看文件名, 不需读内容):
$tierBDir

里面有 $fileCount 个文件, 前几个名字:
$sampleText

请你:
1. 根据文件名推断这批文件是什么主题 (比如 "ING 2024 年银行对账单", "LaTeX 某书的图", "2023 年杭州照片")
2. 在这个 Tier A 目录下建 overview.md: $tierADir
3. 若目录不存在就建
4. overview.md 用这个模板:

---
title: <一句话标题>
asset_type: folder-overview
asset_path: $tierBDir
asset_count: $fileCount
created: $today
tags: [<3-5 个 kebab-case 标签>]
---

# <标题>

## 这是什么
2-3 句说清这批文件是关于什么主题.

## 怎么来的
简述这批文件的来源 (比如 "来自百度云迁移, 2026-04").

## 典型文件
列 3-5 个代表性文件名, 让人一眼明白.

## 关联
- 相关主题: <有关联的 brain 其他目录, 可以是猜的>

---

只看文件名, 不要读文件内容. 不要 git push. git commit 可以. 不要问问题, 直接做.
"@
}

$processed = 0
foreach ($c in $candidates) {
    if ($processed -ge $MaxItems) { break }
    $processed++

    $prompt = Get-OverviewPrompt $c.TierBDir $c.TierADir $c.FileCount $c.Sample
    Write-Host "[$processed/$MaxItems] $($c.TierBDir)" -ForegroundColor Cyan
    Add-Content -Path $log -Value "[$(Get-Date -Format 'HH:mm:ss')] START $($c.TierBDir)" -Encoding UTF8

    try {
        $out = & $agentBin -p $prompt 2>&1 | Out-String
        Add-Content -Path $log -Value $out -Encoding UTF8
        Add-Content -Path $log -Value "[$(Get-Date -Format 'HH:mm:ss')] END  $($c.TierBDir)" -Encoding UTF8
    } catch {
        Write-Host "  FAIL: $_" -ForegroundColor Red
        Add-Content -Path $log -Value "FAIL: $_" -Encoding UTF8
    }
}

Write-Host "`n处理了 $processed 个目录, 日志: $log" -ForegroundColor Green
