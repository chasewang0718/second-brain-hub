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
