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
