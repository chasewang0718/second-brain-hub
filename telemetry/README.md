# telemetry/

**运行日志 + 成本/准确率分析**.

每次 LLM 调用记一行 JSONL. 周/月分析看趋势.

## 结构

```
logs/                         按月滚动 (.gitignored)
  2026-04.jsonl
  2026-05.jsonl
schema.md                     日志字段定义
analyze.ps1                   分析脚本: 出周报
```

## JSONL 单行格式 (参见 schema.md)

```json
{
  "ts": "2026-04-19T14:23:11Z",
  "task": "pdf-classify",
  "executor": "local",
  "model": "qwen2.5:14b-instruct",
  "input_tokens": 3421,
  "output_tokens": 287,
  "duration_ms": 42100,
  "confidence": 0.92,
  "escalated": false,
  "schema_valid": true,
  "source": "D:\\brain-assets\\99-inbox\\xxx.pdf",
  "output_summary": "invoice / 2024-05"
}
```

## 分析

```powershell
.\telemetry\analyze.ps1 -Days 7    # 近 7 天
.\telemetry\analyze.ps1 -Month 2026-04
```

输出: 各任务调用次数, 本地/云端比例, 平均置信, 升云率, 估算 $.

## 隐私

- `source` 只记录**文件路径**, 不记录文件**内容**
- `output_summary` 记录摘要前 50 字符, 不含敏感数据
- 不把日志推 GitHub (已 .gitignore), 仅本地
