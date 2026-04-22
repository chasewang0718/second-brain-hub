---
title: second-brain-hub 优化路线图
status: active
created: 2026-04-20
updated: 2026-04-22
authoritative_at: C:\dev-projects\second-brain-hub\architecture\ROADMAP.md
---

> **📌 2026-04-22 状态快照** · 每个 Phase 内的 `[ ]` 勾选从 v5 起**再没同步**，但代码早已交付。
> 真实完成度以这张表为准（每行给出"最强证据"，不以 `[ ]` 为准）：
>
> | Phase | 现状 | 证据 |
> |---|---|---|
> | F0 目录改名 | ✅ 已交付 | `config/paths.yaml` 用 `D:\second-brain-content` / `D:\second-brain-assets`；生产 DuckDB 在新路径跑通 |
> | F1 Python + MCP 骨架 | ✅ 已交付 | `tools/py/` uv 工程；`brain_mcp/server.py` 挂 15+ 工具；`brain_cli/main.py` Typer CLI |
> | F2 Git 安全网 | ✅ 已交付 | `brain_core/safety.py`: `AutoCommitter` / `BackupBrancher` / `restore_*` / `safety_status` |
> | F3 记忆层 | ✅ 已交付 | `brain_memory/{vectors,graph,structured}.py` 三 DB 门面；Kuzu POC 29 ms FoF；LanceDB 向量；DuckDB 表齐全 |
> | A1 ask-engine | ✅ 已交付 | `brain_agents/ask.py` + `brain ask` CLI + `ask_*` MCP 工具 |
> | A2 text-inbox | ✅ 已交付 | `brain_agents/text_inbox.py` + `brain text-inbox-ingest` + 实体抽取→`person_notes` |
> | A3 file-inbox（含 PS 弃用） | ✅ 已交付 | `{file,image,audio}_inbox.py`；PS pipeline 2026-04-21 整体删除（见 12 条变更日志） |
> | A4 write-assist | ✅ 已交付 | `brain_agents/write_assist.py` + provenance 脚注 + `brain write` |
> | A5 people-engine | 🟡 代码齐 / 真数据已跑 / 评估进入“静态+金标+动态” | `people.py` + `who/overdue/context_for_meeting` CLI + MCP；B-ING-3 + B-ING-5 后已有 WhatsApp 1451 交互 + WeChat 6192 人/50 交互；A5 eval 当前 12 静态 + 12 固定金标 + 11 动态真实样本，共 35 case，35/35 通过 |
> | A6 动态人物档案 | 🟡 规划中（2026-04-22） | bi-temporal `person_facts` + 派生 `person_metrics` + `open_threads` 到期化 + rolling topics；业内对标 Zep/Graphiti + Mem0 + Letta；4 sprint / 1.5–2 周末，详见 Phase A6 |
> | E1 结构自优化 | ✅ 已交付 | `brain_agents/structure.py` + `tools/housekeeping/brain-weekly-maintenance.ps1`（每周日 23:00） |
> | E2 主动化 | ✅ 调度全开 | `brain_agents/digest.py` + `daily-digest/weekly-review/relationship-alerts/budget-tracker`；`BrainDailyDigest` + `BrainWeeklyReview` + `BrainRelationshipAlerts` + `BrainBudgetTracker` 均已注册并 RunNow 冒烟通过 |
>
> **🟡 真数据缺口 · 最需要补的一块**
>
> B-ING-1 iOS AddressBook 已真跑（213 人 / 453 identifiers / 2026-04-22 全部 follow-up 关档），B-ING-3/B-ING-4 WhatsApp（1451 interactions / 57 人）与 B-ING-5 WeChat（6192 人 / 50 interactions）也已真跑。但 A5 的"人际闭环"还差：
>
> - **B-ING-3/B-ING-4 WhatsApp 真跑**：✅ 已完成。
> - **B-ING-5 WeChat 真跑**：✅ 已完成（当前只 ingest 1 份 chat JSON，后续需扩大会话覆盖）。
> - **B-ING-5.1 Caps+D 文本 → person_notes**：✅ 冒烟已通过（`[people-note: Hammond]` 成功写入 `person_notes` 并 linked_person 命中）。
> - **B-ING-6 图→T3 扫描**：✅ 已完成最后复核。在单 writer 会话清理残留图进程后，`sync-from-graph --dry-run` 与 `--apply` 均 `status=ok` 且 `proposed=0`（0-candidate no-op）。
> - **A5 评估**：✅ 已补首轮基线（`tools/py/tests/eval_people.py` + `tools/py/tests/people_eval.yaml`，当前 3/3 通过）；下一步是扩展真实样本覆盖与长期趋势追踪。
>
> **方向校正**：F0–A4 的工程底盘已经**过剩**（pytest 234、MCP 工具 15+、Kuzu + LanceDB + DuckDB 三 DB 全接通），短板在于 #1 文本 inbox / #3 写作助手 / #4 索引助手的**真用户使用证据**——代码齐，但没评估、没被日常用。下一阶段应优先：
>
> 1. 扩容 A5 专项评估样本（真实联系人、同名异人、别名）并接入趋势追踪 → 把 A5 从“可跑”推进到“可运营”。
> 2. 补齐 E2 的 weekly-review / relationship-alerts / budget-tracker 定时任务（daily-digest 已上线）。
>
> 下方每个 Phase 内的 `[ ]` 勾选**请忽略**；以本表 + 各 runbook 为准。待 B-ING-6 + A5 eval + E2 全调度交付后，统一把 ROADMAP 升级到 v6。

## v6 退出标准（A5 / E2）

以下标准用于判断是否从当前“持续优化中”升级为“v6 稳定运营态”：

### A5 people-engine（必须同时满足）

1. 连续 7 天每日评估全绿：`tools/py/tests/eval_people.py` 返回 `failed=0`。
2. 评估趋势落盘连续 7 天：`08-indexes/digests/people-eval-history.jsonl` 每天新增 1 条快照，`people-eval-trend.md` 可正常刷新。
3. 关系变化摘要连续 7 天生成：`08-indexes/digests/relationship-deltas-YYYY-MM-DD.md` 每天有新文件。
4. WeChat 受控扩量至少 2 批完成且每批通过幂等复检：post-check 中 `wechat-sync --dry-run` 为 `would_insert=0`。

### E2 主动化（必须同时满足）

1. 三个日常任务需在任务计划中可见并为可运行状态：`BrainDailyDigest` / `BrainRelationshipAlerts` / `BrainBudgetTracker`；`BrainWeeklyReview` 改为按需开启（默认可保持禁用，不阻塞 v6 达标）。
2. 连续 7 天运行无失败日志（含 `-RunNow` 冒烟与定时触发窗口）。
3. 四类产物文件按频率持续生成（daily / weekly / relationship / budget）。

### 判定与回退

- **达标**：满足上述 A5 + E2 全部条件，ROADMAP 升级到 v6，并将 A5/E2 标记为“稳定运营态”。
- **未达标**：继续执行“受控扩量 + 每日复检”循环，不升级版本；优先处理锁争用、会话噪音、任务失败三类问题。

# second-brain-hub 优化路线图 (v5 · 零预算全自主)

> **一句话心智**: AI 全自主管控, git 做安全网, Python 单一栈, 零云端预算, 借 Cursor 订阅额度兜底.
>
> **v5 核心公式**:
> - 范式: AI 自主执行 + git 可回滚 (不是 AI 提议 + 人审批)
> - 栈: Python + LangGraph + FastMCP, 嵌入式 DB 三件套 (LanceDB + Kuzu + DuckDB)
> - 预算: $0/月 (Cursor 订阅为已付沉没成本, 借道使用)
> - 目录: `D:\second-brain-content` (Tier A md) + `D:\second-brain-assets` (Tier B 二进制)
> - 老 PS 代码: Phase A3 上线时直接删除, 不渐进迁移

---

## 🎛️ 调度协议 (触发词约定)

| 触发词 | AI 动作 | 会动文件? |
|---|---|---|
| **"推进 hub"** / **"hub 下一步"** | 读本文件 → 找第一个未勾选项 → 直接提议具体改动, 等点头再动手 | 提议阶段不动; 点头后动 |
| **"hub 进度"** / **"查看 roadmap"** | 只读本文件 → 报告当前位置 + 各 Phase 勾选情况 | ❌ 只读 |
| **"hub 验收 Phase N"** | 对照 Phase N 的"退出标志" → 跑 eval / smoke → 出验收报告 | 可能跑脚本, 不改源码 |
| **"hub 痛点: \<描述\>"** | 追加到 `D:\second-brain-content\04-journal\YYYY-MM-DD.md`, 打 `hub-pain` 标签 | ✅ 只追加 journal |
| **"hub 改方向: \<理由\>"** | 进入路线图编辑模式, 讨论调整, 最后升级本文件到 vN+1 | ✅ 改本文件 |
| **"处理 cursor 队列"** | 扫 `D:\second-brain-assets\_cursor_queue/` → Cursor AI 逐个处理 → 写 `.processed.md` | ✅ 处理队列 |

**默认行为** (用户只说"推进 hub"没指定 Phase):
- AI 自动选第一个未勾选项直接提议, 不反问
- 若整个当前 Phase 已全勾选 → 进入验收模式

**硬约束 (v5 保留)**:
- AI 不得自主跳过 Phase 顺序 (除非用户明说 "跳到 Phase X")
- AI 在落地任何 Phase 任务前**必须**: 建 backup 分支 → 执行 → auto-commit

---

## 0. v5 与历史版本的关系

### v5 相对 v4 的关键变化

| 维度 | v4 | v5 |
|---|---|---|
| 技术栈 | Python + LangGraph (主导) | **Python 唯一栈, 无 TS 分支** |
| 结构化 DB | 未定 | **DuckDB** (否决 Supabase / SQLite) |
| 云端预算 | $50/月 | **$0/月**, Cursor 订阅为 sunk cost |
| 云端兜底 | Claude Opus 自动 | **`_cursor_queue/` 人工触发 Cursor** |
| 老 PS 代码 | 渐进迁移 | **直接弃用** (A3 上线时删) |
| 面板 | E2.5 可选 | **永不做** |
| LoRA fine-tune | E3 按需 | **删除** (0 预算训不起) |
| 目录命名 | 待 Phase 1.5 | **本次一起改名到 `second-brain-*`** |

### v1-v4 被废弃的假设

- ❌ "AI 不得自主改 L3 知识结构" → v5 **AI 必须**自主改, git 兜底
- ❌ "AI 守 supreme law 原则" → v5 原则降级为**偏好参考**
- ❌ "建议 > 执行" → v5 **执行** + auto-commit
- ❌ "PowerShell 为主" → v5 **Python 唯一**
- ❌ "混合本地+云端 LLM" → v5 **100% 本地**, 失败入 Cursor 队列

### v5 保留的硬红线（非协商）

这三条**不是哲学原则, 是法律/工程风险**:

1. **Tier C 隐私黑名单** (BSN / 医疗 / 银行密码): 永不触碰 (GDPR 合规)
2. **破坏性 git** (`push --force` / `reset --hard` / 删 `.git/`): 需显式确认
3. **Git 作为安全网**: 每次 agent 写入**必经** auto-commit + backup branch

违反以上任一条不是"违反原则", 是"破坏系统基本盘".

---

## 1. 终端用户目标 (五大场景)

| # | 场景 | 交互 | 业内对标 |
|---|---|---|---|
| 1 | Caps+D 万物文本 → 自动打标签/切碎/整理/链接/归档 | AHK → MCP → agent | Mem.ai / Reflect |
| 2 | 文件 (PDF/图/音/视频) 丢 inbox → 自动分析/重命名/归档 | FSWatcher → MCP → agent | 现 PDF pipeline 泛化 |
| 3 | 写作助手 (四层知识模型 + self-critique + provenance) | CLI / MCP | Jasper + Notion AI |
| 4 | 索引助手 (秒找想要内容) | CLI / MCP / Cursor | Perplexity Spaces 本地版 |
| 5 | 人际关系助手 (对话抽人/事/承诺) | Caps+D → MCP → agent | **Monica + Dex + DenchClaw** |

**一句话**: 全自主 + 可回滚 + 本地优先的外脑 API, 被任何 MCP 客户端调用.

---

## 2. v5 架构蓝图

```
┌──────────────────────────────────────────────────────────┐
│ 接入层                                                    │
│ AHK (Caps+D) / CLI (brain) / Cursor / FSWatcher           │
└────────────────┬─────────────────────────────────────────┘
                 ↓ (MCP protocol)
┌──────────────────────────────────────────────────────────┐
│ MCP Server (brain-mcp, FastMCP Python)                   │
│ tools: ask / write / inbox.text / inbox.file / who /     │
│        overdue / meeting / process_cursor_queue          │
└────────────────┬─────────────────────────────────────────┘
                 ↓
┌──────────────────────────────────────────────────────────┐
│ Agent 编排 (LangGraph)                                    │
│ text-inbox / file-inbox / write / ask / people / struct  │
└────────────────┬─────────────────────────────────────────┘
                 ↓
┌──────────────────────────────────────────────────────────┐
│ 记忆层 (全嵌入式, 零运维, 零预算)                          │
│ LanceDB (向量) · Kuzu (图) · DuckDB (结构化) · FS (md/bin)│
└────────────────┬─────────────────────────────────────────┘
                 ↓
┌──────────────────────────────────────────────────────────┐
│ 模型层 (100% 本地, 0 增量预算)                             │
│ Ollama: qwen2.5:14b / qwen2.5:3b / llava:13b /           │
│         nomic-embed-text / faster-whisper / paddleocr    │
│ "云端": Cursor 订阅额度 (人工触发 `_cursor_queue/`)       │
└──────────────────────────────────────────────────────────┘

Cross-cutting:
 • Git 安全网 (GitPython + auto-commit)
 • _cursor_queue/ (cursor-delegated escalation)
 • Telemetry (DuckDB 表, SQL 可查)
```

### 物理目录 (v5 起)

```
C:\dev-projects\second-brain-hub\   (Git, 代码/配置/工具)
D:\second-brain-content\            (Git, Tier A markdown)
D:\second-brain-assets\             (非 Git, Tier B 二进制)
  └─ _cursor_queue/                 (escalation 队列)
  └─ _escalation/                   (向后兼容, 逐步废弃)
```

### 技术栈最终清单

| 角色 | 工具 |
|---|---|
| 语言 | Python 3.12 |
| 包管理 | `uv` (2026 事实标准) |
| Agent 编排 | LangGraph |
| MCP server | FastMCP |
| LLM 客户端 | `ollama-python` |
| 向量 DB | LanceDB |
| 图 DB | Kuzu |
| 结构化 DB | **DuckDB** |
| ORM | SQLAlchemy + DuckDB dialect |
| Schema 校验 | pydantic v2 |
| Whisper | faster-whisper |
| OCR | paddleocr |
| PII 检测 | presidio-analyzer |
| Git | GitPython |
| FS Watch | watchdog |
| Eval | pytest + promptfoo |
| CLI | typer |
| 日志 | loguru |
| Windows 入口 | AHK (仅保留项) |

---

## 3. 路线图 (v5 Phase 结构)

### Phase F0 · 目录改名 ✅ (30 分钟, 手工 + 一次性)

由用户在干净 PS 里执行物理改名, AI 更新所有仓内引用.

- [ ] 关闭所有使用 `D:\brain` / `D:\brain-assets` 的进程
- [ ] 执行: `Rename-Item D:\brain second-brain-content`
- [ ] 执行: `Rename-Item D:\brain-assets second-brain-assets`
- [x] 仓内 `config/paths.yaml` 改路径 (AI 已改)
- [x] 仓内 `rules/AGENTS.md` / `privacy.md` / `inbox-ingest.md` 改路径 (AI 已改)
- [x] 仓内 `brain-tools-index.md` 改路径 (AI 已改)
- [ ] 内容仓自身 `.git` hook 检查 (若有引用旧名)
- [ ] PS profile 里 `brain-*` 函数引用检查
- [ ] AHK 脚本 (`tools/ahk/`) 引用检查

**退出标志**: `cd D:\second-brain-content` + `git status` 正常; 仓内 `rg 'D:\\brain\\' -g '!**/ROADMAP.md'` 零命中.

---

### Phase F1 · Python + MCP Server 骨架 ✅ (2-3 周末)

搭 Python 主工程 + MCP server, Cursor/Claude Desktop 可调.

- [ ] `tools/py/` 用 `uv init` 初始化 (pyproject.toml + uv.lock)
- [ ] 包结构:
  - `brain_core/` (config, logging, paths)
  - `brain_mcp/` (FastMCP server)
  - `brain_agents/` (LangGraph agents, 后续 Phase 填充)
  - `brain_memory/` (三 DB 门面, 后续 Phase 填充)
  - `brain_cli/` (typer CLI)
- [ ] `brain_core/config.py` 读 `config/paths.yaml` + `thresholds.yaml`
- [ ] `brain_core/telemetry.py` 写 DuckDB 表 (不再 jsonl)
- [ ] `brain_mcp/server.py` FastMCP + 3 个 stub tool (`health`, `echo`, `paths`)
- [ ] PS profile 的 `brain` 命令改调 Python CLI
- [ ] Cursor `.cursor/mcp.json` 配置 brain-mcp-server

**退出标志**: Cursor 里输入 "use brain mcp to get paths" → 返回 `paths.yaml` 内容.

---

### Phase F2 · Git 安全网 ✅ (1-2 周末)

所有 agent 写入 auto-commit + backup + restore.

- [ ] `brain_core/safety.py`:
  - `AutoCommitter` context manager (每个 write 一个 commit)
  - `BackupBrancher` (agent session 建 `agent/<name>/<ts>` 分支)
  - `RestorePoint` (定时 tag)
- [ ] `brain restore` CLI:
  - `brain restore --to <commit>`
  - `brain restore --last-clean`
  - `brain restore --agent <name>`
- [ ] `brain history` 看 agent 改动时间轴
- [ ] 内容仓 `.git/hooks/pre-agent-write` 脚本

**退出标志**:
- Agent 随机改 10 个文件后, `brain restore --last-clean` < 10 秒复原
- commit message 带 `[agent:name]` 前缀, git log 可识别

---

### Phase F3 · 记忆层 ✅ (2-3 周末)

三 DB 就位 + 全量 embed.

- [ ] LanceDB 向量 (`brain_memory/vectors.py`)
  - `nomic-embed-text` 本地嵌入
  - 嵌入 `D:\second-brain-content\**\*.md` 全部
  - watch-and-embed 增量 (用 watchdog)
- [ ] Kuzu 图 (`brain_memory/graph.py`)
  - Schema: `Person / Org / Topic / Event` + `MENTIONS / WORKS_AT / RELATED_TO`
- [ ] DuckDB 结构化 (`brain_memory/structured.py`)
  - 表: contacts / invoices / interactions / telemetry / escalations
  - EAV 模式 (参考 DenchClaw)
- [ ] 统一门面 `brain_memory.Memory`
- [ ] 初始化脚本: 全量索引 content 仓一次

**退出标志**: 本地问 "那个荷兰公证员" < 1 秒命中.

---

### Phase A1 · ask-engine ✅ (1-2 周末, 最先做)

暴露统一检索 API.

- [ ] `brain_agents/ask/` LangGraph
  - 向量 (LanceDB) + 图 (Kuzu) + 全文 (ripgrep) 三路融合
  - 本地 14B 组装答案 + 引用
- [ ] MCP tool: `brain.ask(query, mode="fast"|"deep")`
- [ ] CLI: `brain ask "..."`
- [ ] AHK 长按 Caps+D 快捷问答

**退出标志**:
- Cursor `@brain what did I write about 故事原型` 有答案 + 引用
- `brain ask` < 2 秒

---

### Phase A2 · text-inbox agent ✅ (2-3 周末)

Caps+D 贴任何文本 → 零操作归档.

- [ ] `brain_agents/text_inbox/` LangGraph:
  - PII 检测 (presidio): BSN / 银行卡 / 医疗号 → 入 Tier C, 不嵌入向量
  - 主题分类 + 实体抽取 + 标签生成
  - 切碎长文本为多卡
  - 路由归档决策
  - 关联检测 + 双向链接
- [ ] 每步走 AutoCommitter, 每步一个 commit
- [ ] 低置信 (<0.7) → `99-inbox/_draft/` (你看)
- [ ] 无法决策 → `_cursor_queue/` (Cursor 处理)
- [ ] 每日操作日志 → `99-inbox/_log/YYYY-MM-DD.md`

**退出标志**:
- Caps+D 贴文本, 1 分钟后正确位置 + 标签 + 反链
- 一周错误率 < 10%

---

### Phase A3 · file-inbox agent ✅ (2-3 周末, 包含 PS 弃用)

多模态文件自动归档, **并删除老 PS pipeline**.

- [ ] `brain_agents/file_inbox/`:
  - PDF: Qwen 分类 + QA (复现 PS 版逻辑)
  - 图片: LLaVA 分类 + paddleocr
  - 音频: faster-whisper → 复用 text-inbox
  - 视频: 关键帧抽取 + LLaVA + 音轨
- [ ] 统一 dispatcher (替代 PS task-router 手工实现)
- [ ] 失败入 `_cursor_queue/`
- [x] **弃用 PS 脚本** (2026-04-21 完成):
  - [x] 删除 `tools/ollama-pipeline/*.ps1`（6 个 + `category-to-path.md`）
  - [x] 删除 `tools/lib/config-loader.ps1` / `telemetry.ps1` / `wait-for-batch.ps1`
  - [x] 删除 `tools/feedback/harvest-feedback.ps1`
  - [x] 删除 `tools/watchdog/pdf-production-watchdog.ps1`（依赖已删除的 pipeline）
  - [x] 保留 `tools/ahk/` + `tools/watchdog/notify.ps1`（通用通知库, 供未来 watchdog 复用）

**退出标志**:
- 10 种格式文件丢 inbox 全部正确归档
- `tools/ollama-pipeline/` 目录为空或删除
- git log 里最后一条 PS 相关提交有"deprecated"标记

---

### Phase A4 · write-assist ✅ (3-5 周末)

四层知识模型 + 7 行业技巧.

- [ ] 四层骨架:
  - L1 事实层: `D:\second-brain-content\99-inbox + 01-concepts + 03-projects`
  - L2 方法论: `01-concepts\writing\{principles,frameworks,techniques,taboos}/`
  - L3 风格: `00-memory\my-writing-voice.md`
  - L4 约束: `config/writing-constraints.yaml` + `writing-cliche.yaml`
- [ ] `brain_agents/write/` LangGraph:
  - 组合 L1-L4 → system prompt
  - 本地 14B 初稿 → self-critique (2 轮)
  - Reverse outline 检查
  - Cliché 扫描 + Reader persona 注入
  - Provenance: 每段标来源卡
- [ ] Voice fingerprint: 从历史原创抽 → 写 `my-writing-voice.md`
- [ ] `brain write --topic X --platform Y --reader Z`
- [ ] 对 Cursor 开放: `process_cursor_queue` 里含 "润色请求" 类任务用 Cursor 订阅兜底

**退出标志**:
- `brain write --topic "第二大脑"` 产出带溯源脚注的小红书初稿
- 通用 AI detector 判定 AI 率 < 30%

---

### Phase A5 · people-engine 🟡 (3-5 周末, 依赖 F3 Kuzu) · 代码齐，WhatsApp 已真跑；待 WeChat/Caps+D 与评估

Monica/Dex 式人际关系助手.

- [ ] `brain_agents/people/`:
  - 实体抽取: 从 text-inbox + file-inbox 所有内容抽人
  - 别名解析: 向量相似度 + LLM 裁决
  - Timeline: 每人 `D:\second-brain-content\06-relationships\people\<slug>.md`
  - Health score: 距上次联系天数 / 期望频次 / 未兑现承诺
  - 承诺追踪: "下周喝咖啡" / "把 X 发给你" 抽为 action
- [ ] MCP tools:
  - `brain.who(name)` 人员 summary
  - `brain.overdue()` 超期未联系
  - `brain.context_for_meeting(person)` 会前 brief
  - `brain.mentioned_by(person)` 此人被哪些笔记提到
- [ ] Daily digest 集成

**退出标志**:
- 贴 5 条对话, 人物自动入库 + timeline 更新
- 明天日程 "见 X" → 早上桌面有 `meeting-brief-X.md`

---

### Phase A6 · 动态人物档案（Bi-temporal Person Profile）🟡 (1.5–2 周末, 4 sprint, 依赖 A5 + F3)

把 `06-people` 从"堆积的聊天摘要"升级为"随时间演化的人物档案"：事实有 valid_from/valid_to 可回溯 + 指标每日重算 + 承诺可到期 + 主题滚动摘要。

**业内对标**（2026-04 调研）：
- Zep / Graphiti —— bi-temporal KG + 自动事实失效（`valid_time` × `transaction_time`）
- Mem0 —— `pin / override / erase` 三态事实操作
- Letta (MemGPT) —— core memory / archival / recall 三段式
- Neo4j Agent Memory —— entity resolution（确定性 + 概率 + 人审）三档阈值

**对齐原则**（相对现有 A5）：
- **不重构**已有 `persons` / `person_identifiers` / `interactions` / `person_notes` / `person_insights` / `open_threads` / `merge_candidates`；A6 只**新增表**。
- **不删 interactions**：它是 Episodic 真相源，永远可从它重算 metrics 和回填 facts。
- **事实分三层**：pinned / derived / narrative（见 Sprint 1）。

#### Sprint 1 · `person_facts`（bi-temporal）+ `person_metrics`（派生）· P0

- [ ] DuckDB schema 升级到 v3：
  - `person_facts(id, person_id, key, value, value_json, valid_from, valid_to, confidence, source_kind, source_interaction_id, created_at)` —— `valid_to IS NULL` 表示"当前事实"；写入同 `key` 新事实时自动把旧记录 `valid_to = now`
  - `person_metrics(person_id PK, first_seen_utc, last_seen_utc, last_interaction_channel, interactions_all, interactions_30d, interactions_90d, distinct_channels_30d, dormancy_days, computed_at)` —— 覆盖式，派生自 `interactions`
- [ ] `brain_agents/person_facts.py`：`add_fact` / `invalidate_fact` / `list_facts(person_id, at?, include_history=False)` / `get_fact(person_id, key, at?)`
- [ ] `brain_agents/person_metrics.py`：`recompute_one(person_id)` / `recompute_all()`（全库重算一次约等于一次扫 `interactions`）
- [ ] CLI：`brain facts add|invalidate|list`、`brain person-metrics recompute [--person-id|--all]`
- [ ] `people_render` 在卡里增补两节：
  - `## Facts`（当前事实 + 可选 `--facts-history` 展开历史）
  - `## Metrics`（30d / 90d / all 计数、last_seen、dormancy、top channel）
- [ ] pytest：bi-temporal 覆盖（新写入自动关闭旧事实 / 时点查询 / invalidate / confidence）+ metrics 正确性
- [ ] 生产回填：一次性 `recompute_all`，对田果（`p_8168e6185835`）做回归验证

**退出标志**：田果卡里出现 `Metrics`（互动 424 / last=2026-04-20 / dormancy=…）与 `Facts`（允许空）两节；`brain facts add p_8168e6185835 residence "杭州"` 可查、可覆盖、可 invalidate；pytest 全绿。

#### Sprint 2 · `open_threads` 到期化 + 承诺抽取 · P1 ✅

- [x] `open_threads` schema 补齐：`due_utc` / `status (open/done/dropped)` / `promised_by (self/other)` / `last_mentioned_utc` / `source_interaction_id` / `source_kind` / `body_hash` / `created_at`（schema v4，向后兼容 ALTER TABLE）
- [x] `brain due [--within 7] [--person-id X] [--overdue-only]`、`brain thread add|close|reopen|update-due|list`
- [x] 候选承诺抽取（手动优先，LLM 次之）：
  - 手动：`brain thread add p_X "下周三寄书" --due 2026-04-30 --promised-by self`
  - LLM 自动：新增 `brain threads-scan --since-days 14`，用 Ollama fast model（qwen2.5:14b-instruct）从最近 interactions 里抽候选；默认 `--dry-run`，确认后 `--apply` 写 `source_kind='llm_extracted'`；幂等（body_hash 去重）
- [x] `people_render` 卡补 `## Open threads` 表格（status / due / who owes / body / last seen / source；⚠️ overdue / 🔥 today / ⏳ soon 芯片）
- [x] E2 `BrainDailyDigest` 接入 "Today's Commitments" + "Overdue Commitments" 两节

**退出标志**：✅ pytest +34 case (17 threads + 12 extract + 3 digest + 2 render)；✅ 生产烟测 snapshot `AC6D82DE..`, schema v4, 3 条 thread 写入, `brain due` 正确排序 (overdue-first), daily-2026-04-22.md 两节渲染, 田果卡 `## Open threads` 显示 ⏳ soon 芯片。详见 `architecture/a6-sprint2-acceptance.md`。

#### Sprint 3 · Rolling Topics + Weekly Digest · P1→P2 ✅

- [x] 每人 rolling topic 抽取：对 `interactions` 最近 30 / 90 天分桶，Ollama fast model 产出 top-K 主题词 + 一段小结，写入 `person_insights(insight_type='topics_30d'|'weekly_digest')`
- [x] `brain person-digest rebuild [--person-id|--all] [--since-days 30]`；幂等、带 `superseded_by` 链
- [x] `people_render` 卡补 `## Topics (30d)` + `## Weekly Digest`
- [x] E2 `BrainWeeklyReview` 串联：先 `person-metrics recompute --all` → 再 `person-digest rebuild --all --since-days 7`
- [x] pytest 覆盖：`superseded_by` 旧记录不出现在当前视图；空 interactions 人安全降级

**退出标志**：任一 tier=inner 的人卡里都有不超过 7 天旧的 Topics 段落；`BrainWeeklyReview` `-RunNow` 一次后 `person_insights` 有该人 ≥ 1 条 `weekly_digest`。

#### Sprint 4 · Relationship Tier + Cadence Alarm · P2 ✅

- [x] 在 `person_facts` 里用 `key='relationship_tier'`（value ∈ `inner / close / working / acquaintance / dormant`）；人工置顶优先，AI 只做建议
- [x] 每 tier 配 `cadence_target_days`（inner 14 / close 30 / working 60 / acquaintance 120 / dormant null）写 `config/thresholds.yaml` 的 `people_cadence:` 段
- [x] `brain tier set <person_id> <tier>`、`brain tier get`、`brain tier list`、`brain tier suggest [--all|--person-id] [--apply]`、`brain tier overdue [--tier X]`（建议走 `person_insights.insight_type='tier_suggestion'` 带 superseded_by 链；`--apply` 仅在无人工 fact 时才写入）
- [x] `people_render` 加 `relationship_tier` + `cadence_target_days` frontmatter 字段与 `## Relationship Tier` 节（within-cadence / overdue chip / AI 建议行）
- [x] `digest.generate_relationship_alerts` 扩展 `## Tiered Cadence Alarm` 节按 tier 分桶（inner→14/close→30/working→60/acquaintance→120），无 tier 的人回落到原 45d 平基线
- [x] E2 `BrainWeeklyReview` 追加 `brain tier suggest --all`（不 `--apply`，AI 永不覆盖人工设置）
- [x] pytest 覆盖 22 case + `test_digest` 新增 3 case：set/get 循环、拒无效 tier、bi-temporal 历史、启发式分桶、cadence 阈值读取/garbage 容忍、superseded_by 链、人工不被 AI 覆盖、overdue 按天倒序 + 过滤、tiered alert 段落渲染

**退出标志**：设 `relationship_tier=inner` 的人若 `dormancy_days > 14`，下一次 `brain relationship-alerts` 生成的 markdown 里 `## Tiered Cadence Alarm` 节的 `inner (cadence 14d)` 分桶列出该人；pytest 覆盖超期判定与阈值读取。

**Done log**: 2026-04-22 — 接在 Sprint 3 后直接推进 S4，零新增表、零破坏性迁移。权威 tier 复用 `person_facts`（key='relationship_tier'），免费拿到"2026-Q1 她当时什么 tier"的 bi-temporal 回查能力；AI 建议复用 `person_insights(insight_type='tier_suggestion')`，同样走 `superseded_by` 链保留完整历史。CLI 新增 5 条子命令（set/get/list/suggest/overdue），`people_render` 在 Metrics 节后加一节 Relationship Tier（内含 `current`/`cadence target`/`status` 三元组，`status` 出 ✅ within cadence 或 ⚠️ Nd overdue chip），并在 frontmatter 暴露 `relationship_tier` + `cadence_target_days` 以便 Obsidian 查询/过滤。Alert 层 `generate_relationship_alerts` 新增 `## Tiered Cadence Alarm` 表格节（按 inner→close→working→acquaintance 优先级渲染，人名/dormancy/超期天数/last_seen），原 flat 45d 段保留做基线。生产烟测：47.5 MB pre-apply snapshot → `brain tier suggest --all`（500 人启发式分布 inner=10 / close=22 / working=311 / acquaintance=150 / dormant=7 — 符合直觉，长尾偏 working）→ 田果（dormancy=2d）人工 set inner，卡渲染出"✅ within cadence (2/14d)" + AI 建议 `inner` (conf 0.70)；demo 把陈浩祈（dormancy=103d）set 为 close，`brain tier overdue` 精确列出 `+73d`，`brain relationship-alerts` 输出的 md 里 `## Tiered Cadence Alarm → close (cadence 30d) → 1 overdue` 的表格行完全正确。测试总规模 105/105 通过（S1+S2+S3+S4 合计）。唯一性能观察：`tier suggest --all` 500 人跑 7.5 min（每人一个独立 `transaction()` 往返），后续若扩到 10k 人需批量化；当前规模可接受。

#### 跨 Sprint 通用约束

- 任何新表走 `_ensure_v2_tables` 同款迁移模式 + `_record_migration` 递增版本
- 所有派生/抽取结果都必须能从 `interactions` + `person_facts` 重建，派生表**禁止**成为真相源
- 每个事实/承诺/主题记录**必须**带 `source_interaction_id` 或 `source_kind='manual'/'capsd'`，为未来审计与 Graphiti 式 provenance 打基础
- 每 Sprint 结束前跑一次 `brain ingest-backup-now --label a6-sprintN-pre-apply` 快照 DuckDB

**整体退出标志**（A6 从 🟡 升 ✅）：
- [x] 田果（或任一 tier=inner 人）卡同时可见：`Facts` / `Metrics` / `Open Threads` / `Topics (30d)` / `Weekly Digest` / `Relationship Tier` 六节（S4 新增 Relationship Tier 节）
- [x] Bi-temporal 回查能回答："2026-Q1 她在忙什么"（`list_facts(at='2026-03-31')` 返回该时点有效事实集）；`relationship_tier` 同样享此能力
- [x] A5 eval 不掉：`eval_people.py` 仍 ≥ 35/35
- [ ] 连续 7 天 `BrainWeeklyReview` + `BrainRelationshipAlerts` 无失败（生产观测项，周级评估）

> Phase A6 状态：**S1+S2+S3+S4 全部完成 ✅**（2026-04-22）。S5 起进入"运营 + 观测"阶段，关注 7 天连跑稳定性与 eval trend。

---

### Phase E1 · 结构自优化 ✅ (2-3 周末, 依赖 A1+A2+F2)

**自动执行**, git 兜底.

- [ ] 聚类检测 → 自动建 concept 目录 + commit
- [ ] 密度告警 → 自动拆分 + commit
- [ ] 孤岛检测 → 自动归档 `_archive/` + commit
- [ ] 关联发现 → 自动建双向链接 + commit
- [ ] 调度: 每日凌晨, 单次操作上限 20 次防暴走
- [ ] `brain history --structure` 看自优化历史

**退出标志**: 两周跑下来 20 次操作 revert 次数 ≤ 1.

---

### Phase E2 · 主动化 ✅ (2 周末) · 四类 digest 命令与调度均已上线

每日/每周自动推送.

- [ ] Daily digest (7:00): 昨天新增 + 今日 overdue + 日程 brief → 桌面 md
- [ ] Weekly review (周日): 本周新增/整合/自优化 + 预算 + eval 趋势
- [ ] Relationship alerts: 人际健康度告警
- [ ] Budget tracker: Cursor 额度 + 电费估算

**退出标志**: 周一早上桌面有周报; 工作日早上有 daily digest.

---

### Phase E4 · Cross-document 推理 agent (可选, 按需)

"准备 2026 自雇税务" / "过去 3 年我的关注点变化" 级任务.

- 触发: 实际跑过 3 次"跨 10+ 文件人工整理"后启动
- LangGraph multi-step + A1/A3/A5 工具组合
- 复杂任务自动入 `_cursor_queue/`

---

## 附录 · 人际 CRM 数据面 (hub 已落盘, 2026-04-21)

与 Phase A5 目标对齐的**结构化层**已在 DuckDB 打通（路径见 `config/paths.yaml` → `telemetry_logs_dir` → `brain-telemetry.duckdb`），用于多通道身份合并（微信 / Caps+D / iOS 通讯录 / WhatsApp 备份）与手动云队列兜底。

| 能力 | CLI / 入口 |
|---|---|
| 查询联系人 / 逾期 / 会前上下文 | `brain who`, `brain overdue`（可选 `--channel wechat` 等）, `brain context-for-meeting`（`--since-days`、`--format md`） |
| 同上（MCP） | `who_tool`, `overdue_tool`, `context_for_meeting_tool`, `merge_candidates_*`, `merge_candidates_sync_from_graph_tool`, `cloud_flush_preview`, `identifiers_repair_preview`, `cloud_queue_list_tool`, `ios_backup_locate_preview`, `wechat_sync_preview`, `graph_fof_tool`, `graph_shared_identifier_tool`（`brain_mcp/server.py`） |
| T3 合并候选（手动审） | `brain merge-candidates list`, `accept <id> [--keep PID]`, `reject <id>` |
| 微信 decoder 导入 | `brain wechat-sync [--dry-run]` |
| iPhone 备份定位 / 通讯录 / WhatsApp | `brain backup-ios-locate`, `brain contacts-ingest-ios`, `brain whatsapp-ingest-ios`（参见 `architecture/ios-backup-runbook.md`）；与本机备份 quick check：`tools/py/scripts/verify_ingest_dry_run.py` |
| 本地模型做不了的条目 | `brain cloud queue list` → `brain cloud flush`（写锁 + cursor-agent；日志在 Tier A 根 `.brain-cloud-flush-last.log`） |
| Caps+D 文本 inbox | `brain text-inbox-ingest`；归档后自动跑实体抽取 + `[people-note: 姓名]` → `person_notes` / `cloud_queue` |

**不做的事情**: 自动 Web 搜索补全联系人；WhatsApp Win11 商店版本地 DB 解密（推荐 iPhone 未加密备份路径）。

---

## 4. 时间估算

| 层 | Phase | 工时 |
|---|---|---|
| 改名 | F0 | 30 分钟 |
| 基础 | F1 + F2 + F3 | 5-8 周末 (6-10 周) |
| 功能 | A1 + A2 | 3-5 周末 |
| 功能 | A3 + A4 + A5 | 8-13 周末 |
| 进化 | E1 + E2 | 4-5 周末 |

**里程碑**:
- **3-4 个月**: F0-F3 + A1 + A2 → 最小可用 (能问能存)
- **5-7 个月**: + A3 A4 A5 → 五大场景齐活
- **7-10 个月**: + E1 E2 → 完整形态

---

## 5. Cut List (v5 最终)

| 砍掉项 | 理由 |
|---|---|
| LoRA fine-tune | 0 预算训不起, 数据不够 |
| FastAPI / HTTP 服务 | MCP 原生替代 |
| Web 面板 / 部署 | 永不做, 本地 CLI+MCP 够 |
| Supabase (云或本地) | DuckDB 嵌入式更合适 1-user 场景 |
| 跨设备 / 移动端 | MCP 远程即可, 有痛点再做 |
| 云端 LLM 自动兜底 | 0 预算. 改为 `_cursor_queue` 人工触发 |
| 每周结构体检报告 | E1 自动执行替代 |
| TypeScript 栈 | Python ML 生态碾压 |

**重新启用门槛**: 写一条痛点日志到 `04-journal/`, 累计 ≥ 3 条才重评.

---

## 6. 默认假设

| 决策 | 默认值 | 改法 |
|---|---|---|
| 安全网 | git auto-commit + backup + restore | 说 "关掉 git 兜底" |
| 技术栈 | Python 唯一 | 说 "加 TS" (不推荐) |
| 隐私 Tier C | 保留黑名单 (GDPR) | 说 "放开 Tier C" (我会警告) |
| 预算 | $0 + Cursor 订阅 sunk cost | 说 "允许 $X/月云端" |
| 顺序 | F0→F1→F2→F3→A1→A2→A3→A4→A5→E1→E2 | 说 "先做 A5" |
| 老 PS | A3 时整体删除 | 说 "保留不删" |
| 备份 | 内容仓 push GitHub 私仓 / 资产仓本地 + 第二块盘 rsync | 待 F3 末期拍板 |
| 面板 | 永不做 | 说 "做 Next.js 面板" |

---

## 7. 偏好 (前 "原则" / "选型三铁律" 降级)

**AI 决策时作为参考, 不作为硬约束**:

- 优先简单方案, 但业内最佳实践可 override
- 优先本地执行, 但 Cursor 订阅额度可用于队列
- 先痛点后方案, 但预防性建设若业内成熟也接受

**AI 行为**:
- 新建功能**默认按业内最佳实践**
- 违反上述偏好时**在 commit message 注明理由**, 不阻塞执行

---

## 8. 变更日志

| 日期 | 版本 | 改动 |
|---|---|---|
| 2026-04-22 | — | **06-people 人类可读出口**：新增 `brain people-render`（`brain_agents/people_render.py`）从 DuckDB 生成 `06-people/by-person/*.md` 与 `_index.md`；`wechat-ingest-preset.ps1 -RunPostChecks` 串联 `--all --since-days 45 --limit 2000`。旧 `wechat_to_people_bridge.py` 产物迁至 `06-people/_legacy-wechat-bridge/`。pytest 新增 `test_people_render.py`。 |
| 2026-04-22 | — | **Phase4 连续推进（批次 1 + 噪音复盘）**：使用 `wechat-ingest-preset.ps1 -Mode helper-no-person -ExtraWhitelist 20292966501@chatroom -Apply -RunPostChecks` 跑通完整证据链（preflight=0 / apply inserted=0 / post-check 全绿 / 关系变化摘要落盘）；随后对 `helper-link-person` 与 `helper-blacklist` 做 dry-run 复盘，二者均 `would_insert=0`，确认当前 decoder 导出下会话增量已耗尽，后续扩量需先刷新 decoder 产物。 |
| 2026-04-22 | — | **Phase5 v6 gate（首轮）**：新增 A5/E2 的 v6 退出标准（连续 7 天评估/产物/调度健康）。首轮判定：**未达升级窗口**（观测天数不足 7 天），继续执行“受控扩量 + 每日复检”循环。 |
| 2026-04-20 | v1 | 初版, 六 Phase 裁剪. 采纳 P1/2/3/5/6, 砍掉 agent 层 / fine-tune / 跨设备 |
| 2026-04-20 | v2 | 加 Phase 7 写作助手 (7a/7b, 四层知识 + 7 行业技巧) + Phase 1.5 命名统一 |
| 2026-04-20 | v3 | 加 Phase 2.5 任务派发器 (规则驱动, not-started) |
| 2026-04-20 | v4 | 重大转向: 放弃"AI 守原则"范式, 改为"AI 全自主 + git 兜底". Python + LangGraph + MCP 栈. 五大终端目标明确. LangGraph 从 Cut 到采纳 |
| 2026-04-20 | **v5** | **零预算 + 改名 + Python 唯一**. 云端兜底改为 `_cursor_queue/` 人工触发 Cursor 订阅处理. LoRA 砍掉 (0 预算). DuckDB 确定为结构化 DB (否决 Supabase). 目录改名 `D:\brain` → `D:\second-brain-content`, `D:\brain-assets` → `D:\second-brain-assets` (Phase F0 一次性). 老 PS 代码 A3 时整体删除. 原则降级为偏好. TypeScript 栈经评估拒绝. |
| 2026-04-21 | — | **附录**: 人际 CRM 多源栈（persons / identifiers / interactions / cloud_queue）与相关 `brain` 子命令写入路线图；runbook `architecture/ios-backup-runbook.md`。 |
| 2026-04-21 | — | **CRM / identity**: 中国大陆手机号归一化为 `86` + 合法号段（避免把 NANP `1…` 误判为 CN）；存量 `person_identifiers` 用 `brain identifiers-repair [--dry-run] [--kinds phone,email,wxid|all]` 重写（email 含 `gmail_addr`）并按冲突写入 `merge_candidates`（T3）。CLI 约定：子命令 stdout 仅输出可解析文本/JSON（Shell Profile 若在 Python 启动前打印横幅，与本仓库无关）。 |
| 2026-04-21 | — | **CRM CLI**: `overdue --channel`、`context-for-meeting --since-days/--format md`、`merge-candidates list|accept|reject`。 |
| 2026-04-21 | — | **Tests / runbook**: pytest 化（`tools/py/tests/`），`smoke_people`/`test_identity_phone_normalize`/`test_merge_candidates`/`test_people_cli` 共 22 用例；新增 `cloud flush` runbook `architecture/cloud-flush-runbook.md`。 |
| 2026-04-21 | — | **Caps+D PDF**: AHK `ClipWait(..., 1)` 捕获文件列表；`file_inbox.ingest_pdf_paths` + `~/.brain-exclude.txt` 黑名单；Stage3 E 验收表追加一行。 |
| 2026-04-21 | — | **MCP**: people / merge-candidates 工具与 CLI 对齐（channel、since_days、md、T3 accept/reject）。 |
| 2026-04-21 | — | **identifiers-repair**: `--kinds phone|email|wxid|all`；email+gmail_addr、wxid 存量大小写归一（T3 冲突语义与 phone 一致）。 |
| 2026-04-21 | — | **Cloud flush / D3**: MCP `cloud_flush_preview` + `identifiers_repair_preview`；pytest `test_cloud_flush.py`；`parse_identifiers_repair_kinds` 供 CLI/MCP 共用。 |
| 2026-04-21 | — | **Dry-run ingest**: `tools/py/scripts/verify_ingest_dry_run.py`（可选 `VERIFY_WECHAT_DECODER`）；MCP `cloud_queue_list_tool`、`ios_backup_locate_preview`、`wechat_sync_preview`。 |
| 2026-04-21 | — | **A3 图像分支**: `brain_agents/image_inbox.py` + `brain image-inbox-ingest [--path ...] [--no-copy]`；paddleocr 懒加载且可选（未安装时写 `ocr_status: pending` 指针卡 + `_cursor_queue/` 兜底任务）；`config/paths.yaml` 新增 `image_inbox_dir`；6 个 pytest 用例（全量 36 个）。 |
| 2026-04-21 | — | **A3 音频分支**: `brain_agents/audio_inbox.py` + `brain audio-inbox-ingest [--path ...] [--no-copy]`；faster-whisper 懒加载（`BRAIN_ASR_MODEL` / `BRAIN_ASR_LANG` 可调；未安装写 `asr_status: pending` 指针卡 + cursor_queue 兜底）；`config/paths.yaml` 新增 `audio_inbox_dir`；6 个 pytest 用例（全量 42 个）。 |
| 2026-04-21 | — | **Caps+D 统一分派**: 新增 `tools/ps/brain-caps-d-dispatch.ps1`（`Invoke-BrainCapsDSave` 按扩展名批量分派到 pdf/image/audio CLI，未识别/无文件降级到文本分支）；`.reference` profile 里 `gsave` 现以一行 dot-source + 一行 `if(...) return` 接入三件套；pytest `test_caps_d_dispatch_sync.py` 4 用例锁定 PS 表与 Python `SUPPORTED_EXT` 同步（全量 46 个）。 |
| 2026-04-21 | — | **A4 provenance**: `write_assist` 输出尾部自动追加 `## 参考` 块（按序引用 `sources`），并在 `provenance` 字段补 `kind`（pdf/image/audio/person-note/journal/note）+ 指针卡 `asset_sha256 / asset_type / person_id / ocr_status / asr_status`（来自目标文件 frontmatter）；新增 `include_provenance=False` 旁路；`test_write_provenance.py` 6 用例（全量 52 个）。 |
| 2026-04-21 | — | **F3 Kuzu 只读 POC**: `brain_agents/graph_build.py` + `brain_agents/graph_query.py`；CLI `brain graph-build/graph-stats/graph-fof/graph-shared-identifier`；Kuzu 作为 DuckDB 派生视图（全量重建 ~7s），POC 实测 FoF 29ms / shared-identifier 22ms / stats 26ms @ 75 人（< 1s 目标达标）；5 个 pytest 用例以 `importorskip("kuzu")` 保护；详见 `architecture/stage3-f3-kuzu-poc.md`（全量 57 个）。 |
| 2026-04-21 | — | **E1 周期维护**: 新增 `tools/housekeeping/brain-weekly-maintenance.ps1` + `register-brain-weekly-maintenance.ps1`（每周日 23:00，跑 `identifiers-repair --kinds all` / `cloud flush --dry-run` / `graph-build`，均只读或幂等；日志写 `_runtime/logs/brain-weekly-maintenance-YYYYMMDD.log`；runbook 见 `architecture/e1-weekly-maintenance-runbook.md`）。 |
| 2026-04-21 | — | **A3 收尾 · 弃用 PS 脚本**: 删除 12 个 (~105KB) 老 PS 脚本——整个 `tools/ollama-pipeline/`（6 + 配置 md）、`tools/lib/`（config-loader / telemetry / wait-for-batch）、`tools/feedback/harvest-feedback.ps1`、`tools/watchdog/pdf-production-watchdog.ps1`。全部已被 `brain_agents/file_inbox.py` + `image_inbox.py` + `audio_inbox.py` + `cloud_queue.py` 覆盖；保留 `notify.ps1`（通用通知库）。`tools/README.md` 更新子目录说明。 |
| 2026-04-21 | — | **F3 接入 `context_for_meeting`**: `people.context_for_meeting` 现在同时拉取 Kuzu `shared_identifier` 结果填入 `graph_hints`；Markdown 输出附加 "潜在同一人线索" 表格；缺 Kuzu / 图未构建 → `{"status":"skipped"}` 优雅降级（Markdown 不渲染该节）。MCP 新增 `graph_fof_tool` + `graph_shared_identifier_tool`（也走 skipped 约定）。新增 6 个 pytest 用例（test_context_graph_hints + MCP skip smoke），全量 **63 passed**。 |
| 2026-04-21 | — | **F3 → T3 队列自动补洞**: `merge_candidates.sync_from_graph` 从 Kuzu 枚举所有跨人 shared-identifier 对，去重 `merge_log` / 已有 `merge_candidates` 后，按 kind 打分（phone/wxid/email ≥ 0.92，其他 0.6）写入 pending；CLI `brain merge-candidates sync-from-graph --dry-run/--apply`；MCP `merge_candidates_sync_from_graph_tool`；E1 周任务第 4 步默认跑 `--dry-run`（日志报 `proposed = N`，写入仍需人工 `--apply`）。新增 6 个 pytest（含 merge_log/merge_candidates 去重 + 正反序规范化 + 未知 kind 默认分数），全量 **69 passed**。 |
| 2026-04-21 | — | **F3 `graph-rebuild-if-stale`**: 新增 `brain_agents/graph_build.graph_staleness` + `rebuild_if_stale`（对比 Kuzu vs DuckDB mtime；支持 `--max-age-hours` 墙钟阈值和 `--force`）；CLI `brain graph-rebuild-if-stale` + `brain graph-staleness`；E1 周任务改走这条便宜路径（fresh 时只 stat 文件；stale 才 ~7s 重建）；9 个新 pytest 覆盖 missing / no_duckdb / duckdb_newer / fresh / older_than_max / 不重建 fresh / 重建 stale / force / build 抛错时 skipped。全量 **78 passed**。 |
| 2026-04-21 | — | **`tools/asset/` 迁移评估文档**: 产出 `architecture/asset-migration-plan.md`——清点 5 个 PS 脚本（migrate / source-cleanup / dedup / stats / overview-cards）、当前 Python 覆盖率（~0-60%）、6 批推荐顺序（B1 stats+dedup → B2 删 overview-cards → B3 migrate → B4 source-cleanup → B5 profile → B6 删 dir），含 "绝对不做的事" 和并跑对拍 3 周的中间态约定。**不动代码**，仅评估。 |
| 2026-04-21 | — | **真实 ingest 上线范围文档**: 产出 `architecture/real-ingest-scope.md`——4 条线（iOS AddressBook / WhatsApp / WeChat / remark）代码就绪但全部未跑真数据，列出 4 个公共前置（PC-1 备份快照 / PC-2 T3 阈值演练 / PC-3 jsonl ingest 日志 / PC-4 事务包裹）、7 步上线路线（B-ING-0 ~ B-ING-6，~3 工日 / 跨 1 周）、绝对不做清单（不本地解密 / 不跨线混跑 / 不回溯 1 年前消息 / 用户不在不 apply）。**不动代码**，等用户说"开 B-ING-0"再起。 |
| 2026-04-22 | — | **E2 剩余调度补齐**: 新增 CLI `brain relationship-alerts --days` 与 `brain budget-tracker`；新增 `tools/housekeeping/brain-e2-task.ps1` + `register-brain-e2-tasks.ps1`，注册 `BrainWeeklyReview`（Sun 20:00）、`BrainRelationshipAlerts`（Daily 08:30）、`BrainBudgetTracker`（Mon 08:45），`-RunNow` 三任务均返回 OK。 |
| 2026-04-22 | — | **B-ING-5.1 · Caps+D→person_notes 冒烟通过**: 导入 `[people-note: Hammond]` 样本后，`text-inbox-ingest` 返回 `people_notes_written=1`、`linked_person=p_0ac7536db641`、`cloud_enqueued=false`，并在 `D:\second-brain-content\99-inbox\_draft\people-note-hammond.md` 落卡。DB 核对新增 `person_notes.source_kind='capsd-people-note'` 一行，`detail_json.tag_name=Hammond`。 |
| 2026-04-22 | — | **A5 专项评估扩展（第二轮）**: `people_eval.yaml` 从 3 case 扩展到 12 case，新增 who 前缀/不命中、overdue 渠道大小写容错、`context-for-meeting --format md`（命中/未命中）断言；`eval_people.py` 补 `context_md` 校验器。真实库复跑 `python tools/py/tests/eval_people.py` 为 `12/12 passed`，报告更新至 `architecture/a5-eval-baseline-2026-04-22.md`。 |
| 2026-04-22 | — | **A5 趋势化接入 E2 weekly-review**: 新增 `tools/py/scripts/eval_people_trend.py`，每次执行写入 `D:\second-brain-content\08-indexes\digests\people-eval-history.jsonl`；`brain-e2-task.ps1` 在 `weekly-review` 后自动追加一次 A5 eval 快照（失败会让任务失败），已本机冒烟通过。 |
| 2026-04-22 | — | **A5 趋势摘要 Markdown**: 新增 `tools/py/scripts/eval_people_trend_summary.py`，从 `people-eval-history.jsonl` 生成 `D:\second-brain-content\08-indexes\digests\people-eval-trend.md`；E2 `weekly-review` 已串联该步骤，周任务可直接消费可读趋势摘要。 |
| 2026-04-22 | — | **A5 真实样本增强（静态+动态）**: `eval_people.py` 新增动态样本生成器（每次自动抽取最近联系人 6 条、高互动联系人 3 条、同名冲突 2 条），与静态 `people_eval.yaml` 组合运行；当前实跑 `23/23 passed`（`dynamic_cases_added=11`）。 |
| 2026-04-22 | — | **A5 固定金标机制 v1**: `eval_people.py` 接入可选 `people_eval_golden.yaml`；新增 `tools/py/scripts/generate_people_golden_candidates.py` 用于从真实库筛出可读联系人候选；当前纳入 12 条固定金标并实跑 `35/35 passed`（`static=12, golden=12, dynamic=11`）。 |
| 2026-04-22 | — | **A5 graph 正例夹具（可选）**: `eval_people.py` 新增 `graph_shared_identifier` 断言类型与共享标识符夹具；通过 `EVAL_PEOPLE_INCLUDE_GRAPH_POSITIVE=1` 显式启用（默认关闭），用于在 Kuzu 锁稳定窗口内验证 graph_hints 正例，不影响日常稳定基线。 |
| 2026-04-22 | — | **B-ING-6 ✅ 收官（0-candidate no-op）**: 最后一轮在单 writer 会话先清理残留 `graph-rebuild-if-stale/graph-build` 进程后复跑；`merge-candidates sync-from-graph --dry-run` 返回 `status=ok, proposed=0`。随后按流程先 snapshot `20260422-101439-bing6-final-noop-apply.duckdb`（sha `201a7674...`）再执行 `--apply`，结果 `inserted=0, auto_applied=0`，确认当前图→T3 无新增候选。 |
| 2026-04-22 | — | **B-ING-5 · WeChat 真跑收官**: `brain wechat-sync --dry-run` 命中 `contact.db`（6192 contacts）+ `chat_20292966501@chatroom.json`（would_insert=50），随后 `brain wechat-sync --since 2026-03-23T11:33:07` apply 成功：`persons_created=6192`、`identifiers_added=609`（`wechat_alias`）、`interactions_added=50`、`chats_processed=1`、`elapsed_ms=111333.9`。预先快照 `20260422-093307-bing5-wechat-pre-apply.duckdb`（sha `1c8d43da...`）；审计 `ingest-log-recent` 记录 `source=wechat mode=apply status=ok`。落库核对：`person_identifiers.kind=wxid` 6192、`kind=wechat_alias` 609、`interactions.source_kind=wechat` 50。 |
| 2026-04-22 | — | **B-ING-5 扩容（helper chats）**: `wechat-sync` 新增 `--include-helper-chats` 开关（默认关闭）；开启后纳入 `chat_file_transfer_assistant.json` / `chat_filehelper.json`。dry-run 评估新增 100，快照 `20260422-112619-bing5-helper-chats.duckdb` 后 apply 实际 `inserted=50`（另 50 同 `source_id` 去重）；复跑 dry-run 三会话 `would_insert=0`。 |
| 2026-04-22 | — | **B-ING-5 噪音控制阀**: `wechat-sync` 新增 `--chat-whitelist` / `--chat-blacklist`（会话级过滤）与 `--helper-chat-mode link-person|no-person`（helper 会话是否绑定 person）。可实现“保留 filehelper 记录但不挂到联系人”或“直接黑名单屏蔽 helper 噪音”。 |
| 2026-04-22 | — | **B-ING-5 默认策略固化（runbook+preset）**: 新增 `tools/housekeeping/wechat-ingest-preset.ps1`（`default` / `helper-no-person` / `helper-link-person` / `helper-blacklist`，`-Apply` 自动先 snapshot），并新增 `architecture/wechat-ingest-policy-runbook.md` 快捷命令手册；`helper-no-person` dry-run 冒烟已通过。 |
| 2026-04-22 | — | **B-ING-5 一键核对链路**: `wechat-ingest-preset.ps1` 新增 preflight 门槛（`-MaxWouldInsert`）与 `-RunPostChecks`（自动跑 `ingest-log-recent` + 幂等 dry-run + `eval_people.py` + 趋势刷新）。新增 `architecture/wechat-ingest-acceptance-checklist.md` 验收清单；`helper-no-person -RunPostChecks` 全链路通过。 |
| 2026-04-22 | — | **B-ING-5 只读巡检定时化**: 新增 `tools/housekeeping/brain-wechat-inspect.ps1` 与 `register-brain-wechat-inspect.ps1`，将 `helper-no-person -RunPostChecks` 固化为每日只读巡检（默认 21:30）。`-RunNow` 冒烟通过，计划任务 `BrainWechatInspect` 状态 `Ready`。 |
| 2026-04-22 | — | **B-ING-3/B-ING-4 · WhatsApp 真跑收官**: `backup-ios-locate` 命中 `ChatStorage.sqlite`（`C:\Users\chase\Apple\MobileSync\Backup\00008101-0002250A21A3003A\7c\7c7fba66680ef796b916b067077cc246adacf01d`，2,039,808 bytes）；先 dry-run（`--limit 30`）抽样后 apply 全量：`rows_seen=1451` / `inserted=1451` / `persons_created=57` / `messages_without_peer=0` / `elapsed_ms=7280.3`。预先快照 `20260422-091535-bing3-whatsapp-pre-apply.duckdb`（sha `46b6c9c4...`），审计 `ingest-log-recent` 记录 `source=whatsapp_ios mode=apply status=ok` 且自动回填 `backup`。当前 `interactions.source_kind='whatsapp_ios'` 总量 1451。 |
| 2026-04-22 | — | **A1/A2/A4 eval + E2 每日调度落地**: A1 现成 `tests/eval_ask.py`（10/10，Top-3 hit ratio=1.0）；新增 A2 `tests/eval_text_inbox.py` + `text_inbox_eval.yaml`（6/6，含 low-confidence 入 draft 与 PII block）；新增 A4 `tests/eval_write.py` + `write_eval.yaml`（3/3，template 路径下 `## 参考` / banned phrase / 段落上限全过）。E2 新增 `tools/housekeeping/brain-daily-digest.ps1` 与 `register-brain-daily-digest.ps1`，已注册 `BrainDailyDigest`（每天 07:00）并 `-RunNow` 冒烟通过；`D:\second-brain-content\08-indexes\digests\daily-2026-04-22.md` 已生成。全量 pytest 仍 **241/241** 绿。 |
| 2026-04-22 | — | **B-ING-2 · T3 阈值抽到 `config/thresholds.yaml`**: `merge_candidates._GRAPH_KIND_SCORES` / `_GRAPH_DEFAULT_SCORE` 原本硬编码，auto-apply 阈值只能从 CLI `--auto-apply-min-score` 传入。现在 `config/thresholds.yaml` 新增 `merge_queue:` 段（`graph_kind_scores` / `graph_default_score` / `auto_apply_min_score`），加一层 `@lru_cache` 的 `_load_merge_queue_config()` 懒加载，CLI 未显式传阈值时 fallback 到 YAML。默认 `auto_apply_min_score: 0.0`（= 禁用 auto-merge，与 B-ING-1 行为完全一致）；改成 0.95 即可让 E1 周任务自动合 phone 级高置信对，email/wxid 仍排队。Back-compat：`_GRAPH_KIND_SCORES` / `_GRAPH_DEFAULT_SCORE` 模块级别名保留。新增 `tests/test_merge_queue_config.py` 7 用例（YAML 读取 / 缺失 fallback / malformed / 越界 auto-apply / caller 覆盖 / None → YAML / back-compat 别名），全量 **241/241** 绿。 |
| 2026-04-22 | — | **ROADMAP 对齐**: 顶部加"2026-04-22 状态快照"表 + 每 Phase 标题追加 ✅/🟡 标记。F0–F3/A1–A4/E1 标记 ✅（代码已交付且 pytest 覆盖），A5/E2 标记 🟡（A5 真数据未跑 / E2 Windows 任务计划未注册）。Phase 内的 `[ ]` 勾选从 v5 起再没同步，下一次升级到 v6 时清理；在那之前以新增的顶部状态表为准。 |
| 2026-04-22 | — | **Phase A6 起稿 · 动态人物档案**: 受 2026-04 业内调研（Zep/Graphiti bi-temporal KG、Mem0 pin/override/erase、Letta 三段式、Neo4j entity resolution）启发，在 ROADMAP 新增 `Phase A6`（4 sprint / 1.5–2 周末），把 `06-people` 从聊天摘要升级为可回溯的动态档案：Sprint 1 `person_facts`（bi-temporal）+ `person_metrics`（派生）；Sprint 2 `open_threads` 到期化 + 承诺抽取；Sprint 3 rolling topics + weekly digest；Sprint 4 relationship tier + cadence alarm。对齐原则：不重构 A5 既有表、Episodic interactions 恒为真相源、所有派生必须可从 interactions + facts 重建。 |
| 2026-04-22 | — | **Phase A6 Sprint 3 ✅ 交付**: DuckDB 升到 `_brain_migrations v5`，`person_insights` 补 `window_start_utc` / `window_end_utc` / `source_kind` / `superseded_by` 四列（ALTER TABLE 对 90 行历史 `topics`/`commitments`/`warmth` 旧行无破坏——旧行 `superseded_by IS NULL` 被当作 "current" 自然兼容）。新增 `brain_agents/person_digest.py` 两类 insight：`topics_30d`（top-K 主题词 + 60–160 字中文小结，严格 JSON prompt 走 Ollama fast model `qwen2.5:14b-instruct`）与 `weekly_digest`（7 天自然语言段落）；`rebuild_one` / `rebuild_all` 幂等——每次写一条新行并把旧行的 `superseded_by` 指向新 id，历史可回溯；LLM 崩盘、返回乱码、空窗口三类路径各自安全降级到启发式占位或直接跳过。CLI 新增 `brain person-digest rebuild [--person-id\|--all] [--insight-type both\|topics\|weekly] [--topics-days 30] [--weekly-days 7]` 与 `brain person-digest show <pid>`。`people_render` 的卡在 `## Open threads` 之后注入 `## Topics (30d)`（tag chips ` ` · ` ` + 小结段落 + window 元数据）和 `## Weekly Digest`（段落 + window 元数据），没有 current 行时两节都静默省略（避免空 header 污染）。E2 `brain-e2-task.ps1` 的 weekly-review 分支在 people-eval 趋势前**先**跑 `person-metrics recompute --all` 再跑 `person-digest rebuild --all --weekly-days 7 --topics-days 30`，子步骤失败只 `hub-alert` 不中断主流程。pytest +18 case（`test_person_digest.py` 15 · rebuild 双写 / 幂等 + superseded 链 / 空窗口跳过 / LLM 崩盘回退启发式 / LLM 乱码回退 / 30d 窗口过滤真的过滤 / fenced JSON 与散文夹带都能解析 / rebuild_all 扫活跃人 / 错误隔离；`test_people_render.py` 扩 3 case · Topics+Weekly 节渲染 / chips tag / 无 digest 数据静默省略），Sprint 1+2+3 全核心 **77/77** 绿。生产烟测：snapshot `brain-telemetry-pre-a6s3-20260422-220054.duckdb`（sha `2D92DE01...` / 47.01 MB），v5 迁移 0 错，田果（p_8168e6185835）首次 rebuild = topics_30d(`人民币` · `欧元` · `自拍杆`, "宝宝向妈妈求助换汇和带物品，提到机票和睡眠情况") + weekly_digest（"本周主要聊了一些生活琐事和旅行准备..."），`rebuild --all --min-interactions-30d 3 --max-persons 20` 扫 20 人全 ok / 0 错 / ~3 min，第二次 rebuild 验证 superseded 链 91→95、92→96 current 行数稳 2 条。验收报告 `architecture/a6-sprint3-acceptance.md`。承接 Sprint 2 的遗留问题：原来 LLM commitment-scan 在田果身上抽 0 条承诺（summary 太碎），Sprint 3 的 rolling digest 给了同一批 summary 一个更高层的 LLM 视角并产出非空叙述，说明"噪音在条目层噪、聚合层清"；未来 Sprint 4 的 tier 建议可直接基于 `weekly_digest` 做 warm signal。 |
| 2026-04-22 | — | **Phase A6 Sprint 2 ✅ 交付**: DuckDB 升到 `_brain_migrations v4`，`open_threads` 补 `due_utc` / `promised_by (self/other)` / `last_mentioned_utc` / `source_interaction_id` / `source_kind` / `body_hash` / `created_at` 七列（ALTER TABLE 方式对 6192 行现存数据无破坏）。新增 `brain_agents/open_threads.py`（`add_thread / close_thread / reopen_thread / update_due / list_threads / list_due / classify_due`，body_hash 每人级去重让 LLM 重扫幂等）+ `brain_agents/commitment_extract.py`（Ollama fast model qwen2.5:14b，强 schema prompt → JSON 数组 → 每人独立解析，`_call_llm` 可注入以供测试，LLM 失败不崩盘）。CLI 新增 `brain thread add|close|reopen|update-due|list` + `brain due [--within N] [--overdue-only]` + `brain threads-scan [--since-days N] [--apply]`（默认 dry-run + 置信度过滤）。`people_render` 的 `## Open threads` 从单行摘要升级为 6 列表格（status chip ⚠️/🔥/⏳、due、who owes、body、last seen、source），空状态保留 `(none)`。`digest.generate_daily_digest` 新增 `## Today's Commitments` 与 `## Overdue Commitments` 两节，返回 JSON 加 `due_today_count` / `overdue_commitments_count`。pytest +34 case（test_open_threads 17 + test_commitment_extract 12 + test_digest 3 + test_people_render 2），核心 60/60 全绿。生产烟测：snapshot `20260422-214452-a6-sprint2-pre-apply.duckdb`（sha `AC6D82DE...`, 47.01 MB），migration v4 0 error，手动 3 条 thread（田果 4/29 soon / Jason 今日 due / Akane 已 overdue 2 天）写入，`brain due --within 10` 正确排序（overdue 最先），daily-2026-04-22.md 两节正确渲染，田果卡 `## Open threads` 显示 ⏳ soon 芯片。LLM dry-run 10 persons / 0 candidates（符合预期：当前 WeChat interactions summaries 多为 `[msg_type=50]` 元数据，Sprint 3 interaction summaries 落地后复扫会显著提升）。验收报告 `architecture/a6-sprint2-acceptance.md`。 |
| 2026-04-22 | — | **Phase A6 Sprint 1 ✅ 交付**: DuckDB 升到 `_brain_migrations v3`，新增 `person_facts`（bi-temporal：`valid_from` / `valid_to` / `confidence` / `source_kind` / `source_interaction_id`；`value_json` 永远 JSON 编码，同 key 新写自动关闭旧记录）与 `person_metrics`（派生：`first_seen / last_seen / interactions_all|30d|90d / distinct_channels_30d / dormancy_days`，`recompute_all` 一次 CTE 扫 `interactions`）。新增 `brain_agents/person_facts.py` + `person_metrics.py`，CLI `brain facts add|list|invalidate` + `brain person-metrics recompute|show`，`people-render` 卡插入 `## Facts` + `## Metrics` 两节（空数据安全降级）+ `--facts-history` 展开历史。pytest +21 case（test_person_facts 11 + test_person_metrics 7 + test_people_render 3），全量 **273/273 passed**。生产回填：snapshot `20260422-184830-a6-sprint1-pre-apply.duckdb`（sha `e8137d68...` / 49 MB），`recompute --all` updated=656；田果（p_8168e6185835）Metrics = 互动 424 / 30d 147 / 90d 274 / last 2026-04-20 (wechat) / dormancy 2d。验收报告 `architecture/a6-sprint1-acceptance.md`。 |
| 2026-04-22 | — | **WeChat decoder 全量导出上线**: `C:\dev-projects\wechat-decoder\scripts\wechat_chat_reader.py` 加 `--export-all` / `--limit 0`（抽出 `export_and_write_chat` helper 复用），一次导 54 个会话 / 6136 条原始消息；hub 侧 `brain wechat-sync --include-helper-chats` apply：`inserted=6036 / identifiers_added=609 / persons_created=0 / errors=0`，全库 WeChat interactions 从 101→6137、参与 persons 26→598，田果 (p_8168e6185835) 互动数 0→424。预同步快照 `20260422-181525-wechat-full-export.duckdb`。 |
| 2026-04-22 | — | **B-ING-1.12 · orphan identifier 修复**: 宏观验收时发现 3 条 `person_identifiers` 的 `person_id` 在 `persons` 表里不存在（`amirnesta@gmail.com` / `h.oosterhuis119@outlook.com` / `astone.shi@gmail.com`）。根因是 `contacts_ingest_ios._apply` 在 strong-kind `register_identifier` 触发 auto-T2 merge 后没跟踪 survivor pid，后续 email 插入使用了已 absorbed 的 pid；`person_identifiers` 没有 FK 所以静默写入 orphan。修复：caller 跟踪 `r["person_id"]`，`ensure_person_with_seed` 同步加固，`register_identifier` docstring 写清 caller 契约；WhatsApp ingest 不需改（每 peer 只挂 1 个 identifier）。新增 `test_contacts_ingest_ios_orphan_regression.py` 2 用例复刻 bug 路径。生产 3 条 orphan 已 reparent 到 merge survivor（snapshot `20260422-090206-bing1.12-orphan-cleanup.duckdb`）。全量 **234/234** 绿。详见 `architecture/bing1-followups.md` B-ING-1.12 段。 |
| 2026-04-22 | — | **B-ING-0 验收强化**（PC-3 字段 + 文档 + E1 健康检查，无新真数据路径）: `ingest_log.log_ingest_event` 现写 `started_at`（可 `started_at_utc=` 显式传，或从 `ts_utc`−`elapsed_ms` 自动推，满足 `real-ingest-scope.md` 对 Provenance 的字段表）。`real-ingest-scope.md` 的 PC-1/3/4 与 B-ING-0 代码对齐，删「只写文档」旧段。E1 `brain-weekly-maintenance.ps1` 加第 3 步只读 `ingest-log-recent --days 14 --limit 10`；`Invoke-BrainStep` 改 `python -m brain_cli.main` + `PYTHONPATH=…/src`（不再 `uv run`）。+1 pytest（显式 `started_at` 覆盖推导）。全量 **192 passed**。 |
| 2026-04-21 | — | **F3 `merge-candidates sync-from-graph --auto-apply-min-score`**: 把图→T3 的"只写 pending、等人工 accept"半自动流程升级为"高置信自动合、低置信仍 pending"。`sync_from_graph` 新增 `auto_apply_min_score: float\|None`：`None`/≤0/>1/非数字均视为关闭（安全 fallback，不会误合）；`(0, 1]` 内的值把 proposed 分两桶，`score >= 阈值` 的先 `_insert_pending` 再立刻 `accept_candidate`（走完整 `merge_persons` + `merge_log` 审计链），低置信仍落 pending。`max_inserts` 预算优先喂给高置信桶。返回值新增 `auto_applied` / `would_auto_apply` / `would_stay_pending` / `auto_apply_min_score` / `auto_applied_samples`。CLI `brain merge-candidates sync-from-graph --apply --auto-apply-min-score 0.95` / MCP `merge_candidates_sync_from_graph_tool(auto_apply_min_score=…)` 全同步。E1 周任务加第 5 步可选自动合（`brain-weekly-maintenance.ps1 -AutoApplyMinScore`，默认 0 关闭；`register-brain-weekly-maintenance.ps1 -AutoApplyMinScore 0.95` 一键启用）。推荐 0.95 阈值 = 只自动合 `phone` 对（`email`/`wxid` 的 0.92/0.93 仍人工审）。12 新 pytest（dry-run 分桶预览 / apply 自动合 phone 留 email 在 pending / 无阈值仍全 pending / 预算优先高置信 / 阈值越界安全降级 / `_coerce_threshold` 7 参数化用例）+ 老测试的 merge_candidates 清理升级为 id 白名单（旧的 `DELETE FROM merge_candidates` 全表清会误删用户真实数据）。全量 **191 passed**。|
| 2026-04-21 | — | **B6 对拍 · Pass 1/3 通过**: 首次 PS↔Python manifest 对拍。源 `D:\BaiduSyncdisk\20250922.手机照片`，839 文件，824 完全一致（98.2%），15 差异**全部是 Python 更准**（PNG 真 EXIF：Pillow 12.2 读到 iPhone 截图埋的 `DateTimeOriginal`，PS 的 `System.Drawing.Image` 对 PNG EXIF 支持有限只回退 mtime），0 Python 退化。过程中揪出两个真 bug 并修：（a）`asset_migrate_parity.load_manifest` 改用 `utf-8-sig` 吃掉 PS 5.1 `Export-Csv -Encoding UTF8` 的 BOM（没改前首列名变 `\ufeffsource_path` 造成 common_count=0 假阴性，+2 pytest 回归）；（b）`Pillow>=10.4.0` 加入 `tools/py/pyproject.toml`（没装时照片全 fallback mtime，造成 ~45% 假差异）。归档 `D:\second-brain-assets\_migration\parity-archive\parity-2026-04-21.*`。`asset-parity-runbook.md` 加 Pillow 前置。下一 pass ≥ 2026-04-28，换源目录。全量 **179 passed**。 |
| 2026-04-21 | — | **E2 · asset-migrate 对拍工具**: 为 B3/B4 后的 3 周 PS↔Python 并跑期准备。新增 `brain_agents/asset_migrate_parity.py`——`load_manifest` 读 TSV（容错老格式）；`diff_manifests` 以 `source_path`（大小写无关 + 斜杠归一化）为键，三维比对 `rule`/`action`/`target_dir`（`target_dir` 的斜杠/反斜杠差异自动归一化，避免虚假 diff）；`render_markdown` 出 `对拍通过 / 有差异` 顶部结论 + 整体汇总 + 每类计数 + 三张差异明细（only-in-A / only-in-B / 共同但分类不同，各前 20 条）；`|` 字符自动转义防表格破损。CLI `brain asset-parity-diff --a X.tsv --b Y.tsv [--output report.md]`。同时产出 `architecture/asset-parity-runbook.md` 讲"预期可接受差异"vs"必须停下修"的 6 种分类 + 3 次通过才 B6 的出口条件。17 个新 pytest（identical/disjoint/mismatch/case-insensitive/slash-normalize/pipe-escape/stats-by-rule/missing-side/report-write/omit-write），全量 **177 passed**。|
| 2026-04-21 | — | **B4 · `brain-asset-source-cleanup.ps1` → Python**: 新增 `brain_agents/asset_source_cleanup.py`——`parse_execute_log` 抽 `OK\t<src>\t->\t<dst>` 行拿源→目标映射；`derive_ok_map_from_manifest` 作为 fallback（当 `<job>-execute.log` 缺失时，只取 `action in (copy, copy-to-assets-inbox)` 行，`copy-to-brain-inbox` 不进删除集——源进 Tier A inbox 的删除是人工决策）；`check_pair` 三道门（src 在 / dst 在 / size 一致）；`cleanup()` 主流程写 `<job>-cleanup.log`（`WOULD-DELETE` / `DELETED` / `SKIP-SRC-GONE` / `SKIP-DST-MISSING` / `SKIP-SIZE-MISMATCH` / `FAIL-*` / `DELETED-DIR`）。CLI `brain asset-source-cleanup [--manifest-path] [--execute-log] [--source-root] [--apply] [--no-delete-empty-dirs]`。**安全升级两处**：（1）默认 dry-run（PS 默认真删），`--apply` 显式；（2）空目录清扫改为 `--source-root` 显式开启（PS 硬编码 `D:\BaiduSyncdisk`）。21 个新 pytest（OK 行解析 + manifest fallback + 三道安全门 + dry-run 不删 + apply 真删 + latest-manifest + 空目录级联清扫 + 关断），全量 **160 passed**。PS 版暂保留 3 周对拍后 B6 删。 |
| 2026-04-21 | — | **B3 · `brain-asset-migrate.ps1` → Python**: 新增 `brain_agents/asset_migrate.py`——`classify_file` 复刻 PS 全部分类规则（photos/video/audio/font/archive/text→brain-inbox/pdf/document/trash/other，`.tiff`/`.webp`/`.ds_store` 补齐）；`scan()` 枚举源目录 + 过 `~/.brain-exclude.txt` + 写 `<assets_root>/_migration/<job>-manifest.tsv`（列同 PS）；`execute()` 读 manifest → copy2+mtime 保留 + 碰撞加 `-YYYYMMDD-HHmmss` 源 mtime 后缀 + `trash-candidate` 只记日志不删 + `__BRAIN_INBOX__` 落 `content_root/99-inbox` + 写 `*-execute.log`。CLI `brain asset-scan --source X --job Y` 和 `brain asset-migrate-execute [--manifest-path]`。**源文件永不删除**（由人工 7 天后手动清）。30 个新 pytest（classify 全分支 + exclude startswith/substring + scan 写 TSV + execute copy/missing/collision/trash/brain-inbox/latest-manifest），全量 **139 passed**。PS 版暂留 3 周对拍后再 B6 删除。 |
| 2026-04-21 | — | **B2 · 删除 `brain-asset-overview-cards.ps1`**: 按 `asset-migration-plan.md` 的 B2 建议——该脚本原先要启 cursor-agent 烧 token 生成"资产簇 overview"，能力已被 `brain_agents/write_assist.py` 的本地 LLM 路径覆盖，且"批量自动给每个簇写描述"无强需求。删除 5.5 KB PS；同时清 `brain-tools-index.md` 对应条目。 |
| 2026-04-21 | — | **B-ING-1 操作手册**: 新增 `architecture/bing1-runbook.md`——从"iPhone 做一次非加密备份"到"apply 通讯录到 DuckDB"的 6 步清单，每步带期望输出 / 失败应对 / 回滚指令（复用 B-ING-0 的 snapshot）。B-ING-1 之后一切已就位，只欠用户真机配合。 |
| 2026-04-21 | — | **B1 part 2 · `brain asset-dedup`**: `brain_agents/asset_dedup.py`——两遍扫描（先按 size 分桶，只对 size ≥ 2 的桶算 SHA256；`_migration` 恒跳 / `99-inbox` 默认跳 / 可 `--include-inbox`），按"浪费字节"降序输出重复组，"KEEP" 选最短路径；写 `<assets>/_migration/dedup-<today>.{md,tsv}`（**只做报告，绝不删**）。CLI `brain asset-dedup [--min-kb N] [--include-inbox] [--no-write]`。11 新 pytest。真机发现 **111 冗余 / 471.8 MB** 可释放。全量 **109 passed**。 |
| 2026-04-21 | — | **B1 part 1 · `brain asset-stats`**: `brain_agents/asset_stats.py`——纯元数据 os.walk（不跟 symlink，跳过 `_migration/` 子树），渲染同老 PS 的 5 小节 MD 报告（一级目录 / ext Top20 / 按月 / Top10 单文件），写到 `<content_root>/04-journal/brain-assets-stats-<today>.md`。CLI `brain asset-stats [--assets-root X] [--content-root Y] [--no-write]`。6 新 pytest。真机 11,751 文件 / 73.79 GB / 1.8 s 扫完。按 `architecture/asset-migration-plan.md` 的 B1 执行，PS 文件先留，B6 统一删。全量 **98 passed**。 |
| 2026-04-21 | — | **F3 `context_for_meeting` 自动保鲜**: `_collect_graph_hints` 默认 `auto_freshen=True`，先调 `rebuild_if_stale(max_age_seconds=3600)`——graph_hints 永远 ≤ 1h 于 DuckDB（不再等 E1 每周一次）。Fresh 时成本 < 5 ms（只是 mtime stat）；stale 时顺带重建 ~7 s。`context_for_meeting(auto_freshen_graph=False)` 可关停。新增 2 个 pytest（auto_freshen 默认触发 / False 时不触发）+ 存量 5 个保持绿。全量 **92 passed**。 |
| 2026-04-21 | — | **B-ING-0 落地**（PC-1 + PC-3 + PC-4 合批）: `brain_memory/structured.py` 新增 `transaction()` 上下文（thread-local 活连接 + BEGIN/COMMIT/ROLLBACK，禁止嵌套）；`brain_agents/ingest_backup.py`（快照 DuckDB → `_backup/telemetry/<ts>-<label>.duckdb` + sha256 sidecar + pointer-log.jsonl）；`brain_agents/ingest_log.py`（`log_ingest_event` 写 `ingest-YYYY-MM-DD.jsonl`，IOError 不抛只标 skipped）；3 条 ingest（AddressBook/WhatsApp/WeChat）全部接入 `wrap_transaction=True` + 日志发射；CLI `brain ingest-backup-now --label` + `brain ingest-log-recent --days --source`。12 个新 pytest 全绿（snapshot/sanitize/list/apply-sha/dry-run/append/OS skipped/commit/rollback/nested-reject/post-error）。真机冒烟：24 MB DuckDB 备份 55 ms 落盘。全量 **90 passed**。 |

---

*本文件是 `second-brain-hub` 的路线图唯一真相源. AI 会话开始时若被要求"做下一步", 优先读这里.*
