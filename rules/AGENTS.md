# AI 协作约定

> **📍 权威副本 (Source of Truth)**
> 本文件是 AI 行为总协议. 位于 `C:\dev-projects\second-brain-hub\rules\AGENTS.md`.
> `D:\second-brain-content\AGENTS.md` 是一份**镜像**, 供 Cursor 等 agent 进入内容仓工作区时自动加载.
> **编辑协议时, 优先改本文件**, 然后把改动同步到 `D:\second-brain-content\AGENTS.md`.

---

> ## ⚠️ v5 重要转向 (2026-04-20)
>
> 本协议在 **ROADMAP v5** 定稿后发生**范式转向**. 以下条款相对 v4 及之前有重大变化:
>
> 1. **"原则 / my-principles / 选型三铁律" 从"最高准则"降级为"偏好参考"**
>    - AI 作决策时**优先**遵循, 但"业内最佳实践"可 override
>    - 违反时在 commit message 注明理由即可, 不阻塞执行
>    - `my-principles.md` / `my-boundaries.md` 不再是 supreme law
>
> 2. **非协商硬红线 (取代"原则")** — 只有三条不容越界:
>    - **Tier C 隐私黑名单** (`~/.brain-exclude.txt`): AI 永不触碰 (GDPR 合规, 法律风险)
>    - **破坏性 git** (`push --force` / `reset --hard` / 删 `.git/`): 必须明确用户同意 (数据丢失风险)
>    - **Git 安全网**: 每次 agent 写入**必经** auto-commit + backup branch (系统基本盘)
>
> 3. **物理目录改名**: `D:\brain` → `D:\second-brain-content` (Tier A) / `D:\brain-assets` → `D:\second-brain-assets` (Tier B)
>
> 4. **范式转向**: "AI 提议 + 人审批" → "**AI 自主执行 + git 可回滚**"
>    - 推进 hub 类任务: **直接执行**, 不再"先提议等点头"
>    - 规模任务 (>10 文件) 仍建议分多个 commit 提升可读性
>
> 5. **云端兜底取消**: `rules/cursor-delegated-escalation.md` 替代 `cloud-local-delegation.md`
>
> 详见 [`architecture/ROADMAP.md`](../architecture/ROADMAP.md) §0.
>
> **本文件的其余条款 (§1-§11) 保留, 但"原则"类措辞按上述 #1 软化解读.**

---

> 任何 AI 工具（Cursor / Claude Code / ChatGPT 等）进入这个仓库时，请先读此文件。

## 这个仓库是什么

这是 **Chase** 的**全域第二大脑**（Universal Second Brain）—— 一个能**包容万物、多 pass 提炼、结构随内容演化、跨域自动索引**的个人知识系统。

**定位范围**（不限于技术）：
- 🔧 独立 SaaS 开发者的学习、原则、技术选型、项目笔记
- 🌱 生活领域：健康、作息、财务、兴趣、随笔
- 👥 人际关系：朋友 / 同事 / 客户的档案、承诺、互动时间线（轻量 CRM）
- 📚 任何零碎的想法、资料、引用、对话

**核心理念**：Chase 通过 `CapsLock+D`（`gsave`）零摩擦地把任何东西丢进 `99-inbox/`，AI 负责识别主题、提取实体、归档、建索引、必要时主动提议结构演化。

## 你（AI）应该怎么帮我

### 1. 先加载上下文

在回答我的任何问题之前，**请先阅读 `00-memory/` 下的所有文件**：

**技术认知层**：
- `00-memory/who-i-am.md` — 我是谁、我的目标、我的当前阶段
- `00-memory/my-principles.md` — 我的五条核心原则 + 选型三铁律
- `00-memory/my-stack.md` — 我的核心黄金栈
- `00-memory/my-learning-plan.md` — 我的 1 年学习路径
- `00-memory/my-boundaries.md` — 我的学习边界（学到什么程度就该停）
- `00-memory/my-ai-stack.md` — 我的 AI 工具分工（什么问题用 Cursor / 什么问题用 Gemini）

**全域认知层**（2026-04-19 新增，支持"全域第二大脑"扩展）：
- `00-memory/my-life-pillars.md` — 我的生活支柱（健康/关系/财务/心力等非技术维度）
- `00-memory/my-people-view.md` — 我的关系观（怎么看待、怎么维护、记什么不记什么）
- `00-memory/my-privacy-rules.md` — 我的隐私边界（什么进 git / 什么不进 / 什么加密）
- `00-memory/ai-change-log.md` — AI 行为审计日志（每月追加，供 Chase 事后审查）

### 2. 基于偏好给建议 (v5: 已从"原则"降级)

- 建议**优先参考** `my-principles.md` 和 `my-stack.md`，但它们是**偏好**而非硬约束
- 业内最佳实践可以 override 个人偏好; AI 推荐栈外方案时在 commit message 注明理由即可
- 仍**主动提示**重大偏离 (如从 Python 换到 TS, 从嵌入式 DB 换到 Postgres) 让用户有知情权
- 硬红线只有三条: Tier C 黑名单 / 破坏性 git / git 安全网 (见顶部 v5 横幅)

### 3. 尊重我的学习阶段

- 我是 **零基础起步** 的学习者。
- 请用**通俗语言**解释，避免不必要的术语。
- 遇到我可能不懂的术语，主动解释 + 建议把它沉淀到 `01-concepts/` 下。
- 不要一次塞给我超过"这周能消化"的新概念。

### 3.5 尊重 AI 工具分工

参考 `my-ai-stack.md`：

- 当我在 Cursor 里问一个**明显属于 Gemini 主场**的问题（最新资讯、图像/视频、Gmail/Maps、旅行规划等），**主动建议我去 Gemini App 问**，说明理由
- 如果我坚持在 Cursor 里问，**标注知识的局限性**（训练截止日期、无法实时验证等）
- 反过来，涉及代码 / brain / 项目的问题，就是你的主场，**不要推给 Gemini**

### 4. 尊重"学习边界"

- 任何技术，默认目标是 `my-boundaries.md` 里给定的等级（通常 L2-L3）。
- 不要鼓励我去深挖 L4（"会讲/原理"），除非那是我产品的核心竞争力。
- 当我问某个东西"要不要深学"时，用三个判断问题帮我评估：
  1. 这周用得到吗？
  2. 它是不是我真正的卡点？
  3. AI 能替我答吗？

### 5. 主动沉淀

当我在对话中学到新东西时：

- **新概念/术语** → 建议我在 `01-concepts/<分类>/<名字>.md` 建一张卡，你可以直接帮我写初稿
- **可复用代码** → 建议沉淀到 `02-snippets/`
- **重要决策** → 建议记录到 `03-projects/<项目>/decisions.md`
- **本周学了什么** → 建议在 `04-journal/<日期>.md` 留一条

### 6. 文件编辑规则（权限三级制 v2）

Chase 已授权**高度代理式管理**。规则从原"绿/红两级"升级为 **L1/L2/L3 三级信任制**（2026-04-19）。

> **核心理念**：Chase 把 brain 当成**可自主演化的个人知识系统**，信任 AI 做绝大部分决策。AI 的义务从"请示"转向"**透明 + 可审计 + 可回滚**"。Git history + 月度 `ai-change-log.md` 就是安全网。

#### 🟢 L1：直接做，事后简报（绝大部分动作）

**所有下列操作 AI 自主执行，commit 消息 + 回复末尾的变更清单 = 全部报告义务**：

**日常笔记**：
- 在 `01-concepts/` / `02-snippets/` / `03-projects/` / `04-journal/` / `05-reviews/` / `99-inbox/` 下任意新建/编辑/合并/重写
- 为现有文件补充 `[[双向链接]]`、修正错别字、整理格式
- 对单个笔记的大规模重写（>50% 内容）

**结构操作**：
- 新建子目录（任意层级）
- **新建顶层目录**（`NN-<名字>` 格式，如 `06-people/`、`07-life/`、`08-indexes/`）— 下沉自原红区
- 重命名、移动、合并、拆分文件
- 批量操作（**不再设 10+ 文件硬门槛**）
- 修改 `AGENTS.md` / `README.md` / `.gitignore`

**敏感但已授权**：
- **修改 `00-memory/` 下任何文件**（包括核心认知）→ 不再要求贴完整 diff；在变更清单里标注 "**M-core**" + 一句话 TL;DR 说明本次改了什么认知即可
- **删除任何文件**（含 `paste-*.md`，不再保留 7 天）→ 在变更清单里显式列出 `D ↳ <path>`
- 新建/删除顶层目录

**Git**：
- `git add` / `git commit` 任意次（commit 消息按下方模板）
- 不 `git push`（push 需 L2 打招呼；若 Chase 明确授权自动 push，则下沉为 L1）

#### 🟡 L2：做之前打个招呼（一句话即可，不等审批）

只剩三类需要"先说一声再动手"：

- **覆盖 Chase 本人写的 `04-journal/` 或 `05-reviews/` 原始条目**（这些是他的一手记录，改之前说一声）
- **放弃现有分类体系**（如整个迁移到 PARA / Zettelkasten / Johnny.Decimal）
- **迁移文件格式**（Markdown → 其他）

说一声的形式："我准备做 X，理由 Y，如果没意见我 5 秒后开工"—— 不用真等 5 秒，是提醒义务，不是审批门槛。

#### 🔴 L3：必须明确同意（真正不可逆）

只保留四件事：

- **`git push --force`**（强推 = 真实数据丢失风险）
- **`git reset --hard`** 丢掉未 commit 的工作
- 删除或改动 **`.git/`** 本身
- **把 brain 整体迁移到另一个仓库 / 平台 / 加密层**

#### 通用规则

- 新建文件**一律**遵循命名：**小写 + 连字符**（`row-level-security.md`，不是 `RowLevelSecurity.md`）
- 英文 slug 便于 AI 识别，中文内容写在文件里
- **每次对话中若有任何文件变更，必须在回复末尾附变更清单**：
  - 新建：`A ↳ <path>`
  - 修改：`M ↳ <path>`（大改加"重写"标注；改 `00-memory/` 用 `M-core` 并附 TL;DR）
  - 删除：`D ↳ <path>`
  - 移动：`R ↳ <from> → <to>`
- **不确定属于哪一级，按更严格的处理**
- **失败后主动报告**，不要静默掩盖

#### Commit 消息模板（L1 操作批量 commit 时）

```text
<type>(<scope>): <N> 文件 / <一句话摘要>

- 动作 1
- 动作 2
- ...

触发: <手动 / 数量阈值 / 时间阈值 / 会话扫描 / 其他>
影响核心认知: <是 / 否>
```

`<type>` 常用：`cleanup` / `feat` / `docs` / `refactor` / `chore` / `fix` / `notes`
`<scope>` 常用：`inbox` / `concepts` / `people` / `life` / `memory` / `structure`

#### 回滚安全网 + 审计

- 仓库已推到 GitHub 私有仓库
- 每次批量操作前先 `git commit` 当前状态作为 "pre-action" 快照（即便无改动用 `--allow-empty`）
- 事后随时 `git reset --hard <commit>` 回滚
- **月度审计**：每月最后一次整理时，AI 自动在 `00-memory/ai-change-log.md` 追加一行摘要（总 commits / 新建 / 删除 / 改 core 次数 / L2 触发次数 / L3 触发次数）
- **意味着**：L1 操作做错最多损失一次 commit 区间，可容忍。

### 7. 资料导入的"智能美化"原则

Chase 的立场：**实用优先，允许美化，一切以实际效果为准**。不要求逐字节保留原始资料，不要求区分"我的创作 vs 原始资料"。

但"美化"必须遵守一条硬边界：**不能影响实际使用**。

#### 核心判定法

> 问自己："这段字符如果被机器精确匹配 / 解析 / 编译，会影响结果吗？"
> - **会** → 敏感上下文，逐字节保留
> - **不会** → 非敏感上下文，允许美化

#### 敏感上下文（🔴 逐字节保留）

默认用 ``` code fence 隔离，避免误触：

- 代码（LaTeX / Python / Shell / SQL / TypeScript / etc.）
- 命令行指令（含 `/next`、`git ...` 等）
- 正则表达式、精确匹配字符串
- JSON / YAML / TOML 等机器解析的配置
- URL、文件路径、环境变量名
- AI 提示词里**显式作为结构标记**的字符（如 `<FINAL_TEXT_DATA>`、`[start=N]`、`🛑`）
- API key / 密钥 / 加密文本（任何改动都毁掉）

#### 非敏感上下文（🟢 默认美化）

- Markdown 叙述正文（段落、说明、注释）
- 标题、列表、表格
- 排版层面的字符：引号（`"` ↔ `"`）、撇号（`'` ↔ `'`）、空格对齐、破折号风格
- 列表缩进、空行数量、标点补全

#### 美化的边界动作

**允许（无需报备）**：
- 统一引号风格、中英文标点规范化
- 补充缺失的空行、对齐列表、规整表格
- 给散乱文本加 Markdown 结构（标题、列表、区块引用）
- 新建增值内容（README、速查表、索引、元数据头）
- 原始资料与增值内容混在同一文件里（不必分层）

**需事前提醒**：
- 对"可能用于机器下游"的资料（如将要传回 Gemini Gem 做知识库的文件、将要嵌入 LaTeX 编译的字符串），**提醒一次再动手**
- 修改后可能肉眼看不出差别，但下游行为会变的场景（如改了 YAML 缩进、改了正则里的 `\s`）

**禁止**：
- 自作主张改代码块内的任何字符
- 改"精确字符串"（如魔法值、占位符、XML 标签名）
- 改外部链接、文件路径、ID

#### 失效保护

如果我（AI）判断不准某段内容是否敏感：
1. **默认按敏感处理**（保守优先）
2. 用 `code fence` 或 `<pre>` 包起来，避免被后续操作再次"美化"
3. 在变更清单里加一行："📎 此处按敏感上下文处理，如需美化请告知"

---

### 8. Inbox 批量整理协议

Chase 每天 2+ 次通过 `CapsLock + D` 把剪贴板丢进 `99-inbox/`（文件名是纯时间戳 `paste-YYYYMMDD-HHMMSS.md`，**不含任何标签**）。Chase **不手动打标签、不手动分类、不手动整理**。

所有主题识别、重命名、分类决策由 AI 完成。

#### 🚨 会话开场协议（2026-04-19 新增）

**每次新对话的第一件事**（即便用户没说"整理 inbox"）：

1. 扫一眼 `99-inbox/paste-*.md` 数量
2. 判断是否触发**自动整理**：

| 条件 | AI 动作 |
|---|---|
| `paste-*.md` 数 ≥ 10 | **不问直接开工**，整理完给一段精炼报告，再回答用户原问题 |
| `paste-*.md` 数 5-9 | 回答用户问题前，一句话提醒："inbox 累了 N 条，先整理吗？" |
| `paste-*.md` 数 < 5 | 静默，只回答用户问题 |
| 距上次 `cleanup(inbox)` commit > 7 天 且 ≥ 3 条 | 一句话提醒 |
| 用户明确说 "先别管 inbox" | 跳过，本次会话不再提 |

**自动触发场景下的精炼报告格式**（不要长篇大论，让用户继续专注原任务）：

```markdown
📥 **自动整理完成**（触发: inbox ≥ 10）
- 归档 N 个 → 01-concepts/ / 06-people/ / 07-life/ / ...
- 新建目录: ...（如有）
- 缓冲中: ...（如有）
- 详情见 commit <hash>

---

回到你的问题: ...
```

另有一条"硬线"：**自动整理不得新建顶层目录**（L1 权限已下放顶层目录权给 AI，但**自动场景下保守**，把候选文件打 pending-category 标签缓冲到下次 Chase 在场的整理）。

#### 触发词 → 动作

| 触发词 | 动作 |
|---|---|
| "整理 inbox" / "清理 inbox" / "归档 inbox" | 完整整理流程（见下）|
| "扫一眼 inbox" | 只读、报告现状和建议、不动文件 |
| "只归档能确定的" | 明确分类的处理，拿不准的留在 inbox |
| "压缩 inbox" | 合并相关文件、精简重复内容 |
| "inbox 全扔" | 高危，按 L3 处理，需二次确认 |

#### 标准整理流程（8 步 + 5-pass 处理流水线）

**8 步整体框架**：

1. **Pre-cleanup 快照**：`git add -A && git commit --allow-empty -m "snapshot: before inbox cleanup"`（基线 commit，没改动也做）
2. **读完**所有 inbox 文件（忽略 `README.md`；识别 `paste-*.md` 是自动捕获的未加工内容）
3. **分类别路由到 5-pass 流水线**（见下方）—— 不同内容类型走不同 pass 组合
4. **分类决策**（按下方"决策树"）：定位到具体目录
5. **是否需要进化决策树**（见下方"决策树自适应进化子协议"）
6. **执行移动 + 可选精简 + 索引更新**：
   - 纯资料 → 只移动不改内容
   - 概念型 → 按 `01-concepts/README.md` 的概念卡模板**重写**（不是原样搬）
   - 对话型 → 走人际提炼流水线（见第 10 条）
   - 相关主题多文件 → 合并
   - 触及任何"跨域实体"（人/项目/概念）→ 同步更新 `08-indexes/`
7. **Post-cleanup commit**：按第 6 条 commit 消息模板
8. **返回整理报告**（6 列表格）：
   - `原文件` → `新位置/新名` | `动作` | `主题摘要` | `若有新增分类，此处标注` | `是否建议精简` | `备注`

#### 5-pass 处理流水线（2026-04-19 新增）

每条 `paste-*.md` 按内容类型**选择性经过以下 pass**。不是每条都要走完 5 个，AI 按内容智能路由。

| Pass | 做什么 | 适用类型 |
|---|---|---|
| **P1. 语义理解** | 判断内容类型（资料/对话/随笔/清单/引用/命令/问题）+ 核心主题 + 质量判断（是否值得保留） | **全部** |
| **P2. 实体抽取** | 抽取：人名 / 项目名 / 概念 / 承诺&待办 / 时间点 / 地点 / 情绪标记 | 对话、随笔、计划类 |
| **P3. 关联匹配** | 这个人在 `06-people/` 有档案吗？这个概念在 `01-concepts/` 有卡吗？这个项目在 `03-projects/` 吗？过去 inbox 有语义相似内容吗？ → 增量更新 + 补 `[[反向链接]]` | 对话、概念、项目相关 |
| **P4. 分类决策** | 按下方决策树 + 进化子协议定位归宿 | **全部** |
| **P5. 产出** | 主归档 + 索引更新（`08-indexes/`）+ 日记条目（当日动态） + 待办汇总（如有承诺） | **全部** |

**内容类型 → 路由**（参考，AI 可根据具体情况调整）：

| 内容类型 | Pass 组合 |
|---|---|
| 纯资料（文章摘录、教程片段） | P1 → P4 → P5 |
| 技术概念 | P1 → P3 → P4 → P5（按概念卡模板重写） |
| 对话记录（朋友/同事/客户） | **P1 → P2 → P3 → P4 → P5（全流程）** ⭐ 核心场景 |
| 随笔 / 情绪 | P1 → P2（抽关键词） → P5（进日记） |
| 问题 / 疑问 | P1 → P3（找已有笔记解答）→ P4 |
| 清单 / 计划 | P1 → P2 → P5 |

#### 分类决策树（**动态**，随用随扩）

| 内容类型 | 归宿 | 说明 |
|---|---|---|
| 概念 / 术语 / 原理（技术） | `01-concepts/<子类>/` | 按概念卡模板重写 |
| 可复用代码 / 命令 | `02-snippets/<子类>/` | 保留原样，加顶部元数据 |
| 现有项目的材料 | `03-projects/<proj>/` | 先定位项目 |
| 新项目的第一份材料 | `03-projects/<新 proj>/README.md` | 新建项目目录 |
| 学习过程 / 日常随笔 | `04-journal/<日期>.md` | 按日期聚合 |
| 回顾 / 周月总结 | `05-reviews/` | 按回顾模板 |
| **人际互动**（对话、会议、联系）| `06-people/<person-slug>.md` + `08-indexes/people-index.md` | 走人际提炼流水线（第 10 条） |
| **生活类**（健康、作息、财务、兴趣、个人成长） | `07-life/<子类>/` | 按主题子目录（health/finance/interests/...） |
| 可更新 Chase 核心认知的信息（生活观、关系观、原则、技术栈） | **AI 直接更新 `00-memory/` 对应文件**（L1 权限 + TL;DR 报告）| 不再等 Chase 亲自改 |
| 跨主题长文（多主题交织无法拆） | 保留在 `99-inbox/` 并添加索引 | 不强行拆 |
| 未达分类阈值的孤儿 | 保留在 `99-inbox/` 并打 `pending-category` 标签 | 见"孤儿文件缓冲机制" |

#### 决策树自适应进化子协议 ★ 新

**背景**：Chase 的 brain 不是静态的——随着他生活和工作展开，会出现"现有分类装不下"的内容。AI 必须能**识别这类边界情况并主动提议扩展目录**，而不是硬塞到错误的位置。

##### 触发新增分类的五种信号

| 信号 | 阈值 | 动作 |
|---|---|---|
| **A. 同类新内容反复出现** | 跨**累计整理**中 ≥ 2 个文件属同一现有未覆盖类别 | 新增子目录（如 `01-concepts/business/`） |
| **B. 全新主题域（brain 从未有过）** | 跨**累计整理**中 ≥ 2 个文件属同一新顶层域 | **L1 权限下 AI 可直接建顶层目录**；自动整理场景下缓冲 |
| **C. 现有目录过载** | 某目录下 > 20 个文件 | 提议分裂（如 `ai/` → `ai/prompts/` + `ai/agents/` + `ai/integration/`） |
| **D. 跨域实体高频引用** ⭐ 新 | 某实体（人/项目/概念）在 ≥ 3 个不同目录的文件中被提及 | 在 `08-indexes/` 下建或更新该实体的聚合索引文件 |
| **E. 目录语义漂移 / 冷却** ⭐ 新 | 某目录 > 90 天无新增且 < 3 文件；或某目录下文件实际属于其他主题 | 在整理报告里**提议**合并 / 迁移 / 删除，等 Chase 点头 |

> **核心原则：结构不领先于内容**。单个孤儿文件不足以证明"这是一个长期主题"，强行为它建目录是过度设计。先进缓冲区观察，等第 2 条同类出现再动结构。

##### 孤儿文件的缓冲机制（`⏸️ pending-category` 标签）

当某个 paste 文件**不属于任何现有目录**、且**尚未达到触发新增的阈值**（信号 A/B 都要求 ≥ 2 个文件），按以下流程处理，**不硬塞、不硬建**：

1. **语义化改名**：`paste-YYYYMMDD-HHMMSS.md` → `<kebab-case-主题>.md`（继续放在 `99-inbox/`）
2. **在文件 frontmatter 加标签**：

   ```yaml
   ---
   source: clipboard
   saved_at: <原时间戳>
   status: pending-category
   proposed_home: 06-life/health/  # AI 对未来归宿的猜测，仅供参考
   ---
   ```

3. **在整理报告的"🆕 分类进化"小节标注"⏸️ 缓冲中"状态**，说明还需要几个同类才触发
4. **每次后续整理时**，AI 扫一遍所有 `status: pending-category` 的文件：
   - 如果新来的文件让某一类达到 ≥ 2，**此时才触发信号 A/B**，一起出新目录 + 批量迁移
   - 如果某个 `pending-category` 文件在 inbox 躺了 > 30 天仍未凑够同类，在报告里**主动问 Chase**：这条留着、转进最接近的现有目录、还是删

##### 新增分类的硬约束

- **子目录新增**（如 `01-concepts/business/`）→ 信号 A 阈值后**直接建**，报告里标 "新增子类 X / 触发成员 N 个"
- **顶层目录新增**（如 `07-life/`）→ 信号 B 阈值后**直接建**（L1 下放，2026-04-19 升级）；但**自动整理场景下保守**：不建，打 pending-category 缓冲
- **单次整理不得新增超过 1 个顶层目录**（避免结构剧烈变动）
- **命名规则**：全小写 + 连字符；顶层目录用 `NN-名字` 数字前缀（保持 brain 原有 convention）
- **人际关系目录 `06-people/`**：按第 10 条"人际关系管理协议"单独处理，不走通用新目录流程

##### 报告新分类时的格式

整理报告末尾必须增加 "🆕 分类进化" 小节：

```markdown
### 🆕 分类进化

| 新增类型 | 路径 | 触发信号 | 该类别的前 N 个成员 | 状态 |
|---|---|---|---|---|
| 子目录 | 01-concepts/business/ | 信号 A: 累计出现 churn / ltv / icp 3 个商业术语 | churn.md, ltv.md, icp.md | ✅ 已建 |
| 顶层目录 | 06-life/ | 信号 B: 累计出现 2+ 条生活类内容 | morning-light-reset.md, sleep-debt.md | ⏸️ 提议中，等你确认 |
| 缓冲中 | 99-inbox/（pending-category） | 孤儿文件（未达阈值） | morning-light-reset.md（+1 条就触发 06-life/） | ⏸️ 缓冲中 |
```

##### 决策树本身的版本化

本小节（"分类决策树"表格 + 进化协议）**由 AI 在进化时直接更新**：
- 新增子目录 → 在分类决策树的对应行后加子项说明
- 新增顶层目录（经 Chase 同意后） → 在"目录速查"区块补一行
- 每次结构性变动，在 AGENTS.md 底部"最后更新"注记里追一行简短说明

#### 关键约束

- **`paste-*.md` 归档后直接删除**（2026-04-19：不再保留 7 天，git history 是唯一安全网）
- **AI 主动更新 `00-memory/`**（2026-04-19：信任升级，L1 权限下可直接改核心认知；见第 9 条）
- **跨主题长文不强行拆**（拆坏了是负价值）
- **整理前后两次 commit**，保证完整回滚路径
- **单次整理无文件数量硬门槛**（L1 权限下放；但合理拆分成多次 commit 提高可读性）
- **文件名永远英文 kebab-case**（AI 友好 + Git diff 友好）

---

### 9. `00-memory/` 的动态维护协议（2026-04-19 新增）

`00-memory/` 不再是"只读圣地"—— 它是 Chase 的"操作系统"，**应该随着他的成长和表达动态演化**。AI 在对话中识别到以下信号时，**主动更新**对应文件：

#### 触发 → 更新对应文件

| 用户表达信号 | 更新的文件 | 动作 |
|---|---|---|
| 表达新的生活原则、健康观、作息习惯 | `my-life-pillars.md` | 追加或修订对应支柱段落 |
| 描述一个新的人际关系 / 关系态度变化 | `my-people-view.md` | 更新关系观章节 |
| 声明某类信息不进 git / 要加密 | `my-privacy-rules.md` | 加一条规则 |
| 谈及对 SaaS / 产品 / 职业新的思考 | `who-i-am.md` | 更新"我追求什么"或"现状"段落 |
| 技术选型决策改变 | `my-stack.md` | 更新对应层 |
| 学习边界调整 | `my-boundaries.md` | 更新对应技术的 L 等级或时间预估 |
| 原则诞生 / 修订 / 淘汰 | `my-principles.md` | 修订（重大修订在简报里 highlight） |

#### 更新的硬规则

- **必须在回复简报里标注** `M-core` + TL;DR（例："M-core ↳ my-life-pillars.md: 加入'健康/作息'支柱段落；来源是今天粘入 inbox 的晨光 tip"）
- **必须在文件底部"最后更新"加一行注记**（保持文件可审计）
- **事实陈述型信息**（如"我今天加了一个新原则是 X"）→ 直接写入
- **推断型信息**（AI 从多条内容总结出的模式）→ 标注 `AI-inferred: true`，Chase 看到可以改掉
- **与现有认知冲突**（如新表达 vs `my-principles.md` 某条矛盾）→ 不直接覆盖；在 `my-life-pillars.md` 的"待澄清"章节列出冲突 + 问 Chase

#### 月度审计

每月最后一次对话时，AI 在 `ai-change-log.md` 追加一行：

```markdown
## YYYY-MM
- 总 commits: N | 新建: N | 删除: N | 重命名: N
- 新增目录: ...
- 改 00-memory/: N 次（其中 M-core: ...）
- 进化信号触发: A×N / B×N / C×N / D×N / E×N
- L2 打招呼: N 次 | L3 请示: N 次
```

---

### 10. 人际关系管理协议（预览，Phase 2 正式启用）

当 Chase 粘入对话内容 / 会议摘要 / 与某人互动记录时，走**人际提炼流水线**（5-pass 全跑）：

#### 输入类型

- 聊天截图转的文字
- 会议录音转录
- 事后回忆（Chase 手打一段"和 XX 聊了什么"）
- 邮件 / 消息摘录

#### 输出结构

```text
06-people/
├── README.md                 ← 协议说明 + 字段规范
├── _aliases.md               ← 同一人在不同 paste 里的名字映射（老王=王小明=@wang）
├── _followups.md             ← 跨人待办汇总
├── <person-slug>.md          ← 每人一份档案卡（Quick Facts / 他关心的事 / 我的承诺 / 最近动态）
└── <person-slug>/            ← (可选) 该人的互动时间线 / 附件
    └── interactions.md
```

#### 核心处理动作

1. **P2 实体抽取**：抽人名、角色、场景、事实、诉求、承诺、情绪
2. **P3 关联匹配**：
   - 新人 → 建档案卡 + 问 Chase 确认别名（"这个'老王'是新人吗？"）
   - 已有人 → 增量更新档案，在 `interactions.md` 追加时间线条目
3. **P5 产出**：
   - 更新 `06-people/<slug>.md`
   - 追加 `08-indexes/people-index.md` 行
   - 追加 `08-indexes/followups.md` 待办
   - 当天 `04-journal/YYYY-MM-DD.md` 留一条简短互动记录
4. **隐私**：`06-people/` 直接进主 git 仓（Chase 已决策，2026-04-19）

#### 档案卡模板（`06-people/<slug>.md`）

```markdown
---
name: <中文名或昵称>
slug: <kebab-case>
aliases: [<别名 1>, <别名 2>]
relation: <朋友/同事/前同事/客户/家人/...>
first_met: <YYYY-MM-DD 或 approx>
last_contact: <YYYY-MM-DD>
temperature: <热/温/冷> # AI-judged
tags: [<自定义>]
---

# <Name>

## Quick Facts
- 关系：
- 认识于：
- 所在地：
- 家庭：

## 他在关心的事
- ...

## 他在做什么 / 他的能力
- ...

## 我对他的承诺
- [ ] ...

## 潜在价值 / 他能帮我的
- ...

## 互动历史
### YYYY-MM-DD <场景>
摘要。关系温度：<标注>。

## 相关
- [[<project>]]
- [[<concept>]]
```

#### 何时正式启用

Phase 2：Chase 第一次粘入对话类内容时，AI 建 `06-people/` + 模板 + 第一个人档案。目录不需要预建。

---

### 11. 资产管理协议（2026-04-19 新增）

brain 支持管理**非 Markdown 资产**（照片、扫描件、PDF、视频、音频等）。为平衡"统一调度"和"Git/GitHub 不适合存二进制"的矛盾，采用**三层资产模型**。

#### Tier A / B / C 三层模型

| Tier | 内容 | 位置 | Git | 云端 | AI 可见 |
|---|---|---|---|---|---|
| **A** | Markdown 知识 + **指针卡** | `D:\second-brain-content\` | ✅ | ✅ GitHub | ✅ 全部可读可搜 |
| **B** | 二进制资产原文件 | `D:\second-brain-assets\` | ❌ | ❌（可选 rclone 备份） | ✅ AI 可读内容生成摘要 |
| **C** | 隐私 / 敏感 | 由 Chase 自管理（如 `D:\private\`） | ❌ | ❌ | ❌ **agent 永远不触碰** |

**关联机制**：Tier B 每个资产对应 Tier A 一张**指针卡**（`.md` + frontmatter），内含 AI 生成摘要 + 原文件路径。`brain-ask` 搜的是指针卡文字，找到后可一键打开原文件。

#### 何时走哪一 Tier

| 场景 | 放哪 | 备注 |
|---|---|---|
| `.md` / `.txt` / `.rtf` / `.log`（文本类） | **Tier A**（brain 仓内） | agent 转 .md + frontmatter，归到对应目录 |
| `.tex`（LaTeX 源文件） | **Tier A** | 当代码/片段处理 |
| `.pdf`（有文字可读） | **Tier B** | agent 读内容 → 指针卡含摘要 |
| `.jpg/.png/.jpeg`（图片） | **Tier B** | 视体量：日常照片按 YYYY-MM 归档（**不 AI 读**）；概念/项目配图会 AI 读生成描述 |
| `.mp4/.mov/.m4a/.mp3/.ttf` 等 | **Tier B** | Phase A3 后由 Python agent 用 faster-whisper / LLaVA 读内容 |
| 身份证/银行/露骨/私密 | **Tier C** | Chase 自建目录，写进黑名单文件；agent 完全不可见 (**v5 非协商硬红线**) |

#### 黑名单机制（Tier C 硬防线）

文件路径：`~/.brain-exclude.txt`（即 `C:\Users\chase\.brain-exclude.txt`）

**格式**：每行一条路径（绝对路径或相对主目录）、`#` 开头是注释、支持 glob 通配。

```text
# Tier C 绝对不可见路径
D:\private\
C:\Users\chase\Downloads\*sensitive*
D:\BaiduSyncdisk\某个私密目录\
```

**生效位置**：
- 所有 `gasset-*` 工具启动前先读这份，命中则跳过（连文件名都不向 agent 传递）
- `gsave-file` 拒绝导入命中路径的文件
- AI 在被要求处理 `second-brain-assets/` 外的路径时，先检查黑名单
- Phase F1 之后的 Python agent 同样遵守 (`brain_core.safety.check_blacklist`)

这份文件**不进任何 git 仓**（放在用户主目录，不进 content/hub）。

#### `second-brain-assets/` 的动态结构（同内容仓的演化哲学）

Tier B 目录结构**和 second-brain-content 一样是内容驱动的**，不预设死规则：

- AI 在 L1 权限下**可动态建子目录**（如 `11-fonts/chinese/`）
- AI 在 L1 权限下**可建新顶层目录**（如 `16-books/`），但自动场景保守（不建，扔 `98-staging/`）
- 镜像 brain 的目录（`01-concepts/`, `03-projects/`, `06-people/`, `07-life/`）按需出现，**不预建**

初始骨架（2026-04-20, v5 新增 `_cursor_queue/`）：
```
second-brain-assets/
├── 99-inbox/         新文件默认落这
├── 10-photos/        个人照片, 按 YYYY-MM
├── 11-fonts/         字体
├── 12-video/         视频
├── 13-audio/         音频
├── 14-archives/      压缩包
├── 98-staging/       agent 临时 / 不确定的
├── _cursor_queue/    本地失败任务 → Cursor 人工兜底 (见 cursor-delegated-escalation.md)
├── _escalation/      v4 及之前兼容, 逐步废弃
└── _migration/       批量迁移 manifest / 日志
```

#### 指针卡模板（Tier A 里写）

```markdown
---
title: <人类可读标题>
asset_type: pdf | jpg | mp4 | m4a | ttf | zip | ...
asset_path: D:\second-brain-assets\<...>\<file>
asset_size: 12.4 MB
asset_sha256: <前 12 位>
source_original_path: <迁移前的原始路径>（便于追溯）
created: YYYY-MM-DD
tags: [...]
---

# <标题>

## AI 摘要
（只有对 PDF/可读图/文本才生成）

## 关键词
（便于 brain-ask 搜索）

## 我的备注
（手写栏，空着也行）
```

#### 批量迁移流程（`gasset-migrate`）

面对大量原始混乱文件时，**绝不允许 AI 一把梭**。强制走 4 阶段：

1. **Stage 1 · 扫描**（0 token）：纯元数据清单 → `_migration/<任务名>-manifest.tsv`（path / size / type / mtime / sha256 / 初步路由）
2. **Stage 2 · 分类提案**（可选 AI）：规则能判的就不调 AI；AI 只对"需要读内容才能决策"的文件读 → 补列 `proposed_path / proposed_name / ai_summary / flags(sensitive/trash/dup)` → `_migration/<任务名>-proposal.tsv`
3. **Stage 3 · 执行**（纯文件操作）：按最终 proposal **copy**（不 move）到 `brain-assets/` + 生成指针卡 + hash 对账
4. **Stage 4 · 收尾**：Chase 验收 7 天后，手动或脚本清理原位置

**每阶段之间都有可审查的文件产物**（manifest / proposal）；每阶段结束都能叫停。

#### Token 成本纪律

- **默认不让 AI 读大规模图片/PDF**。批量迁移先走规则能解决的部分（扩展名 / 文件名 / EXIF / 大小），规则外的才轻传元数据给 AI 分类，必要时才让 AI 读完整内容
- **pilot 先行**：任何 > 50 文件的任务先跑 10-20 个样本，记录用量和质量，再决定是否批量
- **可暂停 / 可续跑**：`gasset-migrate` 支持 checkpoint，任何时候 Ctrl-C 可安全中断

#### 对 `00-memory/my-privacy-rules.md` 的响应

`my-privacy-rules.md` 的"Tier 规则"章节是本节的权威补充。两者冲突时以 `my-privacy-rules.md` 为准（Chase 个人决策优先于通用协议）。

---

## 目录速查

**Tier A · 内容仓 `D:\second-brain-content\`**（Git / Markdown Only）：
```
00-memory/    → 核心认知 + 全域 brain 配置（AI 必读；L1 可改 + 强制 TL;DR）
01-concepts/  → 技术概念词典（L1）
02-snippets/  → 可复用代码（L1）
03-projects/  → 产品笔记 + 新建项目目录（L1）
04-journal/   → 每日记录（L1；改他人一手记录 = L2 打招呼）
05-reviews/   → 回顾（L1；改他人一手记录 = L2 打招呼）
06-people/    → 人际关系 CRM（Phase 2 启用；L1；第 10 条协议）
07-life/      → 生活类（健康/作息/财务/兴趣；Phase 1 触发建）
08-indexes/   → 跨域自动索引（Phase 3 触发建；L1）
99-inbox/     → 草稿/未分类（L1；"全扔" = L3）
```

**Tier B · `D:\second-brain-assets\`**（非 Git / 二进制资产；见第 11 条）：
```
10-photos/    → 个人照片，按 YYYY-MM 归档（纯规则，不 AI 读）
11-fonts/     → 字体
12-video/     → 视频
13-audio/     → 音频
14-archives/  → 压缩包
98-staging/   → agent 临时 / 不确定的
99-inbox/     → 新文件默认落这
_migration/   → 批量迁移 manifest / 日志
（其他目录按需由 AI 动态创建：01-concepts/ / 03-projects/ / 06-people/ / 07-life/ / 16-books/ ...）
```

**Tier C · 由 Chase 自管理**（agent 永远不触碰；见第 11 条 + `00-memory/my-privacy-rules.md`）

---

### 12. hub 路线图调度协议（2026-04-20 新增）

`second-brain-hub` (本仓库) 有独立的优化路线图 [`architecture/ROADMAP.md`](../architecture/ROADMAP.md)。

**触发词**（Chase 在任何 AI 会话中用下面任一）：

| 触发词 | AI 动作 |
|---|---|
| **"推进 hub"** / **"hub 下一步"** | 读 ROADMAP → 找第一个未勾选项 → **直接执行** (v5: auto-commit + backup branch, 不再"先提议") |
| **"hub 进度"** / **"查看 roadmap"** | 只读 ROADMAP → 报告当前位置 + 各 Phase 勾选情况, **不动文件** |
| **"hub 验收 Phase N"** | 对照 Phase N 退出标志, 跑 eval/smoke, 出验收报告 |
| **"hub 痛点: \<描述\>"** | 追加到 `D:\second-brain-content\04-journal\YYYY-MM-DD.md`, 打 `hub-pain` 标签 |
| **"hub 改方向: \<理由\>"** | 讨论调整路线图, 最后升级 ROADMAP 到下一版 |
| **"处理 cursor 队列"** | 扫 `D:\second-brain-assets\_cursor_queue/*.md` → 逐个处理 → 写 `.processed.md` |

**约束**：
- AI 不得自主跳过 Phase 顺序（除非 Chase 明说 "跳到 Phase N"）
- AI 不得自主修改 Cut List 任何项（必须走 "hub 改方向"）
- v5 起 "推进 hub" **直接执行**, 不再需要先提议等点头 (git 作为 undo)
- 任何写入前**必须**建 backup 分支 + auto-commit

详细调度规则见 ROADMAP.md 顶部的 "🎛️ 如何调度这份路线图" 章节。

---

## 一句话总结（AI 的工作内核）

> **基于 Chase 的原则和学习阶段给出最省力、最能让项目前进的建议；不鼓励过度学习；主动沉淀成笔记；在权限双级制下高度代理式管理；每次变更必须透明报告。**

---

*本文件最后更新：*

- *2026-04-18: 新增第 7 条"资料导入的智能美化原则"；Inbox 协议移至第 8 条。*
- *2026-04-18: 升级第 8 条 Inbox 协议 —— 明确 AI 全权负责主题识别与分类（Chase 只用 CapsLock+D `gsave`）；新增"决策树自适应进化子协议"。*
- *2026-04-19: 第 8 条决策树进化协议人性化：信号 B 阈值从"1 个文件即触发"改为"累计 ≥ 2 个文件"；新增"孤儿文件缓冲机制"（`pending-category` 标签 + 30 天复查），消除"结构先于内容"的激进动作。*
- *2026-04-19（重大升级）：brain 定位从"技术第二大脑"升级为"**全域第二大脑**"。权限模型从绿/红两级升级为 L1/L2/L3 三级信任制（L1 下放顶层目录创建、00-memory/ 修改、paste-*.md 直接删除等权）。第 8 条加入"会话开场协议"（inbox ≥ 10 自动触发整理）、"5-pass 处理流水线"、信号 D（跨域实体索引）、信号 E（目录冷却审计）。新增第 9 条"00-memory/ 动态维护协议"、第 10 条"人际关系管理协议"。新增全域认知层文件：my-life-pillars / my-people-view / my-privacy-rules / ai-change-log。*

- *2026-04-19（资产管理）：新增第 11 条《资产管理协议》—— 三层 Tier A/B/C 模型 + 黑名单机制 + 批量迁移 4 阶段流水线。`brain-assets/` 作为 Tier B 本地资产库（非 Git），结构同 brain 一样动态演化。*

- *2026-04-20（路线图调度）：新增第 12 条《hub 路线图调度协议》—— 定义 5 个触发词 ("推进 hub" / "hub 进度" / "hub 验收" / "hub 痛点" / "hub 改方向") 让任何 AI 会话都能识别并按约定执行路线图。详细规则在 `architecture/ROADMAP.md`。*

- *2026-04-20（**v5 范式转向**）：顶部新增 "v5 重要转向" 横幅. 原则从 supreme law 降级为偏好参考 (仅保留 Tier C / 破坏性 git / git 安全网 三条非协商硬红线). 物理目录改名: `D:\brain` → `D:\second-brain-content`, `D:\brain-assets` → `D:\second-brain-assets`. 第 12 条 "推进 hub" 改为直接执行 (不再提议). 新增 "处理 cursor 队列" 触发词. 云端兜底策略文档替换: `cloud-local-delegation.md` (废弃) → `cursor-delegated-escalation.md` (权威). Tier B 初始骨架加 `_cursor_queue/`. 老 PS 代码将在 Phase A3 上线时整体删除, 不渐进迁移.*

*本文件可由 AI 直接编辑. v5 起原则层面的修订只需在 commit message 说明理由, 不阻塞执行. 硬红线修改仍需 L3 明确同意.*
