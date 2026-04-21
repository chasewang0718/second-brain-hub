# Stage 3 · D4 — `hub-pain` 扫描与归类

- **扫描范围**：`D:\second-brain-content\04-journal\**\*.md`（glob 10 个文件）  
- **匹配**：显式标题 `## hub-pain`、正文 `hub-pain` 标签约定（见 `AGENTS.md` § 语音指令表）  
- **扫描日**：2026-04-21  

## 1. 显式 `hub-pain` 条目（唯一来源块）

| 来源 | 原文摘要 | 归类 | 映射（Stage 3 / 后续） |
|------|----------|------|-------------------------|
| `04-journal/2026-04-21.md` | Phase 0.5：把 Caps+D 当周主捕获路径 | **流程 / 习惯** | **Stage 2** `s2_caps_daily`；非 hub 代码缺陷 |
| 同上 | Caps+D 与重复 AHK 启动脚本冲突 → 已解决 | **已关闭** | 记为 **A** 类历史痛点（环境/脚本），无需新开代码项 |
| 同上 | `ginbox` 见大量非 paste 文件；为验证触发 `gclean` | **数据形态 + 阈值** | **D** 真实 inbox 回归 `s3_d_regression_group`；调参 **A2b** `s3_bug_text_inbox_threshold_tune`；与 **A-config** 已抽阈值（A2a）衔接 |

## 2. 未打 `hub-pain` 但相关的 journal 线索（供 D 扩展）

以下未使用 `hub-pain` 标题，若后续要扩大 D4 覆盖面，可改为在 journal 里统一用 `## hub-pain` 追加一条指针。

| 来源 | 线索 | 建议归类 |
|------|------|----------|
| `2026-04-19.md` | 881 PDF 批处理、断点续传、熔断 | **C/D** 批处理质量与成本，属 **D1** 抽样评估前置 |
| `2026-04-19.md` | ghealth 断链 / frontmatter 缺字段 / 孤儿卡 | **D** 内容质量；非 hub CLI 必修复项 |
| `2026-04-20.md` | 仅 smoke 备忘 | 无 triage 动作 |

## 3. 归类定义（与 ROADMAP Stage 3 字母一致）

| 桶 | 含义 | 本批结论 |
|----|------|----------|
| **A** | 低风险 UX / 配置 / CLI 体验 | 已解决 AHK 冲突记档；`ginbox` 噪声 → A2b + 阈值 yaml |
| **B** | 冷启动与性能 | 当日 journal 已在 `stage-3-b-performance` 记录达标；无新 hub-pain |
| **C** | ask / write 检索与生成质量 | 本批 hub-pain 未涉及 |
| **D** | 真实数据回归（PDF / people / inbox） | `ginbox` 非 paste 堆积 → **D** + **A2b** |
| **E** | Stage 3 总验收 | 见 `architecture/stage3-e-acceptance.md` |

## 4. 建议动作（不写代码，仅路由）

1. **维持习惯**：新 hub 痛点继续按协议写入 `04-journal/YYYY-MM-DD.md` → `## hub-pain`，便于下次 D4 自动化扫描。  
2. **ginbox 噪声**：Stage 2 积累真实样本后跑 **A2b**；必要时在 `thresholds.yaml` 的 `text_inbox` 或（若另有）inbox 展示规则侧加过滤说明。  
3. **无新增代码项**：本批 3 条中 1 条已解、1 条 S2、1 条 D/A2b，**不新增**未计划的 hub 代码 scope。

## 5. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-04-21 | 首版 triage（D4 闭环） |
