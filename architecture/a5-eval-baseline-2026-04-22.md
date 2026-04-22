# A5 专项评估基线（who / overdue / context-for-meeting）

- 日期：2026-04-22
- 环境：`tools/py/.venv`（本机真实数据库）
- 命令：`python tools/py/tests/eval_people.py`

## 结果（静态 + 金标 + 动态真实样本）

```json
{
  "status": "ok",
  "total": 35,
  "passed": 35,
  "failed": 0,
  "static_cases": 12,
  "golden_cases": 12,
  "dynamic_cases_added": 11,
  "report": [
    {
      "id": "who_hammond_exact",
      "type": "who",
      "status": "pass",
      "rows": 1
    },
    {
      "id": "who_hammond_lowercase",
      "type": "who",
      "status": "pass",
      "rows": 1
    },
    {
      "id": "who_ham_prefix",
      "type": "who",
      "status": "pass",
      "rows": 5
    },
    {
      "id": "who_unknown_name_returns_empty",
      "type": "who",
      "status": "pass",
      "rows": 0
    },
    {
      "id": "overdue_wechat_30d_shape",
      "type": "overdue",
      "status": "pass",
      "rows": 1
    },
    {
      "id": "overdue_global_30d_shape",
      "type": "overdue",
      "status": "pass",
      "rows": 1
    },
    {
      "id": "overdue_channel_case_insensitive",
      "type": "overdue",
      "status": "pass",
      "rows": 1
    },
    {
      "id": "overdue_short_window_allows_empty",
      "type": "overdue",
      "status": "pass",
      "rows": 1
    },
    {
      "id": "context_hammond_json_shape",
      "type": "context",
      "status": "pass",
      "rows": 0
    },
    {
      "id": "context_hammond_json_since_7d",
      "type": "context",
      "status": "pass",
      "rows": 0
    },
    {
      "id": "context_hammond_markdown",
      "type": "context_md",
      "status": "pass",
      "chars": 147
    },
    {
      "id": "context_unknown_name_markdown",
      "type": "context_md",
      "status": "pass",
      "chars": 22
    },
    {
      "id": "dyn_who_recent_1",
      "type": "who",
      "status": "pass",
      "rows": 1
    },
    {
      "id": "dyn_context_interactions_1",
      "type": "context",
      "status": "pass",
      "rows": 5
    },
    {
      "id": "dyn_who_duplicate_name_1",
      "type": "who",
      "status": "pass",
      "rows": 10
    }
  ]
}
```

## 覆盖口径

- `who`：精确命中 / 大小写 / 前缀检索 / 不命中场景。
- `overdue`：全局与渠道筛选、渠道大小写容错、结构键检查。
- `context-for-meeting`：JSON 结构检查 + markdown 渲染检查（命中与未命中）。
- `golden set`：固定 12 条真实联系人回归（当前覆盖中英混名 + 高互动联系人）。
- `dynamic real samples`：每次运行自动从真实库抽样（最近联系人 6 条 + 高互动联系人 3 条 + 同名冲突 2 条）。
- `graph positive harness`：支持通过环境变量 `EVAL_PEOPLE_INCLUDE_GRAPH_POSITIVE=1` 启用共享标识符正例夹具（当前默认关闭，避免偶发 Kuzu 锁导致基线波动）。

## 下一步建议

- 继续扩充金标：加入“别名命中”与“同名异人”更强断言（当前金标以可读主名为主）。
- 新增 graph_hints 非空样本（当前是结构可用，尚未命中 shared_identifier 正例）。
- 将 `eval_people.py` 接入每周任务，按周落盘趋势（pass/fail 与 case 波动）。
