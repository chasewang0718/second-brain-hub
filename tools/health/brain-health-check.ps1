#Requires -Version 5.1
<#
.SYNOPSIS
    扫 D:\second-brain-content 找健康问题: 断链 / 孤儿 / frontmatter 不规范 / 失效 asset_path.

.DESCRIPTION
    检查 5 类问题:
    1. 断的 [[wiki-link]] - 指向不存在的 md
    2. Tier A 指针卡里 asset_path 指向的文件不存在
    3. Frontmatter 缺 title / tags
    4. 完全的孤儿 md (没被任何其他文件引用过)
    5. 目录命名不一致 (同层有大小写混用 / 中英混用)

    生成 04-journal/brain-health-YYYY-MM-DD.md 报告.
#>

[CmdletBinding()]
param(
    [string]$BrainRoot = "D:\second-brain-content"
)

$today = Get-Date -Format "yyyy-MM-dd"
$report = Join-Path $BrainRoot "04-journal\brain-health-$today.md"

Write-Host "`n==== brain 健康检查 $today ====" -ForegroundColor Cyan

# ============================================================
# 1. 收集所有 md 文件和它们的基本信息
# ============================================================
$mdFiles = Get-ChildItem $BrainRoot -Recurse -Filter "*.md" -File | Where-Object { $_.FullName -notmatch '\\\.git\\' }
Write-Host "扫描 $($mdFiles.Count) 个 md 文件..." -ForegroundColor DarkGray

$docs = [System.Collections.ArrayList]@()
foreach ($f in $mdFiles) {
    $content = Get-Content $f.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if (-not $content) { continue }

    # 解析 frontmatter
    $fm = @{}
    if ($content -match "^---\s*[\r\n]+(?<fm>[\s\S]*?)[\r\n]+---") {
        $fmBlock = $matches['fm']
        foreach ($line in ($fmBlock -split "[\r\n]+")) {
            if ($line -match "^(?<k>[\w_-]+):\s*(?<v>.*)$") {
                $fm[$matches['k'].Trim()] = $matches['v'].Trim()
            }
        }
    }

    # 提取所有 wiki-links [[...]]
    $wikiLinks = [regex]::Matches($content, '\[\[([^\]|]+)(?:\|[^\]]*)?\]\]') | ForEach-Object { $_.Groups[1].Value.Trim() }

    # 提取所有 markdown relative links
    $mdLinks = [regex]::Matches($content, '\]\((?!https?://|#)([^)]+\.md)(?:#[^)]*)?\)') | ForEach-Object { $_.Groups[1].Value.Trim() }

    # slug (文件名无扩展)
    $slug = $f.BaseName

    # 相对 brain 的路径
    $relPath = $f.FullName.Substring($BrainRoot.Length).TrimStart('\').Replace('\', '/')

    [void]$docs.Add([PSCustomObject]@{
        File      = $f
        RelPath   = $relPath
        Slug      = $slug
        FM        = $fm
        WikiLinks = $wikiLinks
        MdLinks   = $mdLinks
        Content   = $content
    })
}

# 建立快速查找索引
$slugIndex = @{}
foreach ($d in $docs) {
    if (-not $slugIndex.ContainsKey($d.Slug)) { $slugIndex[$d.Slug] = @() }
    $slugIndex[$d.Slug] += $d
}

$relPathIndex = @{}
foreach ($d in $docs) {
    $relPathIndex[$d.RelPath.ToLower()] = $d
}

# ============================================================
# 2. 检查 1: 断的 [[wiki-link]]
# ============================================================
Write-Host "检查断链..." -ForegroundColor Yellow
$brokenWikiLinks = [System.Collections.ArrayList]@()
foreach ($d in $docs) {
    foreach ($link in $d.WikiLinks) {
        # 支持 [[slug]] 和 [[path/to/slug]] — 路径非法字符直接跳 (例: <project>)
        try { $linkSlug = [System.IO.Path]::GetFileNameWithoutExtension($link.Replace('/', '\')) }
        catch { continue }
        if (-not $slugIndex.ContainsKey($linkSlug) -and $linkSlug) {
            [void]$brokenWikiLinks.Add([PSCustomObject]@{
                From    = $d.RelPath
                LinkTo  = $link
                Missing = $linkSlug
            })
        }
    }
}

# ============================================================
# 3. 检查 2: asset_path 失效
# ============================================================
Write-Host "检查 asset_path..." -ForegroundColor Yellow
$brokenAssetPaths = [System.Collections.ArrayList]@()
foreach ($d in $docs) {
    if ($d.FM.ContainsKey('asset_path')) {
        $assetPath = $d.FM['asset_path'].Trim('"').Trim("'")
        if ($assetPath -and -not (Test-Path -LiteralPath $assetPath)) {
            [void]$brokenAssetPaths.Add([PSCustomObject]@{
                Card        = $d.RelPath
                MissingPath = $assetPath
            })
        }
    }
}

# ============================================================
# 4. 检查 3: Frontmatter 缺字段
# ============================================================
Write-Host "检查 frontmatter..." -ForegroundColor Yellow
$fmMissing = [System.Collections.ArrayList]@()
$required = @('title', 'tags')
foreach ($d in $docs) {
    # 跳过约定不需要 frontmatter 的文件
    if ($d.RelPath -match '^(README|AGENTS)\.md$') { continue }
    if ($d.RelPath -like '00-memory/*') { continue }  # 00-memory 结构自由
    if ($d.FM.Count -eq 0) {
        [void]$fmMissing.Add([PSCustomObject]@{
            File    = $d.RelPath
            Missing = 'NO-FRONTMATTER'
        })
        continue
    }
    $missing = $required | Where-Object { -not $d.FM.ContainsKey($_) }
    if ($missing) {
        [void]$fmMissing.Add([PSCustomObject]@{
            File    = $d.RelPath
            Missing = ($missing -join ',')
        })
    }
}

# ============================================================
# 5. 检查 4: 孤儿 md (没被任何其他文件引用)
# ============================================================
Write-Host "检查孤儿 md..." -ForegroundColor Yellow
# 哪些 slug 被谁引用
$referencedSlugs = [System.Collections.Generic.HashSet[string]]::new()
foreach ($d in $docs) {
    foreach ($link in $d.WikiLinks) {
        try { $linkSlug = [System.IO.Path]::GetFileNameWithoutExtension($link.Replace('/', '\')) }
        catch { continue }
        if ($linkSlug) { [void]$referencedSlugs.Add($linkSlug) }
    }
    foreach ($link in $d.MdLinks) {
        try { $linkSlug = [System.IO.Path]::GetFileNameWithoutExtension($link) }
        catch { continue }
        if ($linkSlug) { [void]$referencedSlugs.Add($linkSlug) }
    }
}

$orphans = [System.Collections.ArrayList]@()
foreach ($d in $docs) {
    # 豁免: README / AGENTS / 00-memory / 04-journal (日志本来就独立)
    if ($d.RelPath -match '^(README|AGENTS)\.md$') { continue }
    if ($d.RelPath -like '00-memory/*') { continue }
    if ($d.RelPath -like '04-journal/*') { continue }

    if (-not $referencedSlugs.Contains($d.Slug)) {
        [void]$orphans.Add($d.RelPath)
    }
}

# ============================================================
# 6. 检查 5: 目录命名不一致
# ============================================================
Write-Host "检查目录命名..." -ForegroundColor Yellow
$dirs = Get-ChildItem $BrainRoot -Recurse -Directory | Where-Object { $_.FullName -notmatch '\\\.git\\' }
$namingIssues = [System.Collections.ArrayList]@()
foreach ($d in $dirs) {
    # 路径里有中文 mixed 英文 (只检查目录名本身)
    $name = $d.Name
    if ($name -match '[\u4e00-\u9fff]' -and $name -match '[a-zA-Z]') {
        [void]$namingIssues.Add([PSCustomObject]@{
            Dir   = $d.FullName.Substring($BrainRoot.Length).TrimStart('\').Replace('\', '/')
            Issue = 'chinese-english-mixed'
        })
    }
    # 驼峰 / 空格
    if ($name -match '\s' -or $name -match '[A-Z].*[a-z].*[A-Z]') {
        [void]$namingIssues.Add([PSCustomObject]@{
            Dir   = $d.FullName.Substring($BrainRoot.Length).TrimStart('\').Replace('\', '/')
            Issue = 'non-kebab-case'
        })
    }
}

# ============================================================
# 7. 写报告
# ============================================================
$md = [System.Collections.Generic.List[string]]::new()
$md.Add('---')
$md.Add('title: brain 健康检查报告 ' + $today)
$md.Add('date: ' + $today)
$md.Add('tags: [health-check, auto-generated, housekeeping]')
$md.Add('---')
$md.Add('')
$md.Add('# brain 健康检查 ' + $today)
$md.Add('')
$md.Add("扫描 **$($mdFiles.Count)** 个 md 文件 + **$($dirs.Count)** 个目录.")
$md.Add('')
$md.Add('## 汇总')
$md.Add('')
$md.Add('| 检查 | 结果 |')
$md.Add('|------|------|')
$md.Add("| 断的 wiki-link | $($brokenWikiLinks.Count) |")
$md.Add("| 失效 asset_path | $($brokenAssetPaths.Count) |")
$md.Add("| Frontmatter 不规范 | $($fmMissing.Count) |")
$md.Add("| 孤儿 md (无人引用) | $($orphans.Count) |")
$md.Add("| 目录命名问题 | $($namingIssues.Count) |")
$md.Add('')

if ($brokenWikiLinks.Count -gt 0) {
    $md.Add('## 1. 断的 wiki-link (指向不存在的 md)')
    $md.Add('')
    $md.Add('| 所在文件 | 断链 | 要找的 slug |')
    $md.Add('|---------|------|-------------|')
    foreach ($b in ($brokenWikiLinks | Sort-Object From | Select-Object -First 100)) {
        $md.Add("| ``$($b.From)`` | ``[[$($b.LinkTo)]]`` | ``$($b.Missing)`` |")
    }
    if ($brokenWikiLinks.Count -gt 100) { $md.Add('') ; $md.Add("*(还有 $($brokenWikiLinks.Count - 100) 条省略)*") }
    $md.Add('')
}

if ($brokenAssetPaths.Count -gt 0) {
    $md.Add('## 2. 失效 asset_path (Tier A 指针卡指向的 Tier B 文件不存在)')
    $md.Add('')
    $md.Add('| 指针卡 | 失效路径 |')
    $md.Add('|--------|----------|')
    foreach ($b in ($brokenAssetPaths | Sort-Object Card | Select-Object -First 50)) {
        $md.Add("| ``$($b.Card)`` | ``$($b.MissingPath)`` |")
    }
    if ($brokenAssetPaths.Count -gt 50) { $md.Add('') ; $md.Add("*(还有 $($brokenAssetPaths.Count - 50) 条省略)*") }
    $md.Add('')
}

if ($fmMissing.Count -gt 0) {
    $md.Add('## 3. Frontmatter 不规范')
    $md.Add('')
    $md.Add('| 文件 | 缺失字段 |')
    $md.Add('|------|----------|')
    foreach ($b in ($fmMissing | Sort-Object File | Select-Object -First 100)) {
        $md.Add("| ``$($b.File)`` | $($b.Missing) |")
    }
    if ($fmMissing.Count -gt 100) { $md.Add('') ; $md.Add("*(还有 $($fmMissing.Count - 100) 条省略)*") }
    $md.Add('')
}

if ($orphans.Count -gt 0) {
    $md.Add('## 4. 孤儿 md (没被任何其他文件引用)')
    $md.Add('')
    $md.Add('豁免: `README.md` / `AGENTS.md` / `00-memory/*` / `04-journal/*`')
    $md.Add('')
    foreach ($o in ($orphans | Sort-Object)) {
        $md.Add("- ``$o``")
    }
    $md.Add('')
}

if ($namingIssues.Count -gt 0) {
    $md.Add('## 5. 目录命名问题')
    $md.Add('')
    $md.Add('| 目录 | 问题 |')
    $md.Add('|------|------|')
    foreach ($n in ($namingIssues | Sort-Object Dir)) {
        $md.Add("| ``$($n.Dir)`` | $($n.Issue) |")
    }
    $md.Add('')
}

$md.Add('## 建议行动')
$md.Add('')
$md.Add('- 断链: 看 wiki-link 是否写错了 slug, 或该建新文档')
$md.Add('- 失效 asset_path: 指针卡没意义了, 修路径或删卡')
$md.Add('- 孤儿 md: 如果是历史笔记没价值了就删, 否则在 README / index 里加索引')
$md.Add('- 命名问题: 文件名改 kebab-case, brain 一贯风格')
$md.Add('')
$md.Add('---')
$md.Add('')
$md.Add('*auto-generated by `brain-health-check.ps1`*')

$md -join "`n" | Out-File $report -Encoding UTF8

Write-Host "`n==== 完成 ====" -ForegroundColor Green
Write-Host ("  断链:         {0}" -f $brokenWikiLinks.Count) -ForegroundColor $(if ($brokenWikiLinks.Count -eq 0) { 'Green' } else { 'Red' })
Write-Host ("  失效 asset:   {0}" -f $brokenAssetPaths.Count) -ForegroundColor $(if ($brokenAssetPaths.Count -eq 0) { 'Green' } else { 'Red' })
Write-Host ("  fm 不规范:    {0}" -f $fmMissing.Count) -ForegroundColor $(if ($fmMissing.Count -eq 0) { 'Green' } else { 'Yellow' })
Write-Host ("  孤儿:         {0}" -f $orphans.Count) -ForegroundColor $(if ($orphans.Count -eq 0) { 'Green' } else { 'Yellow' })
Write-Host ("  命名问题:     {0}" -f $namingIssues.Count) -ForegroundColor $(if ($namingIssues.Count -eq 0) { 'Green' } else { 'Yellow' })
Write-Host "`n报告: $report`n" -ForegroundColor Cyan
