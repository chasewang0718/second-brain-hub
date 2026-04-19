# rules/

**人类可读的政策文档**. AI 读来获取行为约束, 人类读来理解系统意图.

## 文件

| 文件 | 作用 |
|---|---|
| `AGENTS.md` | AI 行为总协议 (Cursor / Claude Code / CLI agent 都读) |
| `cloud-local-delegation.md` | **云-本地协作通用策略** (核心!) |
| `privacy.md` | 隐私规则 (敏感字段脱敏, 禁推云端的内容) |
| `content-structure.md` | brain-content 的目录组织约定 |
| `naming-conventions.md` | slug / frontmatter / tags 规范 |
| `inbox-ingest.md` | 收件箱处理流程 |

## 与 config/ 的分工

- **rules/ = 说明性 (explanatory)**: 为什么这样设计, 边界在哪
- **config/ = 声明性 (declarative)**: 具体阈值/枚举/路径

LLM 读 rules/ 理解**意图**, 代码读 config/ 拿**数字**.

## 约定

- 改 AGENTS.md 必须更新 CHANGELOG + 考虑发一条 commit 单独说明
- rules/ 的改动会影响**所有 agent 会话**, 谨慎
