---
title: 云-本地 AI 协作策略 (已废弃, v5 转向)
tags: [rules, deprecated]
created: 2026-04-19
updated: 2026-04-20
status: deprecated-since-v5
superseded_by: cursor-delegated-escalation.md
---

# 云-本地 AI 协作策略 (已废弃)

> ⚠️ **本文件在 ROADMAP v5 (2026-04-20) 之后已废弃, 保留仅供 git 历史检索.**
> **新的权威策略**: [`cursor-delegated-escalation.md`](cursor-delegated-escalation.md)

---

## 为什么废弃

v5 确定:
- **预算 = $0/月**, 不再允许云端 API 自动计费
- Cursor 订阅 ($20/月) 是 sunk cost, 改为通过 `_cursor_queue/` 人工触发使用
- 所有本地失败 → 入队, 不再 auto-fallback 云端

## 原策略核心 (历史摘要)

v1 策略主张本地执行 + 云端决策/验收/兜底:
- 批处理: 本地 Ollama 分类, 云端抽样验收
- 决策: 涉及 L3 边界的本地困难样本 → 云端 (Claude Opus)
- 预算: $50/月告警, 按 task_router 分 primary/fallback

## v5 改动一览

| 机制 | v1/v4 | v5 |
|---|---|---|
| 兜底触发 | 自动 | 用户说 "处理 cursor 队列" |
| 兜底执行者 | 直调云 API | Cursor agent |
| 预算 | $50/月 | $0/月 |
| 兜底延迟 | 秒级 | 批处理, 分钟到小时级 |
| 反馈循环 | escalation_dir | `_cursor_queue/*.processed.md` |

## 迁移指南

若你在某文档/代码里引用本文件:
- 人读文档 → 改指向 `cursor-delegated-escalation.md`
- 配置引用 → 参见 `config/task-router.yaml` 的 `on_failure.action: enqueue_cursor`
- PS 脚本 → Phase A3 时整体删除, 无需迁移

---

*内容已被 `cursor-delegated-escalation.md` 完全替代. 本文件仅保留文件存在以避免旧链接失效.*
