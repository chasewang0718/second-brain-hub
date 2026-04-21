---
title: Cursor-Delegated Escalation 策略 (v5)
status: authoritative
created: 2026-04-20
supersedes: cloud-local-delegation.md
---

# Cursor-Delegated Escalation 策略 (v5)

> 一句话: 本地 LLM 做不好的任务, 不自动调云端 API (0 预算), 也不无限重试, **入队**. 用户在 Cursor 里喊 "处理 cursor 队列" 时, 借 Cursor 订阅额度 (已付沉没成本) 逐个处理.

---

## 为什么不再用云端 API 自动兜底

v4 及之前的 `cloud-local-delegation.md` 策略:

- 本地置信度低 → 自动调 Claude Opus / GPT-5
- 每月预算 $50, 超支告警

v5 转向后的问题:

1. **预算硬约束改为 $0/月**: API 自动调用在任何语义下都产生增量支出
2. **Cursor 订阅已付**: $20/月已是 sunk cost, 不用白不用
3. **人工介入一次, 队列批量清**: 单次 "处理 cursor 队列" 可清 10-50 条, 比 10-50 次自动 API 调用便宜 10-50 倍
4. **Cursor 上下文更富**: Cursor 看得到你整个 hub 仓 + 内容仓, API 看不到

所以 v5 **取消所有自动云端兜底**. 失败任务**100% 入队**.

---

## 触发条件 (本地执行失败 → 入队)

任一命中就入队:

1. **Schema fail 达上限** (`max_retries_on_schema_fail: 2`)
2. **置信度低于阈值** (`confidence_below: 0.70` 默认, 各任务可覆盖)
3. **本地超时** (`timeout_sec` 超过)
4. **分类为 other** (无匹配类目)
5. **触碰 L2/L3 边界** (涉及 `00-memory/`, 新建顶级目录等)
6. **PII 命中后仍不确定去 Tier B 还是 Tier C**
7. **人工明确要求** (任务 metadata 里标 `force_cursor: true`)

## 入队结构

### 目录

```
D:\second-brain-assets\_cursor_queue\
  └─ YYYY-MM-DD_<task>_<uuid>.md        # 待处理
  └─ YYYY-MM-DD_<task>_<uuid>.processed.md  # Cursor 处理完
```

### 入队文件 schema (markdown + frontmatter)

```markdown
---
task: pdf-classify              # 来自 task-router.yaml 的 task key
source_file: "D:\\second-brain-assets\\99-inbox\\foo.pdf"
source_hash: sha256:abc...
created: 2026-04-20T15:04:05
local_attempt:
  model: qwen2.5:14b-instruct
  confidence: 0.58
  schema_fail_count: 2
  reason: "confidence_below_threshold"
suggested_action: classify_and_move
tier_hint: B                     # A/B/C, AI 推测
---

# 待 Cursor 处理的本地失败任务

## 本地尝试原始输出
<LLM 原始输出, 含 json 解析失败的片段>

## 本地上下文快照
<hub 相关 rule 片段 / 最近 3 次类似任务的结果 / ...>

## 处理方式
用户在 Cursor 里说 "处理 cursor 队列" → Cursor agent 读本文件 → 决策 → 写 `.processed.md` 同目录.
```

### 处理完 schema (`*.processed.md`)

```markdown
---
source_queue_file: "..._uuid.md"
processed_by: cursor-agent-<model>
processed_at: 2026-04-20T16:00:00
decision:
  action: moved_to
  target: "D:\\second-brain-assets\\10-papers\\2026\\..."
  pointer_md: "D:\\second-brain-content\\10-references\\..."
  tags: [...]
  tier: B
feedback_for_harvest:
  good_example: true              # 是否入 few-shot
  fix_category: null              # 若是分类修正, 写原值
---

# 处理记录
<Cursor 的决策理由, 做了什么, 为什么>
```

---

## 反馈闭环 (关键)

`.processed.md` 是**金矿**. Python `feedback` agent 定期扫描:

1. 扫 `*.processed.md` 里 `feedback_for_harvest.good_example=true` 的
2. 转为 few-shot 样本 → `prompts/few-shot/<task>/YYYY-MM-DD_<uuid>.json`
3. 下次本地 LLM 跑同类任务自动使用新 few-shot
4. 失败率理论上应逐月下降 (一个可观测指标)

**禁止**: 把 `.processed.md` 内容直接写入 training data (LoRA 已砍).

---

## 用户操作面

### 触发词

| 说什么 | AI 做什么 |
|---|---|
| "处理 cursor 队列" | 扫 `_cursor_queue/*.md` (非 processed), 逐个处理, 生成 `.processed.md`, commit |
| "cursor 队列多少" | 只读, 报告待处理数量 + 按 task 分组 |
| "清空 cursor 队列" | 把所有 `.processed.md` 归档到 `_cursor_queue/_archive/YYYY-MM/` |
| "跳过 cursor 队列 <task>" | 把某类 task 的未处理项标记为 skipped (不处理, 不归档) |

### 工作流示例

```
周五晚
  watchdog 发现 10 份新 PDF
  本地 qwen 跑 → 6 份成功归档, 4 份入 _cursor_queue/

周六早
  Chase: "处理 cursor 队列"
  Cursor agent: 扫出 4 个待处理, 逐个调用 claude-4.6-sonnet (Cursor 订阅额度)
                每个处理 2 分钟, 总共 8 分钟
                4 个 .processed.md 生成, auto-commit

周日
  feedback agent (每周跑): 扫 .processed.md, 3 条标 good_example=true
                          → 写 prompts/few-shot/pdf-classify/ 三条样本
                          → 本地 qwen 下周表现改善
```

---

## 与 `tools/py/` Python 栈的集成

**未实现阶段** (当前): 本文档是**设计**, 尚无代码.

**Phase F1 落地时**: Python agent 失败路径调用:
```python
from brain_core.escalation import enqueue_cursor
enqueue_cursor(
    task="pdf-classify",
    source_file=pdf_path,
    local_attempt=result,
    reason="confidence_below_threshold",
)
```

**Phase A3 落地时**: 批处理 watchdog 在本地失败后自动入队, 不调任何 API.

---

## 边缘情况

### 队列积压告警

- `_cursor_queue/` 超过 50 条未处理 → daily digest 里红字提醒
- 超过 100 条 → 在下次启动 Python CLI 时阻塞式提示

### Cursor 不可用 (离线)

- 队列只堆积, 不丢失
- 联网后一次性清

### 处理失败的失败 (Cursor 也搞不定)

- `.processed.md` 里写 `decision.action: defer_to_human`
- 转入 `D:\second-brain-content\99-inbox\_draft\` 供人工处理

---

## 对照 v4 / v5 的 delta

| 维度 | v4 "cloud-local-delegation" | v5 "cursor-delegated-escalation" |
|---|---|---|
| 兜底触发 | 自动 | 用户触发词 |
| 兜底模型 | Claude API 直连 | Cursor agent (内部可调任意模型) |
| 预算 | $50/月 | $0/月 (借 Cursor 订阅) |
| 上下文 | 随 API call 发 | Cursor 本身有完整仓访问 |
| 延迟 | 单任务秒级 | 批处理, 分钟到小时级 |
| 反馈闭环 | escalation_dir + harvest-feedback.ps1 | `_cursor_queue/*.processed.md` + Python harvest |

---

*本文件由 v5 架构新引入. 之前的 `cloud-local-delegation.md` 已标注废弃 (见该文件顶部).*
