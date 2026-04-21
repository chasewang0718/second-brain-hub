---
title: second-brain-hub 优化路线图
status: active
created: 2026-04-20
updated: 2026-04-21
authoritative_at: C:\dev-projects\second-brain-hub\architecture\ROADMAP.md
---

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

### Phase F0 · 目录改名 (30 分钟, 手工 + 一次性)

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

### Phase F1 · Python + MCP Server 骨架 (2-3 周末)

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

### Phase F2 · Git 安全网 (1-2 周末)

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

### Phase F3 · 记忆层 (2-3 周末)

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

### Phase A1 · ask-engine (1-2 周末, 最先做)

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

### Phase A2 · text-inbox agent (2-3 周末)

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

### Phase A3 · file-inbox agent (2-3 周末, 包含 PS 弃用)

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

### Phase A4 · write-assist (3-5 周末)

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

### Phase A5 · people-engine (3-5 周末, 依赖 F3 Kuzu)

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

### Phase E1 · 结构自优化 (2-3 周末, 依赖 A1+A2+F2)

**自动执行**, git 兜底.

- [ ] 聚类检测 → 自动建 concept 目录 + commit
- [ ] 密度告警 → 自动拆分 + commit
- [ ] 孤岛检测 → 自动归档 `_archive/` + commit
- [ ] 关联发现 → 自动建双向链接 + commit
- [ ] 调度: 每日凌晨, 单次操作上限 20 次防暴走
- [ ] `brain history --structure` 看自优化历史

**退出标志**: 两周跑下来 20 次操作 revert 次数 ≤ 1.

---

### Phase E2 · 主动化 (2 周末)

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
| 2026-04-21 | — | **B2 · 删除 `brain-asset-overview-cards.ps1`**: 按 `asset-migration-plan.md` 的 B2 建议——该脚本原先要启 cursor-agent 烧 token 生成"资产簇 overview"，能力已被 `brain_agents/write_assist.py` 的本地 LLM 路径覆盖，且"批量自动给每个簇写描述"无强需求。删除 5.5 KB PS；同时清 `brain-tools-index.md` 对应条目。 |
| 2026-04-21 | — | **B-ING-1 操作手册**: 新增 `architecture/bing1-runbook.md`——从"iPhone 做一次非加密备份"到"apply 通讯录到 DuckDB"的 6 步清单，每步带期望输出 / 失败应对 / 回滚指令（复用 B-ING-0 的 snapshot）。B-ING-1 之后一切已就位，只欠用户真机配合。 |
| 2026-04-21 | — | **B1 part 2 · `brain asset-dedup`**: `brain_agents/asset_dedup.py`——两遍扫描（先按 size 分桶，只对 size ≥ 2 的桶算 SHA256；`_migration` 恒跳 / `99-inbox` 默认跳 / 可 `--include-inbox`），按"浪费字节"降序输出重复组，"KEEP" 选最短路径；写 `<assets>/_migration/dedup-<today>.{md,tsv}`（**只做报告，绝不删**）。CLI `brain asset-dedup [--min-kb N] [--include-inbox] [--no-write]`。11 新 pytest。真机发现 **111 冗余 / 471.8 MB** 可释放。全量 **109 passed**。 |
| 2026-04-21 | — | **B1 part 1 · `brain asset-stats`**: `brain_agents/asset_stats.py`——纯元数据 os.walk（不跟 symlink，跳过 `_migration/` 子树），渲染同老 PS 的 5 小节 MD 报告（一级目录 / ext Top20 / 按月 / Top10 单文件），写到 `<content_root>/04-journal/brain-assets-stats-<today>.md`。CLI `brain asset-stats [--assets-root X] [--content-root Y] [--no-write]`。6 新 pytest。真机 11,751 文件 / 73.79 GB / 1.8 s 扫完。按 `architecture/asset-migration-plan.md` 的 B1 执行，PS 文件先留，B6 统一删。全量 **98 passed**。 |
| 2026-04-21 | — | **F3 `context_for_meeting` 自动保鲜**: `_collect_graph_hints` 默认 `auto_freshen=True`，先调 `rebuild_if_stale(max_age_seconds=3600)`——graph_hints 永远 ≤ 1h 于 DuckDB（不再等 E1 每周一次）。Fresh 时成本 < 5 ms（只是 mtime stat）；stale 时顺带重建 ~7 s。`context_for_meeting(auto_freshen_graph=False)` 可关停。新增 2 个 pytest（auto_freshen 默认触发 / False 时不触发）+ 存量 5 个保持绿。全量 **92 passed**。 |
| 2026-04-21 | — | **B-ING-0 落地**（PC-1 + PC-3 + PC-4 合批）: `brain_memory/structured.py` 新增 `transaction()` 上下文（thread-local 活连接 + BEGIN/COMMIT/ROLLBACK，禁止嵌套）；`brain_agents/ingest_backup.py`（快照 DuckDB → `_backup/telemetry/<ts>-<label>.duckdb` + sha256 sidecar + pointer-log.jsonl）；`brain_agents/ingest_log.py`（`log_ingest_event` 写 `ingest-YYYY-MM-DD.jsonl`，IOError 不抛只标 skipped）；3 条 ingest（AddressBook/WhatsApp/WeChat）全部接入 `wrap_transaction=True` + 日志发射；CLI `brain ingest-backup-now --label` + `brain ingest-log-recent --days --source`。12 个新 pytest 全绿（snapshot/sanitize/list/apply-sha/dry-run/append/OS skipped/commit/rollback/nested-reject/post-error）。真机冒烟：24 MB DuckDB 备份 55 ms 落盘。全量 **90 passed**。 |

---

*本文件是 `second-brain-hub` 的路线图唯一真相源. AI 会话开始时若被要求"做下一步", 优先读这里.*
