# Telemetry JSONL Schema

每次 LLM 调用写一行 JSON 到 `logs/YYYY-MM.jsonl`.

## 字段

### 必填

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts` | string (ISO 8601) | 调用开始时间, UTC `2026-04-19T22:00:00Z` |
| `task` | string | 任务类型, 值来自 `config/task-router.yaml` 的 task 名: `pdf-classify`, `inbox-text-route`, `capsd-quick-fix`, `image-classify`, `code-refactor`, `qa-audit`, `escalation-handle` |
| `executor` | enum | `local` / `cloud` / `rule-based` |
| `model` | string | 具体模型: `qwen2.5:14b-instruct`, `claude-opus-4`, `rule-only` |
| `duration_ms` | number | 总耗时毫秒 (从请求到最终成功/失败) |
| `schema_valid` | boolean | 输出是否通过 JSON Schema 校验 |
| `escalated` | boolean | 是否升了云 (本地失败后由 fallback 处理) |

### 选填 (按任务填)

| 字段 | 类型 | 适用任务 |
|---|---|---|
| `input_tokens` | number | 所有 |
| `output_tokens` | number | 所有 |
| `cost_usd` | number | 云端 |
| `confidence` | number (0-1) | 产 JSON 的任务 |
| `category` | string | 分类类任务 |
| `source` | string | 文件路径 (脱敏前) |
| `source_hash` | string | sha256 前 12 位, 用于去重 / 联动 escalation |
| `output_summary` | string | 前 50 字符, **不含敏感信息** |
| `attempt_count` | number | 重试次数 |
| `retry_reason` | string | 重试原因 (schema-fail / timeout / other) |
| `qa_verdict` | enum | `pass` / `fail` / `unsampled` — QA 抽样是否命中 + 结果 |
| `qa_auditor_model` | string | 审计模型 |

## 示例行

### 本地 PDF 分类成功

```json
{"ts":"2026-04-19T22:01:15Z","task":"pdf-classify","executor":"local","model":"qwen2.5:14b-instruct","input_tokens":3421,"output_tokens":287,"duration_ms":42100,"confidence":0.92,"schema_valid":true,"escalated":false,"category":"invoice","source":"D:\\brain-assets\\99-inbox\\foo.pdf","source_hash":"a3c4d5e6f789","output_summary":"invoice / 2024-05 / ING","attempt_count":1,"qa_verdict":"unsampled"}
```

### 本地低置信 → 升云

```json
{"ts":"2026-04-19T22:03:22Z","task":"pdf-classify","executor":"local","model":"qwen2.5:14b-instruct","duration_ms":280000,"confidence":0.42,"schema_valid":true,"escalated":true,"source_hash":"b1c2d3e4f567","retry_reason":"confidence_below_threshold"}
{"ts":"2026-04-19T22:03:30Z","task":"escalation-handle","executor":"cloud","model":"claude-opus-4","input_tokens":4102,"output_tokens":356,"cost_usd":0.089,"duration_ms":12300,"confidence":0.95,"schema_valid":true,"escalated":false,"source_hash":"b1c2d3e4f567","category":"contract","qa_verdict":"pass"}
```

两条关联: 同 `source_hash`, 第一条 `escalated: true`, 第二条 task 是 `escalation-handle`.

### QA 抽样审计

```json
{"ts":"2026-04-19T22:15:00Z","task":"qa-audit","executor":"cloud","model":"claude-opus-4","input_tokens":2100,"output_tokens":120,"cost_usd":0.031,"duration_ms":8400,"schema_valid":true,"escalated":false,"qa_verdict":"pass","source_hash":"a3c4d5e6f789"}
```

## 隐私约束 (与 rules/privacy.md 一致)

- ❌ **不记录**: 文件原文内容 / 证件号 / 金额 / 密码 / 邮箱地址
- ✅ **可记录**: 文件路径 (脱敏版本) / 文件大小 / 摘要前 50 字符
- ⚠️ **Tier C 路径命中时**: 连 source 字段都不写, 只记 `task=blocked-tier-c`
- 日志**只本地**, `.gitignored`, 不推 GitHub

## 轮转

- 每月一个文件: `logs/2026-04.jsonl`, `logs/2026-05.jsonl`, ...
- 超 90 天的自动归档到 `logs/archive/` (压缩)
- 永不删除原始日志 (审计需要)

## 写入方式

推荐使用 `tools/lib/telemetry.ps1` 的 `Write-Telemetry` 函数 (待实现).
直接拼 JSON 字符串附加到文件即可, 无需加载整个 jsonl.

```powershell
$entry = @{ ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"); task = "pdf-classify"; ... }
$json = $entry | ConvertTo-Json -Compress
Add-Content -Path "$logsDir\$(Get-Date -Format yyyy-MM).jsonl" -Value $json -Encoding UTF8
```
