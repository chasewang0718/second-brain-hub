# Changelog

约定: prompt / config / schema 的**每次改动**必须记录在此 (即使是小改). 便于回滚和解释为什么 eval 分数变了.

格式:
```
## YYYY-MM-DD - [type] 标题
- what: 改了什么
- why: 为什么改
- eval-delta: (如有) 跑 eval 前后的准确率变化
```

类型: prompt / config / schema / tool / docs / infra

---

## 2026-04-20 - docs+config: ROADMAP v5 · 零预算全自主
- what:
  - 重写 `architecture/ROADMAP.md` 为 v5 (从 v4 重大转向, Python 唯一栈 + 零预算 + 嵌入式 DB 三件套)
  - 物理目录改名: `D:\brain` → `D:\second-brain-content`, `D:\brain-assets` → `D:\second-brain-assets` (Phase F0, 用户手动执行 PS Rename-Item)
  - `rules/AGENTS.md` 顶部加 v5 转向横幅, 第 2 条从"原则给建议"改为"偏好给建议", 第 12 条 "推进 hub" 改为直接执行 + 新增 "处理 cursor 队列" 触发词, 全文路径更新
  - `rules/cloud-local-delegation.md` 标记废弃, 新增 `rules/cursor-delegated-escalation.md` 为权威云端策略文档
  - `config/paths.yaml` 路径改为 `D:\second-brain-content` / `D:\second-brain-assets`, 新增 `cursor_queue_dir`
  - `config/task-router.yaml` 重写: 删所有 cloud fallback 字段, 改为 `on_failure.action: enqueue_cursor`, 新增硬红线 priority_rules
  - `rules/privacy.md` / `rules/inbox-ingest.md` / `brain-tools-index.md` 路径全部更新
- why:
  - 零预算硬约束 (Cursor 订阅 $20/月为 sunk cost, 不再额外付云端 API)
  - 统一目录命名规范 (all-lowercase-kebab + `second-brain-*` 前缀)
  - 范式转向"AI 自主执行 + git 回滚", 原则降级为偏好, 仅保留 Tier C / 破坏性 git / git 安全网三条硬红线
  - Python + LangGraph + FastMCP + DuckDB + Kuzu + LanceDB 为 v5 最终技术栈
- breaking:
  - 所有指向 `D:\brain\` 或 `D:\brain-assets\` 的 PS 脚本需同步改 (Phase A3 上线时整体删除, 暂不逐个修)
  - 任何引用 `cloud-local-delegation.md` 的代码/配置需改指向 `cursor-delegated-escalation.md`
  - PS profile `$BRAIN_ROOT` / `$BRAIN_ASSETS_ROOT` (若存在硬编码) 需更新
- migration:
  1. 关闭 Cursor / Explorer / AHK 等使用这两个目录的进程
  2. 执行 `Rename-Item D:\brain second-brain-content` + `Rename-Item D:\brain-assets second-brain-assets`
  3. `cd D:\second-brain-content && git status` 验证 git 仍活
  4. 内容仓内同步镜像 `AGENTS.md` / `my-privacy-rules.md` (手动或等 Phase F1 Python 自动同步)
- eval-delta: N/A (v5 架构变动, 非模型侧改动)

## 2026-04-19 - infra: 仓库初始化
- what: 创建 second-brain-hub 骨架 (17 子目录 + 根级 README/.gitignore/.gitattributes)
- why: 从 brain-tools (旧名 chase-brain-tools) 分离出规则控制中枢, 与内容仓 brain-content 解耦
- eval-delta: N/A (尚无 eval 基线)

## 2026-04-19 - infra: 迁 brain-tools 内容进 hub
- what: 复制 brain-tools 全部脚本 + 配置到 hub, 按 tools/{ollama-pipeline,asset,health,housekeeping,lib,ahk} 分类. 拆出 schema.json -> schemas/, prompt-template.md -> prompts/system/
- why: 建立清晰的 tools/ config/ prompts/ schemas/ 分层
- breaking: 用户 PS profile 的 \$BRAIN_TOOLS_ROOT 现指向新 hub; 所有 gollama-* / gasset-* / gbatch-* 已更新. brain-tools 旧仓库保留为安全备份, 稳定后可删

## 2026-04-19 - config+docs: 通用云-本地委派策略 v1
- what: 写 rules/cloud-local-delegation.md (策略, 人读) + config/task-router.yaml (路由表, 机器读)
- why: 把"本地先跑 + 云端验收兜底"从 PDF 特例提升为**通用模式**, 未来 inbox-text/capsd/image 任务都走同一套机制
- content:
  * 3 种工作模式 (batch-pipeline / interactive / long-running-agent)
  * 4 类升云触发器 (Quality / Complexity / Risk / Budget)
  * 月度预算护栏 + 自动降级机制
  * 反馈循环: escalation 结果回灌 few-shot, 准确率爬坡 vs 成本爬降
- tasks configured: pdf-classify (已实现) + inbox-text-route, inbox-file-route, capsd-quick-fix, image-classify, code-refactor (未实现, 等 dispatcher 落地)

## 2026-04-19 - docs: 抽 D:\brain 规则类文件进 hub/rules
- what: 复制 AGENTS.md -> rules/AGENTS.md, my-privacy-rules.md -> rules/privacy.md, brain-inbox-ingest.md -> rules/inbox-ingest.md, brain-tools-index.md -> hub/brain-tools-index.md
- why: 规则内容中心化到 hub, 内容仓只保留内容
- strategy: hub 副本标为权威 (authoritative_at), D:\brain 原件标为 mirror, 保留以便 Cursor 自动加载. 待 brain-content 迁移时统一处理
- breaking: 无 (原文件原位未删, agent 加载行为不变)

## 2026-04-19 - docs: 12-18 月 roadmap + Phase 1 详细任务单
- what: 写 ROADMAP.md (9 Phase 路线图到 "完全形态" 的外脑系统) + architecture/phase-1-plan.md (Phase 1 的 7 个子任务, 共 ~16h)
- why: 把长期愿景 (Personal Agentic IDP with Local-First Model Cascade) 固化下来, 锁定执行节奏
- scope:
  * ROADMAP: 项目定性 + 难度分布 + 技术风险 + 9 个 Phase + 技术栈决策 + 不做什么
  * Phase 1 任务: telemetry 打点, escalation 结构化, feedback harvester, task-router 运行时读取, golden set v1 (20 份), eval runner, 月度成本报告
- principle: 每个 Phase 自成闭环. Phase 1 退出标志 = "每周低置信率" 可绘制成下降曲线

## 2026-04-20 - config+tool+docs: Phase 1 最小包落地 (paths/thresholds/config-loader)
- what: 新增 `config/paths.yaml` 与 `config/thresholds.yaml`; 新增 `tools/lib/config-loader.ps1` (提供 `Get-BrainConfig` / 点号路径读取); 更新 `architecture/ROADMAP.md` 勾选 3 项已完成子任务
- why: 先建立配置单一真相源, 为后续把 PDF pipeline 从硬编码迁到配置驱动做准备
- eval-delta: N/A (本次未变更 prompt/schema/模型行为)

## 2026-04-20 - tool+docs: PDF pipeline 改为配置驱动 (local/qa/apply)
- what: `brain-asset-pdf-local.ps1` / `brain-asset-pdf-qa.ps1` / `brain-asset-pdf-apply.ps1` 接入 `tools/lib/config-loader.ps1`, 默认从 `config/paths.yaml` 与 `config/thresholds.yaml` 读取 `ProposalDir/InboxDir/OutputDir/brain_root/brain_assets_root/timeout/qa_sample_percent/confidence_below`, 读取失败自动回退旧硬编码
- why: 完成 Phase 1 的关键一步, 让阈值和路径可以在配置层修改并立即生效, 减少脚本级硬编码维护成本
- eval-delta: N/A (本次未变更 prompt/schema/模型行为)

## 2026-04-20 - tool+docs: 新增 telemetry 写入库 (Phase 2-1)
- what: 新增 `tools/lib/telemetry.ps1`，提供 `Get-TelemetryLogsDir` / `Get-TelemetryLogPath` / `Write-Telemetry`; 支持自动补 `ts`、按月写入 `telemetry/logs/YYYY-MM.jsonl`、`output_summary` 截断到 50 字符、`task=blocked-tier-c` 自动剔除 `source` 字段; 同时移除 `config-loader.ps1` 与 `telemetry.ps1` 里的 `Set-StrictMode` 以避免 dot-source 污染调用方会话
- why: 为 Phase 2 的统一打点奠定基础, 并避免库文件影响既有脚本执行语义
- verify: 已写入 `phase2-smoke` 样本并通过 `telemetry/analyze.ps1 -Days 1 -Task phase2-smoke` 读到统计
- eval-delta: N/A (本次未变更 prompt/schema/模型行为)

## 2026-04-20 - tool+docs: PDF worker/QA/apply 接入统一 telemetry (Phase 2-2)
- what: 在 `brain-asset-pdf-local.ps1` / `brain-asset-pdf-qa.ps1` / `brain-asset-pdf-apply.ps1` 接入 `tools/lib/telemetry.ps1`; 新增 `Write-TelemetrySafe` 包装, 在成功/低置信/解析失败/审计失败/apply 跳过与失败等关键分支写 telemetry 事件
- why: 把运行结果、错误与人工审计决策统一落到 JSONL, 为后续低置信率趋势和反馈闭环提供可分析数据
- verify: 三脚本解析通过 (`Get-Command` smoke), 且脚本内已存在 telemetry 调用点 (local 6 处 / qa 3 处 / apply 6 处)
- eval-delta: N/A (本次未变更 prompt/schema/模型行为)

## 2026-04-20 - tool+docs: 低置信/schema-fail 自动导出 `_escalation` (Phase 2-3)
- what: 在 `brain-asset-pdf-local.ps1` 新增 `EscalationDir` 配置读取与 `Write-EscalationItemSafe`; 当 `schema-fail` 或 `confidence_below_threshold` 时, 自动落盘结构化 JSON 到 `_escalation/`
- why: 把需要云端兜底的问题从日志文本升级为可机器处理队列, 为后续 `harvest-feedback` 与 escalation handler 提供输入
- verify: 脚本解析通过 (`Get-Command` smoke) 且无 lints
- eval-delta: N/A (本次未变更 prompt/schema/模型行为)

## 2026-04-20 - tool+docs: 新增 feedback harvester (Phase 2-4)
- what: 新增 `tools/feedback/harvest-feedback.ps1`, 扫描 `_escalation/*.processed.json` 并生成 few-shot 候选到 `prompts/few-shot/pdf/harvested/`; 支持 `-DryRun` (默认开), `-MaxItems`, 配置读取 `paths.escalation_dir`
- why: 把云端兜底的结果转成可复用样本, 形成“失败 -> 修正 -> few-shot”的反馈闭环
- verify: 脚本解析通过 + dry-run 可执行 (当前环境 escalation 目录为空, 属正常)
- eval-delta: N/A (本次未变更 prompt/schema/模型行为)
