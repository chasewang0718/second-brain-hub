# second-brain-hub — Roadmap

**项目定性**: Personal Agentic IDP with Local-First Model Cascade
（个人级 · Agentic · 智能文档处理 · 本地优先 · 模型级联）

**愿景**: 24/7 运行的、比你更了解你过去的、隐私归你的、会自动变聪明的、可以被任何 AI 工具接入的"外脑 API"。

**起点**: 2026-04-19（hub 骨架 + 本地 PDF 分类 pipeline + L1 watchdog 完成）

**到达"完全形态"估计**: 12-18 个月（每周末 4-6h 节奏）

---

## 核心设计原则

1. **Local-first, cloud-last**。敏感数据永不出本机，云端只做脱敏摘要的审计 + 兜底。
2. **每个 Phase 自成闭环**。中途停下来系统依然能用；不搞"先挖半年地基再上线"。
3. **配置胜过代码**（`config/task-router.yaml`），提示词胜过算法（`prompts/`）。
4. **Evals 是纪律不是阶段**。每次 prompt/config 改动都要有数字兜底。
5. **Python 与 PowerShell 分工**: PS 做 Windows 胶水 + 工具调度；Python 做 agent + 向量 + ML。

---

## 真实难度分布

| 难度 | 占比 | 代表任务 |
|---|---|---|
| 🟢 琐碎（几小时-几天）| ~60% | telemetry 打点、escalation 导出、vector store、embed 入库、CLI 查询、llava/whisper 接入 |
| 🟡 中等（1-4 周）| ~25% | golden evals + CI、task-router 动态读取、proactive 周报、agent 编排 |
| 🟠 硬（1-3 月专注期）| ~10% | cross-document agent、LoRA fine-tune、复杂多步推理 |
| 🔴 前沿（可选）| ~5% | 持续学习不遗忘、多 agent 协作 |

**90% 的价值落在 🟢🟡 两格。** 做完这两档就是一个真正好用的 Second Brain。

---

## 关键技术风险（提前说清）

| 风险 | 应对 |
|---|---|
| PowerShell 生态不够 | Phase 2 开始引入 Python（FastAPI + uvicorn）。PS 留给 Windows 集成 |
| Windows 编码坑 | `.gitattributes -text` + UTF-8 BOM 方案（今晚已踩过） |
| LLM 漂移（模型升级导致 prompt 失效） | Evals + CI 是唯一解。Phase 1 就要建 golden set |
| 维护疲劳（系统烂尾） | 每个 Phase 自成闭环；锁定每周固定时段 |
| 本地算力上限 | 14b 够用；fine-tune 租 RunPod A100 ~$8/次 |

---

## Phase Roadmap (按 ROI 排序)

### Phase 0 · 地基 · ✅ 已完成 (2026-04-19)

- ✅ Hub 骨架 + GitHub push
- ✅ 迁 brain-tools 内容 → hub 多层结构
- ✅ 抽 D:/brain 规则类文件 → rules/
- ✅ `config/task-router.yaml` + `rules/cloud-local-delegation.md`（纸面设计）
- ✅ `telemetry/schema.md` + `analyze.ps1`（skeleton）
- ✅ 本地 PDF 分类 pipeline（qwen2.5:14b, pilot 10/10 通过）
- ✅ L1 watchdog（auto-restart + silent MessageBox）

### Phase 1 · 闭合反馈环 (MVP Self-Improving)

**周期**: 2-3 个周末 | **优先级**: 🔥🔥🔥 最高

**目标**: 系统开始真正"学习"。可以画出 "每周低置信率" 下降曲线。

子任务见 `architecture/phase-1-plan.md`（7 个任务, ~16 小时）。

**退出标志**:
- worker 每次调 Ollama 有 JSONL 日志条目
- 低置信样本有结构化 escalation 可供云端/人工接手
- 改 prompt 后能立刻跑 golden set 看数字
- `task-router.yaml` 的参数真的被脚本读取（不再是纸面）

---

### Phase 2 · 语义检索层

**周期**: 1-2 个周末 | **优先级**: 🔥🔥🔥 最高

**目标**: "那个荷兰公证员叫什么？" 500ms 本地秒答。

| 任务 | 工具 | 时间 |
|---|---|---|
| 2.1 选向量库 | **LanceDB**（文件式，零运维，Python 原生）| 1h |
| 2.2 Python 服务骨架 | FastAPI + uvicorn，`/query` 端点 | 2h |
| 2.3 批量 embed 现有 brain/*.md | `nomic-embed-text`（已装）| 2h |
| 2.4 增量 embed（inbox-ingest 挂钩）| 新 md/json 入库触发 | 3h |
| 2.5 CLI `brain-ask "query"` | 本地 LanceDB → top-5 → 本地 LLM 组装 | 4h |
| 2.6 Caps+D 集成 | AHK 换成调 brain-ask | 1h |

**退出标志**: 零云端调用回答个人知识问题。

---

### Phase 3 · 多模态接入

**周期**: 2-3 个周末 | **优先级**: 🔥🔥 高（按你实际需求）

| 任务 | 工具 | 时间 |
|---|---|---|
| 3.1 图片分类 pipeline | `llava:13b` 或 `qwen2-vl:7b`，复用 task-router 架构 | 4h |
| 3.2 场景聚类（可选）| ChromaDB | 1-2 天 |
| 3.3 录音转文本 | **faster-whisper**（GPU 加速）| 4h |
| 3.4 扫描 PDF OCR fallback | Tesseract → PaddleOCR（阶梯式）| 3h |
| 3.5 新任务注册到 task-router.yaml | 证明架构通用性 | 1h |

**退出标志**: 扔一张照片进 inbox → 自动分类归档 + 可被检索到。

---

### Phase 4 · Agent 层（能发任务、多步执行）

**周期**: 1 个月 | **优先级**: 🔥🔥 高（这是质变）

| 任务 | 工具 | 时间 |
|---|---|---|
| 4.1 选 agent 框架 | **LangGraph**（成熟，有 checkpoint）或 PydanticAI（轻）| 1 天选型 |
| 4.2 定义工具集 | `search_brain`, `read_file`, `write_md`, `escalate_cloud`, `run_query` | 3 天 |
| 4.3 首个端到端任务: **2024 税务草稿** | 检索 → 抽取 → 聚合 → 本地 draft → 云端审 → 输出 | 1 周 |
| 4.4 流式输出 + 中途可打断 | LangGraph 内置 checkpointing | 2 天 |
| 4.5 `brain-query` CLI | 命令行触发任意任务 | 3 天 |

**退出标志**: "准备 2024 税务材料" 一个命令，20 分钟出初稿。

---

### Phase 5 · 主动提醒（Proactive）

**周期**: 1-2 个周末 | **优先级**: 🔥 中

| 任务 | 工具 | 时间 |
|---|---|---|
| 5.1 Windows Task Scheduler 挂定时任务 | schtasks + PS | 1h |
| 5.2 周报生成器 | 读 telemetry + brain 变化 + 本地 LLM | 1 天 |
| 5.3 异常检测（dedup / orphan / BSN 漏标）| 规则脚本 | 1 天 |
| 5.4 Daily inbox digest | 每天 7:00 汇总 | 半天 |

**退出标志**: 周一早上有一份本周自动摘要 markdown。

---

### Phase 6 · Evals 成熟度 + CI

**周期**: ongoing，贯穿 Phase 1-5 | **优先级**: 🔥🔥 高

**这不是独立 Phase，而是贯穿始终的纪律。**

| 任务 | 说明 |
|---|---|
| 6.1 Golden set 扩到 100+（每个 task 20+）| 被动积累，每次修正就入库 |
| 6.2 Pre-commit hook | 改 prompt → 自动跑 evals → 回归就 block |
| 6.3 A/B 提示变体 | 平行跑两个 prompt，对比分数 |

---

### Phase 7 · 个人化 Fine-Tune（专属模型）

**周期**: 3-6 个月被动数据积累 + 2 周末主动训练 | **优先级**: 🔥 低但杠杆极高

| 任务 | 工具 |
|---|---|
| 7.1 积累 ~1000 对 (文本, 你的修正) | 来自 feedback loop，被动发生 |
| 7.2 数据清洗 + instruction-tuning 格式 | Python 脚本，1 天 |
| 7.3 LoRA fine-tune qwen2.5:14b | **unsloth** 或 **axolotl**；租 RunPod A100 ~$8 |
| 7.4 评估 LoRA vs 原版（你的 golden set）| 必须赢才上线 |
| 7.5 Ollama 加载 LoRA | Ollama 原生支持 adapters |

**退出标志**: 本地专属模型在你的 domain 上 ≥ GPT-4o / Claude Opus。**个人 AI 的终极形态**。

---

### Phase 8 · 跨设备（可选）

**周期**: 1 个月 | **优先级**: 看需求

| 任务 | 工具 |
|---|---|
| 8.1 API gateway | FastAPI + JWT auth |
| 8.2 Tier-based 隐私控制 | 敏感数据白名单 IP/设备 |
| 8.3 移动前端 | React Native 或 PWA |

---

## 时间总账

| 维度 | 估计 |
|---|---|
| 纯编码时间 | ~200-300 小时 |
| 实际日历时间（4-6h/周末）| **12-18 个月到完全形态** |
| 最小可用（Phase 1+2）| **4-6 周** |
| 钱 | 硬件已有；云 API ~$5-20/月；fine-tune 一次 ~$10-30 |

---

## 技术栈决策（避免弯路）

| 选择 | 推荐 | 理由 |
|---|---|---|
| agent 框架 | **LangGraph** | 成熟，有状态管理，Ollama 原生 |
| 向量库 | **LanceDB** | 零运维，文件式，Python 原生 |
| API 服务 | **FastAPI** | Pythonic, 异步, 易部署 |
| embed 模型 | nomic-embed-text (已有) | 够用，本地免费 |
| OCR | Tesseract → PaddleOCR | 阶梯式 |
| 语音转文本 | **faster-whisper** | 最快最好的本地 Whisper |
| 视觉模型 | llava:13b 或 qwen2-vl:7b | 本地多模态 |
| fine-tune | **unsloth** | 最省显存的 LoRA 库 |
| 调度 | **Windows Task Scheduler** | 不为此装 cron 替代品 |
| 配置 | YAML + JSON Schema 验证 | 已在此路 |
| 监控 | 先 JSONL + PS 分析 → 后 Grafana + Loki | 不要一开始上重工具 |

---

## 三条严肃的长期原则

1. **不要跳过 Phase 1**。向量检索更好玩，但没有 feedback loop 的系统会在 3 个月后因为 prompt 改烂而废掉。
2. **Python 不可避免**，早点接受。在 hub 里开 `tools/py/` 子目录逐步迁。
3. **公开记录进展**。这个项目的核心资产是"在你的数据上训练出的个人化"——不可复制、不可外包。但工程经验可以分享。

---

## 不做什么（同样重要）

- ❌ **不做 SaaS 对外售卖**。这是个人工具，不搞商业化会避免大量糟心事（支持、合规、SLA）。
- ❌ **不追求"通用 AI 助手"**。专注在你自己的数据上，这是你的护城河。
- ❌ **不重写已有的优秀工具**（Obsidian / Cursor / Ollama / Whisper）。只做粘合层。
- ❌ **不在完成 Phase 1 之前做 Phase 3-4**。诱惑巨大，但会让系统成为玩具而非工具。

---

## 参考资料（长期跟踪）

- **Anthropic "Building Effective Agents"**（2024 末）—— Agentic workflow 设计原则权威
- **Langfuse Blog / Discord** —— LLMOps 最清醒的声音
- **r/LocalLLaMA** + **Ollama Discord** —— 自托管最新实践
- **LangChain "Awesome LangGraph"** —— agent 编排参考实现

---

## 更新日志

| 日期 | 改动 |
|---|---|
| 2026-04-19 | 初版。Phase 0 完成, Phase 1-8 规划 |
