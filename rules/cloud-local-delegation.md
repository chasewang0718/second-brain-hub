---
title: 云-本地 AI 协作通用策略
tags: [rules, architecture, cost-optimization, authoritative-source]
created: 2026-04-19
updated: 2026-04-19
status: active-v1
authoritative_at: C:\dev-projects\second-brain-hub\rules\cloud-local-delegation.md
---

# 云-本地 AI 协作通用策略 (v1)

> **一句话心智**: 能本地跑就本地跑, 云端做**决策 / 验收 / 兜底**, 省 token = 省钱 = 更大胆使用 AI.

## 0. 适用范围

本策略**通用于所有 AI 调用场景**, 不限于 PDF 分类:
- PDF / 图片 / 音频的批量分类
- Inbox 纯文本路由 (paste-*.md 归档)
- Inbox 文件路由 (丢进 99-inbox 的任何格式)
- Caps+D 交互式快速修复
- 未来的新任务类型 (代码审查/翻译/摘要/...)

每类任务在 [`config/task-router.yaml`](../config/task-router.yaml) 里登记即生效,
不需要改代码逻辑.

---

## 1. 核心原则

### 原则 1: 本地优先 (Local-First)

**默认所有批量任务先走本地**. 不要预设"这个任务太复杂, 本地搞不定".
先让本地跑, 真搞不定了有明确机制升云.

**反例**: "这份 PDF 看起来很长, 直接给云端吧" —— ❌ 先让本地跑, 超 timeout 再升云.

### 原则 2: 云端做三件事

| 角色 | 做什么 |
|---|---|
| **决策者** (Dispatcher) | 看到新任务, 判断该走哪条流水线, 怎么配置 |
| **验收者** (QA) | 抽样审计本地产出 (默认 15%), 发现系统性问题 |
| **兜底者** (Escalator) | 处理本地跑不出的疑难杂症 (低置信/schema 失败/超时/敏感) |

**云端不干重复性脏活**. 清点、搜索、匹配、移动文件 —— 永远本地/脚本.

### 原则 3: 升云要可判

所有"升云"的触发条件必须是**机器可判的 4 类**, 不能靠"AI 觉得"或"人觉得":

| 类别 | 例子 | 机器判据 |
|---|---|---|
| **Quality** | 本地答案不靠谱 | `confidence < 阈值` / JSON Schema 校验失败 |
| **Complexity** | 任务本身超本地能力 | 跨 N 文件 / 触发"refactor"关键词 / 新建顶层概念 |
| **Risk** | 后果严重, 需要更强保险 | 敏感数据 / 破坏性操作 (删/移) / `git push --force` |
| **Budget** | 资源耗尽 | 本地推理 > timeout / 本月云预算剩余 < X USD |

### 原则 4: 省 token 是目的, 不是 KPI

- 本地干活**不收费**, 但耗电耗时;
- 云端**收费**, 但快且聪明;
- 什么任务走哪边, 以"整体 ROI 最高"为准, 不死守"省云 token"单指标.

---

## 2. 三种工作模式

每个任务根据**交互性**和**规模**, 自动落到三种模式之一. 配置在 `task-router.yaml`.

### 模式 A: 流水线模式 (batch pipeline)

**适用**: PDF 分类 / 图片归档 / 音频转录 / 邮件批量整理等.

```
云端 (决策)
  └─ 定策略 (哪些文件、什么 prompt、怎么输出)
  └─ 派发给本地 worker
       └─ 本地循环跑 N 份, 每份产 JSON proposal
            └─ 云端抽样 QA (默认 15%)
                 ├─ pass → 进入 apply 阶段, 落盘 + commit
                 ├─ fail sample → 整批停, 云端诊断 prompt/model
                 └─ 低置信个体 → 入 escalation-queue, 云端兜底
```

**关键特性**:
- 批量 → 本地单价 = 0
- QA 抽样比例随成熟度下降 (新 prompt 30% → 稳定后 10%)
- 兜底队列异步处理, 不阻塞主流程

### 模式 B: 交互模式 (interactive)

**适用**: Caps+D 快速修复 / 对话问答 / 内联建议.

```
用户触发
  └─ 本地小模型 (2-3B) 即时响应 (<2 秒)
       ├─ 置信够 → 直接落地
       └─ 超阈值 / 用户拒 → 升云重做
            └─ 云端 / 交互式 agent
```

**关键特性**:
- 响应速度优先. 用户等着, 不能 30 秒推理.
- 本地模型要小 (gemma2:2b, qwen2.5:3b)
- 用户 review 频繁, 所以 QA 可以省掉 (用户自己就是 QA)

### 模式 C: 长任务模式 (long-running agent)

**适用**: 代码重构 / 复杂写作 / 多步骤调研.

```
云端 agent 全程主导
  └─ 需要 grep/ls/读文件/移动文件 时
       └─ 本地脚本作"脏活工具" (tool-calling)
            └─ 结果回传云端继续推理
```

**关键特性**:
- **不适合 local-first**: 任务本身需要长链路推理, 本地模型压不住
- 本地的作用是"脚手架" (搜索/文件操作/验证)
- 成本较高, 但用于"真正难"的任务有价值

---

## 3. 升云触发器 (Escalation Triggers)

### Quality (质量)

| 触发条件 | 触发动作 |
|---|---|
| `confidence < task.escalate_when.confidence_below` | 本地不 commit, 进 escalation-queue |
| JSON Schema 校验失败 2 次 | 本地停, 升云重做 |
| 本地输出含关键"不确定"表达 (如 "可能", "大概") | 降权重 confidence, 若低于阈值升云 |

### Complexity (复杂度)

| 触发条件 | 触发动作 |
|---|---|
| 任务元数据声明 "involves_refactor" | 直接走模式 C, 不进本地 |
| `touches_files_count > task.escalate_when.touches_files_count_above` | 升云 |
| 新建概念 / 顶层目录 | 保守起见升云 (L1 权限下放 AI, 但需更强判断) |

### Risk (风险)

| 触发条件 | 触发动作 |
|---|---|
| 源路径命中 Tier C 黑名单 | **立即终止**, 不升云也不本地 |
| 涉及 `git push --force` / `git reset --hard` / 删 `.git/` | L3 权限, 必须用户确认 |
| 文档含敏感字段 (证件号/金额/密码关键词) | 标 `sensitive: true`, 标签化写入但摘要脱敏 |

### Budget (预算)

| 触发条件 | 触发动作 |
|---|---|
| 本地推理超 `task.timeout` 秒 | kill 进程, 入 escalation-queue |
| 本月云 token 预算剩余 < 20% | 降低 QA 抽样率, 升云门槛提高 |
| 本月云 token 预算剩余 < 5% | 停止所有主动升云, 只处理 L3 风险 |

---

## 4. 兜底队列 (escalation-queue)

### 存储位置

```
D:\brain-assets\_escalation\
  YYYY-MM-DD_task-id_source-hash.json
```

每条目 Schema 见 [`schemas/escalation-item.schema.json`](../schemas/escalation-item.schema.json) (待建).

### 条目格式 (概念)

```json
{
  "ts": "2026-04-19T22:00:00Z",
  "task": "pdf-classify",
  "source": "D:\\brain-assets\\99-inbox\\foo.pdf",
  "local_attempt": {
    "model": "qwen2.5:14b-instruct",
    "confidence": 0.42,
    "schema_valid": true,
    "duration_ms": 280000,
    "raw_output": "..."
  },
  "reason": "confidence_below_threshold",
  "priority": "normal",
  "status": "pending"
}
```

### 云端处理流程

1. 云端 agent 定时扫 `_escalation/` (或用户显式 `gescalate` 触发)
2. 按 priority 排序处理 (high 先于 normal)
3. 云端读本地的 `raw_output` 作**参考**, 不盲信
4. 产出的结果走**原任务的 apply 流程** (不新建逻辑)
5. 处理完改 `status: processed`, 保留审计

### 反馈循环 (重要!)

- 兜底处理的每一份 → 提炼为新 few-shot, 加入 `prompts/few-shot/`
- 这样本地模型下次遇到类似 PDF 就能搞定, **逐步减少升云率**
- 每周跑一次 evals, 看本地准确率提升轨迹

---

## 5. 成本约束 (Cost Guardrails)

见 [`architecture/cost-model.md`](../architecture/cost-model.md) (待建)  完整版. 纲要:

### 月度预算

| 项 | 预算 | 现状 (需 telemetry 确认) |
|---|---|---|
| 云端 LLM (Claude/GPT) | $20 USD/月 | 待数据 |
| 本地 Ollama 耗电 | 忽略 (< $2/月) | 约 150W × 日均 2h |
| GitHub 存储 | $0 (私仓免费额度内) | — |
| 百度网盘 SVIP | ¥298/年 (可选) | 未付费, 用免费版 |

### 预警阈值

- 月度云 token 用到 **70%** → `analyze.ps1` 周报标黄
- 用到 **90%** → 自动降 QA 抽样率从 15% → 5%
- 用到 **100%** → 降级到"纯本地 + 人工验收"模式, 直到月底

---

## 6. 实现状态 (v1 = 本文件; 后续迭代在 CHANGELOG.md 记录)

### ✅ 已实现

- PDF 分类流水线 (模式 A): `tools/ollama-pipeline/` + `prompts/system/pdf-classifier.md`
- QA 抽样: `brain-asset-pdf-qa.ps1` 调 cursor-agent 审 15%
- 置信阈值: 目前写在 `brain-asset-pdf-local.ps1` 里 (待迁 `config/thresholds.yaml`)

### ⏳ 计划中

- `config/task-router.yaml` — 登记所有任务路由 (本文件的计算机可读伴侣)
- `config/thresholds.yaml` — 统一阈值表
- `config/paths.yaml` — 所有路径集中管理
- `tools/dispatcher/` — 读 task-router.yaml 的通用派发器
- `tools/escalation/` — escalation-queue 消化器
- `prompts/system/inbox-text-router.md` — 纯文本 inbox 路由
- `prompts/system/capsd-quick-fix.md` — Caps+D 模型
- `telemetry/` — 所有 AI 调用的日志与成本分析

### 🎯 待决策

- 当本地模型准确率足够 (如 > 95%), **QA 抽样率降到多少**? 5%? 1%? 全省?
- 升云后的"反馈循环"(把 escalation 结果加回 few-shot) 自动化到什么程度?
- 多本地模型共存时 (qwen2.5:14b 分类, gemma2:2b Caps+D, llava:13b 图像),
  GPU/VRAM 调度策略?

---

## 7. 与其他规则的关系

- **AGENTS.md** §11 (资产管理协议): 本策略是 §11 Tier B 处理的**实现细节展开**
- **privacy.md**: 本策略**必须遵守** `privacy.md` 的 Tier C 黑名单, 命中即终止 (不本地也不升云)
- **inbox-ingest.md**: inbox 的 auto-trigger 未来应改为"先本地分类, 低置信升云",
  即把 inbox 整理也纳入本策略

---

## 8. 一句话心智 (再说一次, 因为重要)

> **本地先跑 + 云端验收兜底 + 兜底结果反哺本地 = 准确率爬坡 × 成本爬降 的正反馈循环.**
