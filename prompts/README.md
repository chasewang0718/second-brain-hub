# prompts/

**投喂 LLM 的软规则**: system prompt + few-shot 样例.

## 结构

```
system/               每类任务一个 system prompt
  pdf-classifier.md
  inbox-text-router.md   (未来)
  inbox-file-router.md   (未来)
  capsd-quick-fix.md     (未来)
  escalation-handler.md  (未来: 云端处理兜底队列)

few-shot/             示例按任务分目录
  pdf/
    01-invoice.json        每个 .json 包含 {user_input, expected_output}
    02-bank-statement.json
    ...
```

## 约定

- System prompt 里**不要放具体路径** (路径在 `config/categories.yaml`, 通过代码注入)
- System prompt 里**不要写死分类枚举** (代码从 `schemas/*.schema.json` 读后拼入)
- Few-shot 独立成文件, 按需组合, 不要堆在 system prompt 里 (否则 token 爆炸)
- 每次修改必须更新 [CHANGELOG.md](../CHANGELOG.md) + 跑 eval
