# Phase 1 · 闭合反馈环 (MVP Self-Improving)

**状态**: 🟡 待启动
**预估总工时**: ~16 小时
**建议周期**: 2-3 个周末
**优先级**: 🔥🔥🔥 最高 —— 不要跳过

---

## 为什么这是 Phase 1

没有 feedback loop 的 LLM 系统会在 3 个月内因为 prompt 改烂而废掉。
这个 Phase 做完，hub 才真正从"一份精心设计的蓝图"变成"活的、会变聪明的系统"。

**量化退出指标**: 能画出一条 "每周低置信率" 下降曲线。

---

## 7 个子任务

### 1.1 · worker 写 telemetry JSONL
**状态**: ⬜ 待做
**估时**: 2h
**依赖**: 无
**改动文件**: `tools/ollama-pipeline/brain-asset-pdf-local.ps1`

**内容**:
- worker 每次调 Ollama 完成 (OK / LOW_CONF / SCHEMA_FAIL / OLLAMA_FAIL) 写一行 JSONL
- 字段按 `telemetry/schema.md` 定义（task, executor, model, duration_ms, confidence, cost_usd=0, 等）
- 写到 `telemetry/logs/YYYY-MM-DD.jsonl`（按日切分）
- 用 `Add-Content` + `ConvertTo-Json -Compress`

**验收**:
```powershell
Get-Content C:\dev-projects\second-brain-hub\telemetry\logs\$(Get-Date -Format yyyy-MM-dd).jsonl | Select -First 3
# 应看到 3 行有效 JSON
```

---

### 1.2 · 低置信 / fail 导出结构化 escalation
**状态**: ⬜ 待做
**估时**: 1h
**依赖**: 无（可与 1.1 并行）
**改动文件**: `tools/ollama-pipeline/brain-asset-pdf-local.ps1`

**内容**:
- 目前低置信只吐 `needs-review.tsv`（纯文本日志）
- 补一份结构化：写 `D:\brain-assets\_escalation\<sha12>.json`
- 内容: `{ sha12, source_filename, reason, text_sample, proposal, ts }`
- 云端或人工审完后写 `<sha12>.processed.json` 带 corrected 字段

**验收**: `_escalation/` 目录下出现 N 个 json，schema 合规。

---

### 1.3 · feedback harvester 脚本
**状态**: ⬜ 待做
**估时**: 3h
**依赖**: 1.2
**新建文件**: `tools/feedback/harvest-feedback.ps1`

**内容**:
- 扫 `_escalation/*.processed.json`（云端/人工已审完的）
- 抽取 `{input, corrected_output}` 对
- 追加到 `prompts/few-shot/pdf/<category>.json`
- 去重（按 sha12）
- 运行后把原 `.processed.json` 移到 `_escalation/applied/`

**验收**:
- 手工标注 1 个 `.processed.json`，跑 harvester
- 检查 `prompts/few-shot/pdf/` 多了一条
- 下次 pipeline 启动时 `Get-Content prompt-template.md` 会自动读到新 few-shot（因为 worker 现在就是每次重读）

---

### 1.4 · task-router.yaml 变成运行时配置
**状态**: ⬜ 待做
**估时**: 4h
**依赖**: 无
**新建文件**: `tools/lib/task-router.ps1`
**改动文件**: `tools/ollama-pipeline/brain-asset-pdf-local.ps1`, `brain-asset-pdf-pipeline.ps1`

**内容**:
- 写 `Read-TaskConfig` 函数（PS 读 YAML，可用 `powershell-yaml` 模块或手工 parse）
- 返回指定 task 的配置（model, timeout, confidence_threshold 等）
- worker 从调用变成：`$cfg = Read-TaskConfig -Task 'pdf-classify'; & $cfg.primary.model ...`
- 删除 worker 里的硬编码参数

**验收**:
- 改 `config/task-router.yaml` 里 `pdf-classify.primary.model`
- 下次跑 worker 真的用新模型（不需要改代码）

---

### 1.5 · Golden set v1（20 份人工金标）
**状态**: ⬜ 待做
**估时**: 2h（一次性手工劳动）
**依赖**: 量产完成（Phase 0 的 655 份跑完）
**新建文件**: `evals/pdf-classify/golden-set/*.json`

**内容**:
- 从 655 份里挑 20 份覆盖各 category（invoice/tax/book/picture-book/education/inburgering/identity/other 等）
- 每份手工标注"正确的"分类 + slug + key tags
- 一个样本一个 json，带 `sha12`, `expected.category`, `expected.tier_a_dir`, `expected.slug`, `expected.tags[0..2]`
- 写个 `evals/pdf-classify/golden-set/README.md` 说明选样原则

**验收**: `Get-ChildItem evals/pdf-classify/golden-set/*.json | Measure-Object` 返回 ≥ 20。

---

### 1.6 · eval runner
**状态**: ⬜ 待做
**估时**: 3h
**依赖**: 1.5
**新建文件**: `evals/run-pdf-classify.ps1`

**内容**:
- 读 `golden-set/*.json`
- 对每份：找到对应的 PDF → 跑一次 worker（dry-run，不写盘）→ 对比 expected vs actual
- 输出：
  - 准确率（category 完全匹配比例）
  - 近似分（tier_a_dir 对 +0.5，tag 交集 ≥1 +0.3）
  - 每份 diff 详情 → `evals/pdf-classify/results/YYYY-MM-DD.md`
- 支持 `-Model` 参数切换模型做 A/B

**验收**: 跑 `run-pdf-classify.ps1 -Model qwen2.5:14b-instruct` 出报告。跑 `-Model gemma2:9b` 对比。

---

### 1.7 · telemetry 月度成本报告 UX
**状态**: ⬜ 待做
**估时**: 1h
**依赖**: 1.1（有数据才能分析）
**改动文件**: `telemetry/analyze.ps1`

**内容**:
- `analyze.ps1` 已经基本能用
- 加一个 `-PromptMode` 参数：输出不仅是 Markdown 报告，还有"上个月你在哪里最费钱"的一句话总结
- 顺便加个 PS profile 别名 `gbrain-cost`

**验收**: 敲 `gbrain-cost` 出月度报告。

---

## 跟踪表（手工勾选法，别搞复杂）

| # | 任务 | 估时 | 状态 | 完成日期 | 备注 |
|---|---|---|---|---|---|
| 1.1 | telemetry JSONL 打点 | 2h | ⬜ | | |
| 1.2 | escalation 结构化导出 | 1h | ⬜ | | |
| 1.3 | feedback harvester | 3h | ⬜ | | |
| 1.4 | task-router 运行时读取 | 4h | ⬜ | | |
| 1.5 | Golden set v1 (20 份) | 2h | ⬜ | | |
| 1.6 | eval runner | 3h | ⬜ | | |
| 1.7 | 月度成本报告 UX | 1h | ⬜ | | |
| **合计** | | **16h** | | | ≈ 3 个周末 |

---

## 推荐做的顺序

```
Week 1 周末:
  1.1 → 1.2 (3h, 并行容易)      ← 打下数据采集地基
  1.5 (2h)                        ← 金标是体力活, 先做完省心

Week 2 周末:
  1.6 (3h)                        ← 有金标立刻做 eval runner, 马上能看分
  1.4 (4h)                        ← 把配置变活

Week 3 周末:
  1.3 (3h)                        ← feedback harvester, 最后装上闭环
  1.7 (1h)                        ← 收尾, 月度报告
  留 2h 处理踩坑                  ← 肯定有
```

---

## 常见陷阱 (预警)

1. **PowerShell YAML 解析**: `Install-Module powershell-yaml` 需要管理员，或者用 `ConvertFrom-Yaml` 自己写简易 parser。预估 1-2h 调通。
2. **JSONL 多进程写冲突**: worker 并行时多进程同时 Append 会乱。Phase 1 worker 是单进程，暂时不是问题，但 Phase 2 要记住加锁。
3. **Golden set 偏样本**: 挑的 20 份容易集中在简单类别（picture-book/tax）。刻意加 3-5 份 low-conf / other / edge case。
4. **Eval 噪声**: 本地 LLM 有随机性（temperature > 0）。考虑 `seed` 参数或每份跑 3 次取众数。

---

## 完成 Phase 1 后你拥有什么

- ✅ 每次 worker 跑都有可追溯的日志
- ✅ 改 prompt / 换模型前能立刻看分回归
- ✅ 人工修正的样本自动进 few-shot，下次启动生效
- ✅ yaml 里改参数不再需要改代码
- ✅ 月度清楚自己花了多少钱在哪里

**换句话说**: hub 从"蓝图"变成了"活系统"。后面 Phase 2-7 都站在这个基础上。
