# schemas/

**LLM 结构化输出契约** (JSON Schema Draft 2020-12).

给 Ollama `format: json` 用, 也给云端 agent 的 tool-calling 用, 也给代码侧做 validate.

## 文件

| 文件 | 用于 |
|---|---|
| `pdf-classify.schema.json` | PDF 分类任务输出 |
| `inbox-route.schema.json` | (未来) inbox item 路由决策输出 |
| `capsd-action.schema.json` | (未来) Caps+D 内联修复动作 |
| `escalation-item.schema.json` | (未来) 兜底队列条目格式 |

## 约定

- 每个 schema 的 `$id` 用 `https://brain-hub.local/schemas/<name>.json` (未实际解析, 纯标识)
- `additionalProperties: false` 是默认选择 (防 LLM 乱加字段)
- 改 schema = 破坏性变更, 必须:
  1. 更新 CHANGELOG
  2. 跑 eval 确认所有 golden 样本仍 pass
  3. 检查所有读该 schema 的代码是否兼容
