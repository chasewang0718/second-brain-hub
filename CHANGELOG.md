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

## 2026-04-19 - docs: 抽 D:\brain 规则类文件进 hub/rules
- what: 复制 AGENTS.md -> rules/AGENTS.md, my-privacy-rules.md -> rules/privacy.md, brain-inbox-ingest.md -> rules/inbox-ingest.md, brain-tools-index.md -> hub/brain-tools-index.md
- why: 规则内容中心化到 hub, 内容仓只保留内容
- strategy: hub 副本标为权威 (authoritative_at), D:\brain 原件标为 mirror, 保留以便 Cursor 自动加载. 待 brain-content 迁移时统一处理
- breaking: 无 (原文件原位未删, agent 加载行为不变)
