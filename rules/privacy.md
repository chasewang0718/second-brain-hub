# 我的隐私规则（Privacy Rules）

> **📍 权威副本**: `C:\dev-projects\second-brain-hub\rules\privacy.md`
> 镜像: `D:\brain\00-memory\my-privacy-rules.md` (该位置被 `AGENTS.md` 引用为"全域认知层"必读)
> 编辑时优先改 hub 本文件, 手动同步到 `00-memory/my-privacy-rules.md`.

---

> brain 已经从"纯技术仓库"扩展为"全域第二大脑"。
> 什么内容能进 git、什么不能、什么需要特殊处理 —— 都在这里。

---

## 已确认的规则

### ✅ 进主 git 仓（2026-04-19 Chase 决策）

- 人际关系档案（`06-people/` 全部）
- 所有技术内容（`01-concepts/`, `02-snippets/`, `03-projects/`, `04-journal/`, `05-reviews/`）
- 个人认知（`00-memory/` 全部）
- 生活支柱 / 作息 / 健康笔记（`07-life/`）

**理由**：
- GitHub 私有仓，非公开
- 加密、分仓、submodule 的复杂度 > 实际隐私风险
- 便于 AI 完整上下文读取
- 便于跨设备同步

### 🗂️ 三层 Tier 规则（2026-04-19 新增 · 与 AGENTS.md §11 配套）

Chase 已决策**不把任何二进制资产上传到 GitHub**。三层模型：

| Tier | 位置 | 是否上传 GitHub | AI 可见性 |
|---|---|---|---|
| **A** | `D:\brain\` | ✅ 是 | ✅ 全部读写 |
| **B** | `D:\brain-assets\` | ❌ **永远不** | ✅ AI 可读内容生成指针卡 |
| **C** | 由 Chase 自管理 | ❌ 永远不 | ❌ **agent 永远不触碰**（硬红线） |

**Tier C 的硬红线**（L3 级不可逾越）：

1. **agent 不得读 `~/.brain-exclude.txt` 列出的任何路径下的文件内容**（连文件名都不向 LLM 上下文传递）
2. **agent 不得将 Tier C 路径下的内容写入 Tier A 或 Tier B**（防止经 AI "洗白" 后混入）
3. **Tier C 黑名单文件自身不进任何 git 仓**（放在 `C:\Users\chase\.brain-exclude.txt`）
4. **gsave-file / gasset-migrate 等工具启动时必须先检查黑名单**（静默跳过，不在日志/报告里暴露敏感路径）

**Tier B 的约束**：
- 虽然不进 git，但要有备份策略（当前：待配置 rclone 周备份）
- 指针卡（Tier A 里）**不得**在摘要里写出可识别的个人敏感信息（证件号 / 具体金额 / 他人隐私），由 AI 按"写入前自检清单"判断
- 遇到疑似 Tier C 内容落到 Tier B，AI 应标注 `sensitive:true` + 建议 Chase 迁到 Tier C

### 🚫 永远不进 git（强制）

这些无论什么情况都在 `.gitignore`：

- `.env`, `.env.*`, `*.env` — 任何环境变量文件
- `*.key`, `*.pem`, `id_rsa*` — 任何密钥/证书
- `credentials.json`, `service-account*.json` — 服务账号
- `.DS_Store`, `Thumbs.db`, `desktop.ini` — OS 垃圾
- `node_modules/`, `__pycache__/`, `.venv/` — 依赖
- 任何出现 "secret" / "token" / "password" / "api_key" 字样的未加密文件

### 🟡 需要 AI 判断 + Chase 确认

以下情况 AI 要主动问 Chase 一句，不默认写入：

- 具体**财务数字**（收入、存款、具体账户余额）
- **身份证 / 护照 / 银行卡号**等证件信息
- **他人的**敏感信息（对方家庭纠纷、健康问题、感情问题）
- **涉及未成年人**的详细信息
- **未公开的商业机密**（你所在公司的内部数据）
- Chase 明确说过"这个别记"的任何事

**AI 行为**：遇到这类内容，在回复里说"这条我看着像敏感信息，确认进 git 吗？"

---

## 待 Chase 澄清的规则

> *引导问题，慢慢填*

### 财务类
- [ ] MRR / 营收数字 —— 进 git 还是本地 only？
- [ ] 具体银行账户余额 —— 默认不进？
- [ ] 支出追踪 —— 是否想让 brain 管？

### 身份 / 医疗类
- [ ] 体检报告 / 病史 —— 默认 `.gitignore`？
- [ ] 证件照片 —— 默认不进 brain？

### 社交类
- [ ] 和特定人（如前任、家庭冲突对象）的对话 —— 如何处理？
- [ ] 关于雇主的评价 —— 进 journal 但标 private？

### 其他
- [ ] 日记里的"情绪/心理低谷"内容 —— 正常存还是特殊标记？

---

## AI 的写入前自检清单

AI 在往 brain 写入**任何新内容**前，心里过一遍这五条：

1. 这里面有密钥 / 证件号 / 银行账户吗？→ 有 → **拒写**，提醒 Chase 手动处理
2. 这是**他人的**私密信息吗？→ 是 → **问 Chase**
3. 这是具体财务数字吗？→ 是 → **问 Chase**
4. 这段内容如果被公开，Chase 会尴尬吗？→ 可能 → 在 commit 消息里 flag，问 Chase 要不要调整
5. 以上都否 → 直接写

---

## 未来的升级路径

如果哪天真的需要更强隐私，下面是备选方案（目前**不启用**）：

| 需求 | 方案 |
|---|---|
| 某个目录不上传 GitHub | 加入 `.gitignore`（本地 only） |
| 某目录需要加密 | 用 [git-crypt](https://github.com/AGWA/git-crypt) 对特定文件加密 |
| 彻底分仓 | 敏感目录单独建私有仓，用 git submodule 挂载 |
| 端到端加密笔记工具 | 切换到 Logseq + Drive / Obsidian + iCloud（代价：放弃 Cursor 一站式） |

**当前决策**：保持全部进主 git 仓的简洁方案，等真有具体泄露顾虑再升级。

---

## 一句话心智

> **信任默认值：在"对 AI 完全透明"和"对 AI 加密"之间，选透明。因为 AI 的价值 = 上下文的完整性。隐私的代价是：谨慎选择"brain 里放什么"。**

---

*最后更新：*
- *2026-04-19: 由 AI 在 Phase 0 brain 升级中创建。"已确认规则"反映 Chase 2026-04-19 的明确决策；"待澄清"段落是 AI 预留的引导问题。*
- *2026-04-19 (资产管理)：新增"三层 Tier 规则"—— 二进制资产走 Tier B 本地 (`D:\brain-assets\`)；敏感资产走 Tier C (agent 永不触碰，黑名单文件 `~/.brain-exclude.txt`)。*
