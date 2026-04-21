#Requires -Version 5.1
<#
.SYNOPSIS
    本地 Ollama + pdftotext PDF 分类 worker. 替代 cursor-agent 跑 Phase 2.3 的量产层.

.DESCRIPTION
    流水线:
        1. pdftotext 抽前 ~4000 字符文本 + 页数
        2. 拼 prompt + few-shot, POST 到 Ollama (format=json, 强制 JSON 输出)
        3. 解析 JSON, 写到 _ollama-output/<sha12>.json (不立即 apply)
        4. 失败/超时/低置信 → 标记到 _ollama-output/needs-review.tsv
    输出不做文件移动, 只产 JSON proposal. apply 由 brain-asset-pdf-apply.ps1 做.

.PARAMETER InboxDir
    PDF 源目录, 默认 D:\second-brain-assets\99-inbox

.PARAMETER OutputDir
    JSON proposal 输出目录, 默认 D:\second-brain-assets\_migration\ollama-output

.PARAMETER Model
    Ollama 模型名, 默认 qwen2.5:14b-instruct

.PARAMETER OllamaUrl
    Ollama API 端点, 默认 http://localhost:11434

.PARAMETER MaxItems
    最多处理多少份, 默认 0 = 全部

.PARAMETER TimeoutSec
    单个 PDF 超时 (秒), 默认 180

.PARAMETER DryRun
    只预览打印, 不写 JSON 文件

.EXAMPLE
    # 烟雾测试 (处理 3 份)
    .\brain-asset-pdf-local.ps1 -MaxItems 3 -DryRun

.EXAMPLE
    # Pilot 10 份
    .\brain-asset-pdf-local.ps1 -MaxItems 10

.EXAMPLE
    # 量产全部
    .\brain-asset-pdf-local.ps1
#>

[CmdletBinding()]
param(
    [string]$InboxDir = "",
    [string]$OutputDir = "",
    [string]$EscalationDir = "",
    [string]$Model = "qwen2.5:14b-instruct",
    [string]$OllamaUrl = "http://localhost:11434",
    [int]$MaxItems = 0,
    [int]$TimeoutSec = 0,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# 配置加载 (优先读 config/*.yaml; 失败则回退硬编码默认值)
$HUB_ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)  # second-brain-hub/
$configLoader = Join-Path $HUB_ROOT "tools\lib\config-loader.ps1"
if (Test-Path $configLoader) {
    . $configLoader
}
$telemetryLib = Join-Path $HUB_ROOT "tools\lib\telemetry.ps1"
if (Test-Path $telemetryLib) {
    . $telemetryLib
}

function Get-ConfigOrDefault {
    param(
        [string]$File,
        [string]$Key,
        $DefaultValue
    )
    if (Get-Command Get-BrainConfig -ErrorAction SilentlyContinue) {
        try { return (Get-BrainConfig -File $File -Key $Key) } catch {}
    }
    return $DefaultValue
}

function Write-TelemetrySafe {
    param([hashtable]$Entry)
    if (-not (Get-Command Write-Telemetry -ErrorAction SilentlyContinue)) {
        return
    }
    try {
        [void](Write-Telemetry -Entry $Entry)
    } catch {}
}

function Write-EscalationItemSafe {
    param(
        [string]$Reason,
        [string]$SourcePath,
        [string]$SourceFileName,
        [string]$SourceHash,
        [int]$DurationMs,
        [double]$Confidence,
        [bool]$SchemaValid,
        [string]$RawOutput
    )
    try {
        if (-not (Test-Path $EscalationDir)) {
            New-Item -ItemType Directory -Path $EscalationDir -Force | Out-Null
        }
        $ts = (Get-Date).ToUniversalTime()
        $safeHash = if ([string]::IsNullOrWhiteSpace($SourceHash)) { "unknown" } else { $SourceHash }
        $fileName = "{0}_{1}_{2}.json" -f $ts.ToString("yyyy-MM-dd"), "pdf-classify", $safeHash
        $path = Join-Path $EscalationDir $fileName

        $payload = [ordered]@{
            ts            = $ts.ToString("yyyy-MM-ddTHH:mm:ssZ")
            task          = "pdf-classify"
            source        = $SourcePath
            source_file   = $SourceFileName
            source_hash   = $safeHash
            local_attempt = @{
                model        = $Model
                confidence   = $Confidence
                schema_valid = $SchemaValid
                duration_ms  = $DurationMs
                raw_output   = $RawOutput
            }
            reason        = $Reason
            priority      = "normal"
            status        = "pending"
        }
        $payload | ConvertTo-Json -Depth 10 | Out-File -FilePath $path -Encoding UTF8
    } catch {}
}

if ([string]::IsNullOrWhiteSpace($InboxDir)) {
    $InboxDir = Get-ConfigOrDefault -File "paths" -Key "paths.pdf_inbox_dir" -DefaultValue "D:\second-brain-assets\99-inbox"
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Get-ConfigOrDefault -File "paths" -Key "paths.ollama_output_dir" -DefaultValue "D:\second-brain-assets\_migration\ollama-output"
}
if ([string]::IsNullOrWhiteSpace($EscalationDir)) {
    $EscalationDir = Get-ConfigOrDefault -File "paths" -Key "paths.escalation_dir" -DefaultValue "D:\second-brain-assets\_escalation"
}
if ($TimeoutSec -le 0) {
    $TimeoutSec = [int](Get-ConfigOrDefault -File "thresholds" -Key "pdf.timeout_sec" -DefaultValue 180)
}
$LowConfThreshold = [double](Get-ConfigOrDefault -File "thresholds" -Key "pdf.confidence_below" -DefaultValue 0.7)

# 载 prompt (system + few-shot 拼成一个大 string)
# prompt 源已迁到 hub 的 prompts/system/pdf-classifier.md (保持单一真相源)
$promptFile = Join-Path $HUB_ROOT "prompts\system\pdf-classifier.md"
if (-not (Test-Path $promptFile)) {
    # 向后兼容: 旧位置 (同目录)
    $legacy = Join-Path $PSScriptRoot "prompt-template.md"
    if (Test-Path $legacy) { $promptFile = $legacy }
    else { throw "缺少 prompt: $promptFile (或 legacy $legacy)" }
}
$promptRaw = Get-Content $promptFile -Raw -Encoding UTF8

# 提 "# 系统提示词" 和 "# Few-shot 样例" 部分, 拼成 system prompt
$systemPrompt = @"
你是「Chase 的第二大脑」PDF 分类助手。
严格按下面每个用户消息里的 FILENAME / PAGES / TEXT_SAMPLE **独立分析**, 输出对应的 JSON 对象。
**不要复制之前对话里的答案**, 每份 PDF 要根据它自己的内容单独判断。
输出必须是严格 JSON (无 markdown, 无解释), 符合 schema.

## 可选 category (enum)
invoice, tax, bank-statement, housing, identity, medical, contract, education, inburgering, business, certificate, picture-book, book, paper, latex-project, code-snippet, design, other

## category → Tier A / Tier B 映射

| category | Tier A dir | Tier B dir |
|----------|-----------|-----------|
| invoice | 07-life/finance/invoices | 07-life/finance/invoices |
| tax | 07-life/finance/tax | 07-life/finance/tax |
| bank-statement | 07-life/finance/bank-statements | 07-life/finance/bank-statements |
| housing | 07-life/housing | 07-life/housing |
| identity | 07-life/identity | 07-life/identity |
| medical | 07-life/health | 07-life/health |
| contract | 07-life/contracts | 07-life/contracts |
| education | 07-life/education | 07-life/education |
| inburgering | 07-life/dutch-inburgering | 07-life/dutch-inburgering |
| business | 03-projects/chase-photo-video-productions | 03-projects/chase-photo-video-productions |
| certificate | 07-life/certificates | 07-life/certificates |
| picture-book | 01-concepts/picture-books | 16-books/picture-books |
| book | 01-concepts/books | 16-books |
| paper | 01-concepts/papers | 01-concepts/papers |
| latex-project | 03-projects/<proj-slug> | 03-projects/<proj-slug> |
| code-snippet | 02-snippets/<lang> | — |
| design | 17-design | 17-design |
| other | 99-inbox | 98-staging |

## sensitive=true 触发条件
- BSN (9 位数字) / IBAN (NL\d{2}[A-Z]{4}\d{10}) / 完整家庭地址 / 个人薪资 / 他人姓名

## slug 规则
- kebab-case, 全英文或拼音, 无中文/空格/特殊字符, <=80 字符
- 含日期: 加 -YYYY-MM-DD 或 -YYYY
- 保证唯一性 (可加发票号等)

## 输出 schema (严格)
{
  "category": "...",                   // enum 之一, 必填
  "subcategory": "...",                // 可选, kebab-case
  "tier_a_dir": "...",                 // 对应 category 的 Tier A 路径
  "tier_b_dir": "...",                 // 对应 category 的 Tier B 路径
  "slug": "...",                       // 必填, kebab-case
  "title_zh": "...",                   // 必填, 2-80 字
  "title_original": "...",             // 可选
  "summary_zh": "...",                 // 必填, 30-500 字, 3-6 句
  "tags": ["...","..."],               // 3-10 个 kebab-case
  "sensitive": true|false,             // 必填
  "sensitive_items": ["..."],          // sensitive=true 时列具体字段
  "related_hints": ["..."],            // 可选 [[slug]] 建议 (不带括号)
  "page_count": 0,                     // 整数
  "language": "zh|en|nl|mixed|other",
  "confidence": 0.0-1.0,               // 必填
  "reasoning_brief": "..."             // 1-2 句说明
}

输出必须是严格的 JSON 对象, 无注释, 无 markdown.
每份 PDF 独立判断 —— 不要复制对话里的任何字段。
"@

# Few-shot 作为独立 user/assistant 对话塞进 messages (chat API), 避免被当答案复制
$global:FewShotExamples = @(
    @{
        input = "FILENAME: 00-2-3.pdf`nSIZE: 1.0 MB`nPAGES: 28`nTEXT_SAMPLE:`n妈妈你看 这是大灰狼 强盗妈妈背着麻袋 走过黑森林"
        output = '{"category":"picture-book","subcategory":"chinese-children-read-aloud","tier_a_dir":"01-concepts/picture-books","tier_b_dir":"16-books/picture-books","slug":"qiangdao-mama-pianduan-00-2-3","title_zh":"强盗妈妈 合上片段 00-2-3","title_original":"强盗妈妈","summary_zh":"中文儿童绘本《强盗妈妈》朗读片段 PDF, 共 28 页. 属于 00-2-* 编号合集之一, 围绕强盗妈妈在黑森林的故事展开. 适合亲子阅读.","tags":["picture-book","chinese","childrens-book","read-aloud","fairy-tale"],"sensitive":false,"sensitive_items":[],"related_hints":[],"page_count":28,"language":"zh","confidence":0.92,"reasoning_brief":"朗读风格中文故事, 文件名明确绘本系列编号."}'
    },
    @{
        input = "FILENAME: Begrijpend lezen voor Anna.pdf`nSIZE: 0.63 MB`nPAGES: 21`nTEXT_SAMPLE:`nBegrijpend lezen Sprookje Rapunzel Lees de tekst en beantwoord de vragen Vraag 1 Wie is Gothel"
        output = '{"category":"inburgering","subcategory":"begrijpend-lezen","tier_a_dir":"07-life/dutch-inburgering","tier_b_dir":"07-life/dutch-inburgering","slug":"begrijpend-lezen-voor-anna","title_zh":"Begrijpend lezen voor Anna (Rapunzel 主题)","title_original":"Begrijpend lezen voor Anna","summary_zh":"荷兰语 begrijpend lezen (阅读理解) 练习 PDF, 21 页. 正文为 Rapunzel 风格童话叙述, 其后为多项选择题. 适合长文阅读与考试型选择题.","tags":["dutch","begrijpend-lezen","inburgering","rapunzel","kinderen"],"sensitive":false,"sensitive_items":[],"related_hints":["main-begrijpend-lezen"],"page_count":21,"language":"nl","confidence":0.95,"reasoning_brief":"文件名 + 文本都明确 Inburgering 阅读理解练习册."}'
    },
    @{
        input = "FILENAME: C Wang - Aangifte inkomstenbelasting 2021.pdf`nSIZE: 59 KB`nPAGES: 10`nTEXT_SAMPLE:`nFiscaal rapport voor de aangifte inkomstenbelasting 2021 BSN 123456789 Box 1 inkomen uit werk en woning EUR 45000"
        output = '{"category":"tax","subcategory":"inkomstenbelasting-fiscaal-rapport","tier_a_dir":"07-life/finance/tax","tier_b_dir":"07-life/finance/tax","slug":"aangifte-inkomstenbelasting-2021-c-wang","title_zh":"Fiscaal rapport inkomstenbelasting 2021 (C Wang)","title_original":"Fiscaal rapport voor de aangifte inkomstenbelasting 2021","summary_zh":"荷兰个人所得税 (inkomstenbelasting) 年度税务报告 / 申报材料, 10 页, 结构含 Box 1 与 onderneming 章节. 为符合隐私规则, 不写入具体金额/BSN/地址, 详见 Tier B 原文件.","tags":["tax","netherlands","inkomstenbelasting","belastingdienst","2021"],"sensitive":true,"sensitive_items":["bsn","home-address","salary"],"related_hints":["aangifte-inkomstenbelasting-2022-c-wang"],"page_count":10,"language":"nl","confidence":0.97,"reasoning_brief":"明确的 Fiscaal rapport 荷兰税务报告, 含 BSN 和金额."}'
    },
    @{
        input = "FILENAME: 2023005_002.pdf`nSIZE: 92 KB`nPAGES: 1`nTEXT_SAMPLE:`nCommercial Invoice 2023005 Date 2023-06-29 From F8 LTD Malta To Chase Photo Video Productions Groningen Netherlands"
        output = '{"category":"business","subcategory":"vendor-invoice","tier_a_dir":"03-projects/chase-photo-video-productions","tier_b_dir":"03-projects/chase-photo-video-productions","slug":"commercial-invoice-2023005-f8-ltd-malta","title_zh":"Commercial Invoice 2023005 F8 Ltd Malta to Chase Photo","title_original":"Commercial Invoice 2023005","summary_zh":"英文商业发票, 发票编号 2023005, 日期 2023-06-29. 开票方 F8 Ltd (马耳他), 客户 Chase Photo Video Productions (荷兰格罗宁根). 服务包括品牌注册/社交媒体管理. 票面 0% VAT. 隐藏金额/账号.","tags":["invoice","business","chase-photo-video","f8-ltd","malta","commercial-invoice"],"sensitive":true,"sensitive_items":["iban","home-address"],"related_hints":[],"page_count":1,"language":"en","confidence":0.94,"reasoning_brief":"Chase Photo 公司收到的对外服务发票, 归 business 优先于 invoice."}'
    },
    @{
        input = "FILENAME: 7-chengjidan.pdf`nSIZE: 0.46 MB`nPAGES: 3`nTEXT_SAMPLE:`n(pdftotext 抽不到文字, 疑似扫描件)"
        output = '{"category":"education","subcategory":"school-transcript","tier_a_dir":"07-life/education","tier_b_dir":"07-life/education","slug":"grade-7-transcript","title_zh":"七年级成绩单","title_original":"7 成绩单","summary_zh":"3 页学业成绩单 PDF. 文本抽取无可选字, 多为扫描图. 不写入学生姓名/学号/分数, 详见 Tier B 原文件.","tags":["education","school","transcript","grade-7","china"],"sensitive":true,"sensitive_items":["other-person-name"],"related_hints":[],"page_count":3,"language":"zh","confidence":0.72,"reasoning_brief":"文件名明确是成绩单, 但无文本只凭名字, confidence 中等."}'
    }
)

# ============================================================
# 工具函数
# ============================================================

function Test-Prereq {
    $missing = @()
    if (-not (Get-Command pdftotext -ErrorAction SilentlyContinue)) {
        $missing += "pdftotext"
    }
    try {
        $r = Invoke-WebRequest -Uri "$OllamaUrl/api/tags" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -ne 200) { $missing += "ollama-api" }
    } catch { $missing += "ollama-api ($OllamaUrl)" }
    return $missing
}

function Test-ModelAvailable {
    try {
        $r = Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 5
        $names = @($r.models | ForEach-Object { $_.name })
        return ($names -contains $Model)
    } catch { return $false }
}

function Get-Sha12 {
    param([string]$Path)
    $h = Get-FileHash -Algorithm SHA256 -Path $Path
    return $h.Hash.Substring(0, 12).ToLower()
}

function Get-PdfText {
    param([string]$Path, [int]$MaxChars = 4000)
    $tmp = [System.IO.Path]::GetTempFileName()
    # 临时降级: pdftotext 对中文 PDF (Adobe-GB1) / 扫描件常吐 stderr warning,
    # 在 ErrorActionPreference='Stop' 下会被当致命错误. 在本函数内改 Continue.
    $savedEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # -l 8: 只抽前 8 页, 对大书够用. 合并 stderr 到 stdout 再丢给 Out-Null, 避免 NativeCommandError.
        & pdftotext -l 8 -layout $Path $tmp 2>&1 | Out-Null
        if (-not (Test-Path $tmp)) { return @{ Text = ""; Pages = 0 } }
        $text = Get-Content $tmp -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if (-not $text) { $text = "" }
        $text = $text -replace '\s+', ' ' -replace '\x00', ''
        if ($text.Length -gt $MaxChars) { $text = $text.Substring(0, $MaxChars) }

        $pages = 0
        try {
            $info = & pdfinfo $Path 2>&1
            $pageLine = $info | Where-Object { $_ -match '^Pages:\s+(\d+)' }
            if ($pageLine -match '^Pages:\s+(\d+)') { $pages = [int]$Matches[1] }
        } catch {}
        return @{ Text = $text; Pages = $pages }
    }
    finally {
        Remove-Item $tmp -ErrorAction SilentlyContinue
        $ErrorActionPreference = $savedEAP
    }
}

function Invoke-Ollama {
    param(
        [string]$System,
        [string]$UserMsg,
        [int]$Timeout = 180
    )
    # 用 chat API + messages 数组, 让 few-shot 清晰分成 user/assistant 对话, 避免模型把 system 里的 few-shot 直接当答案复制
    # few-shot 样例从 $global:FewShotExamples 读 (见 prompt 初始化)
    $messages = @(
        @{ role = "system"; content = $System }
    )
    foreach ($ex in $global:FewShotExamples) {
        $messages += @{ role = "user"; content = $ex.input }
        $messages += @{ role = "assistant"; content = $ex.output }
    }
    $messages += @{ role = "user"; content = $UserMsg }

    $body = @{
        model    = $Model
        messages = $messages
        format   = "json"
        stream   = $false
        options  = @{
            temperature = 0.1
            num_ctx     = 16384
            seed        = 42
        }
    } | ConvertTo-Json -Depth 20 -Compress

    $resp = Invoke-RestMethod -Uri "$OllamaUrl/api/chat" -Method Post -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec $Timeout
    return $resp.message.content
}

function Test-JsonValid {
    param($Obj)
    $required = @("category","tier_a_dir","tier_b_dir","slug","title_zh","summary_zh","tags","sensitive","confidence")
    foreach ($k in $required) {
        if (-not $Obj.PSObject.Properties.Name.Contains($k)) { return "missing-field:$k" }
    }
    $allowed = @("invoice","tax","bank-statement","housing","identity","medical","contract","education","inburgering","business","certificate","picture-book","book","paper","latex-project","code-snippet","design","other")
    if ($allowed -notcontains $Obj.category) { return "bad-category:$($Obj.category)" }
    if ($Obj.slug -notmatch '^[a-z0-9][a-z0-9-]{0,80}$') { return "bad-slug:$($Obj.slug)" }
    if ($Obj.tags.Count -lt 2) { return "too-few-tags" }
    if ($Obj.confidence -isnot [double] -and $Obj.confidence -isnot [decimal] -and $Obj.confidence -isnot [int]) { return "bad-confidence-type" }
    if ($Obj.confidence -lt 0 -or $Obj.confidence -gt 1) { return "bad-confidence-range" }
    return $null
}

# ============================================================
# 主流程
# ============================================================

Write-Host ""
Write-Host "=== brain-asset-pdf-local.ps1 ===" -ForegroundColor Cyan
Write-Host "  Model: $Model"
Write-Host "  Ollama: $OllamaUrl"
Write-Host "  Inbox: $InboxDir"
Write-Host "  Output: $OutputDir"
Write-Host "  MaxItems: $(if ($MaxItems -gt 0) { $MaxItems } else { 'all' })"
Write-Host "  DryRun: $DryRun"
Write-Host ""

Write-Host "检查前置..." -ForegroundColor Yellow
$missing = Test-Prereq
if ($missing.Count -gt 0) {
    Write-Host "  缺: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "  先装好 pdftotext (poppler) + 起 ollama serve" -ForegroundColor Red
    exit 1
}
Write-Host "  pdftotext: OK"
Write-Host "  ollama API: OK"

if (-not (Test-ModelAvailable)) {
    Write-Host "  模型 '$Model' 未 pull. 运行: ollama pull $Model" -ForegroundColor Red
    exit 1
}
Write-Host "  模型 '$Model': OK"
Write-Host ""

if (-not $DryRun -and -not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$pdfs = @(Get-ChildItem $InboxDir -Filter "*.pdf" -ErrorAction SilentlyContinue)
if ($MaxItems -gt 0) { $pdfs = $pdfs | Select-Object -First $MaxItems }
Write-Host "找到 $($pdfs.Count) 份 PDF 待处理" -ForegroundColor Yellow
Write-Host ""

$needsReviewLog = Join-Path $OutputDir "needs-review.tsv"
if (-not $DryRun -and -not (Test-Path $needsReviewLog)) {
    "sha12`tfilename`treason`ttimestamp" | Out-File $needsReviewLog -Encoding UTF8
}

$stats = @{ OK = 0; LOW_CONF = 0; SCHEMA_FAIL = 0; OLLAMA_FAIL = 0; SKIP_EXIST = 0; UNEXPECTED = 0 }
$i = 0
foreach ($pdf in $pdfs) {
    $i++
    Write-Host ("[{0}/{1}] {2}" -f $i, $pdfs.Count, $pdf.Name) -ForegroundColor Cyan

    # 兜底: 任何没被内部 try 捕获的意外 (damaged PDF, IO error, etc.)
    # 都在这里兜住, 写 needs-review 并继续下一份, 不能带崩整个 batch.
    try {

    $sha12 = Get-Sha12 -Path $pdf.FullName
    $outJson = Join-Path $OutputDir "$sha12.json"

    if ((Test-Path $outJson) -and -not $DryRun) {
        Write-Host "  跳 (已有 proposal): $sha12.json" -ForegroundColor DarkGray
        $stats.SKIP_EXIST++
        continue
    }

    # 1. 抽文本
    $textData = Get-PdfText -Path $pdf.FullName -MaxChars 4000
    $sizeMb = [Math]::Round($pdf.Length / 1MB, 2)

    $userMsg = @"
FILENAME: $($pdf.Name)
SIZE: $sizeMb MB
PAGES: $($textData.Pages)
TEXT_SAMPLE:
$($textData.Text)
"@

    # 2. 调 Ollama
    $t0 = Get-Date
    try {
        $respText = Invoke-Ollama -System $systemPrompt -UserMsg $userMsg -Timeout $TimeoutSec
    } catch {
        $ms = [int]((Get-Date) - $t0).TotalMilliseconds
        Write-Host "  × Ollama 失败: $_" -ForegroundColor Red
        if (-not $DryRun) {
            "$sha12`t$($pdf.Name)`tollama-fail: $_`t$(Get-Date -Format o)" | Add-Content $needsReviewLog -Encoding UTF8
            Write-TelemetrySafe -Entry @{
                task         = "pdf-classify"
                executor     = "local"
                model        = $Model
                duration_ms  = $ms
                schema_valid = $false
                escalated    = $false
                source       = $pdf.FullName
                source_hash  = $sha12
                retry_reason = "ollama-fail"
            }
        }
        $stats.OLLAMA_FAIL++
        continue
    }
    $ms = [int]((Get-Date) - $t0).TotalMilliseconds

    # 3. 解析 + 校验
    try {
        $obj = $respText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Host "  × JSON 解析失败" -ForegroundColor Red
        if (-not $DryRun) {
            "$sha12`t$($pdf.Name)`tjson-parse-fail`t$(Get-Date -Format o)" | Add-Content $needsReviewLog -Encoding UTF8
            Write-TelemetrySafe -Entry @{
                task         = "pdf-classify"
                executor     = "local"
                model        = $Model
                duration_ms  = $ms
                schema_valid = $false
                escalated    = $false
                source       = $pdf.FullName
                source_hash  = $sha12
                retry_reason = "json-parse-fail"
            }
        }
        $stats.SCHEMA_FAIL++
        continue
    }
    $schemaErr = Test-JsonValid -Obj $obj
    if ($schemaErr) {
        Write-Host "  × schema 不合: $schemaErr" -ForegroundColor Red
        if (-not $DryRun) {
            "$sha12`t$($pdf.Name)`tschema: $schemaErr`t$(Get-Date -Format o)" | Add-Content $needsReviewLog -Encoding UTF8
            Write-EscalationItemSafe `
                -Reason "schema_fail" `
                -SourcePath $pdf.FullName `
                -SourceFileName $pdf.Name `
                -SourceHash $sha12 `
                -DurationMs $ms `
                -Confidence 0 `
                -SchemaValid $false `
                -RawOutput $respText
            Write-TelemetrySafe -Entry @{
                task         = "pdf-classify"
                executor     = "local"
                model        = $Model
                duration_ms  = $ms
                schema_valid = $false
                escalated    = $false
                source       = $pdf.FullName
                source_hash  = $sha12
                retry_reason = "schema-fail"
            }
        }
        $stats.SCHEMA_FAIL++
        continue
    }

    # 4. 加元信息, 写 proposal
    $proposal = [PSCustomObject]@{
        sha12             = $sha12
        source_filename   = $pdf.Name
        source_fullpath   = $pdf.FullName
        source_size_bytes = $pdf.Length
        model             = $Model
        prompt_version    = "v1-2026-04-19"
        processed_at      = (Get-Date).ToString("o")
        elapsed_ms        = $ms
        classification    = $obj
    }

    $lowConf = ($obj.confidence -lt $LowConfThreshold)
    $confMark = if ($lowConf) { "[低置信]" } else { "" }
    Write-Host ("  OK {0,5}ms  {1,-14}  {2}  conf={3:N2} {4}" -f $ms, $obj.category, $obj.slug, $obj.confidence, $confMark) -ForegroundColor Green

    if ($DryRun) {
        $obj | ConvertTo-Json -Depth 10 | Out-Host
    } else {
        $proposal | ConvertTo-Json -Depth 10 | Out-File -FilePath $outJson -Encoding UTF8
        if ($lowConf) {
            "$sha12`t$($pdf.Name)`tlow-confidence: $($obj.confidence)`t$(Get-Date -Format o)" | Add-Content $needsReviewLog -Encoding UTF8
            Write-EscalationItemSafe `
                -Reason "confidence_below_threshold" `
                -SourcePath $pdf.FullName `
                -SourceFileName $pdf.Name `
                -SourceHash $sha12 `
                -DurationMs $ms `
                -Confidence ([double]$obj.confidence) `
                -SchemaValid $true `
                -RawOutput $respText
            Write-TelemetrySafe -Entry @{
                task          = "pdf-classify"
                executor      = "local"
                model         = $Model
                duration_ms   = $ms
                schema_valid  = $true
                escalated     = $true
                confidence    = $obj.confidence
                category      = $obj.category
                source        = $pdf.FullName
                source_hash   = $sha12
                output_summary = $obj.reasoning_brief
                retry_reason  = "confidence_below_threshold"
                qa_verdict    = "unsampled"
            }
            $stats.LOW_CONF++
        } else {
            Write-TelemetrySafe -Entry @{
                task           = "pdf-classify"
                executor       = "local"
                model          = $Model
                duration_ms    = $ms
                schema_valid   = $true
                escalated      = $false
                confidence     = $obj.confidence
                category       = $obj.category
                source         = $pdf.FullName
                source_hash    = $sha12
                output_summary = $obj.reasoning_brief
                qa_verdict     = "unsampled"
            }
            $stats.OK++
        }
    }

    } catch {
        Write-Host "  !!! 意外错误: $_" -ForegroundColor Red
        if (-not $DryRun) {
            $shaSafe = if ($sha12) { $sha12 } else { "unknown" }
            "$shaSafe`t$($pdf.Name)`tunexpected: $_`t$(Get-Date -Format o)" | Add-Content $needsReviewLog -Encoding UTF8
            Write-TelemetrySafe -Entry @{
                task         = "pdf-classify"
                executor     = "local"
                model        = $Model
                duration_ms  = 0
                schema_valid = $false
                escalated    = $false
                source       = $pdf.FullName
                source_hash  = $shaSafe
                retry_reason = "unexpected"
            }
        }
        $stats.UNEXPECTED++
        continue
    }
}

Write-Host ""
Write-Host "=== 完成 ===" -ForegroundColor Cyan
Write-Host ("  OK (高置信):   {0}" -f $stats.OK)
Write-Host ("  低置信:        {0}  (进 needs-review)" -f $stats.LOW_CONF)
Write-Host ("  schema 失败:   {0}" -f $stats.SCHEMA_FAIL)
Write-Host ("  Ollama 失败:   {0}" -f $stats.OLLAMA_FAIL)
Write-Host ("  意外错误:      {0}" -f $stats.UNEXPECTED)
Write-Host ("  跳过已存在:    {0}" -f $stats.SKIP_EXIST)
Write-Host ""
if (-not $DryRun) {
    Write-Host "proposals:   $OutputDir\*.json"
    Write-Host "需 QA 的:    $needsReviewLog"
    Write-Host ""
    Write-Host "下一步: 跑 brain-asset-pdf-qa.ps1 抽查, 或 brain-asset-pdf-apply.ps1 落盘" -ForegroundColor Yellow
}
