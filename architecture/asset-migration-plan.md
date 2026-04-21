---
title: tools/asset/ · PowerShell → Python 迁移评估
status: plan
created: 2026-04-21
authoritative_at: C:\dev-projects\second-brain-hub\architecture\asset-migration-plan.md
---

# `tools/asset/` 迁移评估（不动代码，只产计划）

## 为什么现在写这份文档

A3 收尾已经删掉了 `tools/ollama-pipeline/`、`tools/lib/`、`tools/feedback/`、
一个老 watchdog（共 12 个 PS / ~105 KB）。剩下唯一还"有活人在用"的 PS 分组
就是 `tools/asset/`——通过 `.reference` profile 的 `gasset` / `gasset-scan` /
`gasset-migrate` 三个函数，用户仍在日常调用。

但 `.reference` 里对 `brain-asset-migrate.ps1` 的路径写的是旧路径
`powershell\brain-asset-migrate.ps1`（实际文件已在 `tools\asset\`）——说明这
一块也处在"半悬空"状态，需要一轮正式评估。**本文档只产计划，不动代码。**

## 范围

`tools/asset/*.ps1` 共 5 个文件：

| 文件 | 大小 | 作用 |
|---|---:|---|
| `brain-asset-migrate.ps1` | 16.3 KB | 外部资产 → `D:\second-brain-assets\` 分类入库。DryRun/Execute/Verify 三模式，按扩展名分 10-photos / 12-video / 13-audio / 11-fonts / 14-archives / inbox 等。 |
| `brain-asset-source-cleanup.ps1` | 8.1 KB | 按 manifest 删 `D:\BaiduSyncdisk\` 里已成功 copy 的源文件，带 7 天延迟 + 三重安全检查（大小/存在/未动）。 |
| `brain-asset-dedup.ps1` | 6.1 KB | SHA256 扫 `brain-assets` 找重复文件，写 `dedup-YYYY-MM-DD.tsv`。永远 dry-run，不删。 |
| `brain-asset-stats.ps1` | 5.3 KB | 统计分布（目录/扩展名/时间线/top 10 大文件）→ `04-journal/brain-assets-stats-YYYY-MM-DD.md`。0 token。 |
| `brain-asset-overview-cards.ps1` | 5.5 KB | 给叶节点目录生成 Tier A `overview.md`（过去走 cursor-agent，烧 token）。 |

全部入口都是本地 PS，不依赖已删除的 `tools/lib/`（亲手核对过）。

## 现状对照

| 功能 | 当前 PS | 已有 Python 对等 | 覆盖率 |
|---|---|---|---:|
| 资产统计 | `brain-asset-stats.ps1` | `brain_agents/ask.py` 可查 `inbox/`，但没有"按 ext / 按时间线统计 `D:\second-brain-assets\`"的专用函数 | ~10% |
| 资产入库 | `brain-asset-migrate.ps1` | `brain_agents/file_inbox.py` + `image_inbox.py` + `audio_inbox.py` 覆盖 PDF / 图 / 音频 **进 inbox**；但"从外部目录扫描 + 按扩展名分类 + 进 assets 树"这一段没有 | ~30%（仅 inbox 这一侧） |
| 源端清理 | `brain-asset-source-cleanup.ps1` | 无 | 0% |
| 去重扫描 | `brain-asset-dedup.ps1` | 无 | 0% |
| 叶目录概览 | `brain-asset-overview-cards.ps1` | `brain_agents/write_assist.py` 可本地生成文档 | ~60%（核心能力在，没专门的批量入口） |

## 风险评估（不动代码时先看清楚）

### 1. `brain-asset-migrate.ps1`（高价值、已在用）
- **风险**：用户 profile 里的 `gasset-scan/gasset-migrate` 直接调这个，profile 里路径还是错的（`powershell\brain-asset-migrate.ps1`），说明真跑一次立刻就会 `Test-Path` 失败报 `❌ 找不到`。但用户没抱怨——意味着**大概率已经不再日常使用**。
- **验证方法**：运行一次 `gasset-scan 'D:\some\path'`，看是否报错。
- **迁移工作量**：大。文件分类规则（扩展名→目标目录、按 mtime/EXIF 分月）、manifest 格式、三模式（dry/execute/verify）都要移植。估算 ~1 天。

### 2. `brain-asset-source-cleanup.ps1`（低频、有安全边界）
- **风险**：这是"真删源文件"的动作。当前以 Task Scheduler 触发（2026-04-26 注释）。是否仍注册、是否仍在跑，不确定。
- **验证方法**：`Get-ScheduledTask | ? TaskName -like '*asset*cleanup*'` 看任务状态。
- **迁移工作量**：中。核心逻辑是三重校验 + 删除；Python 用 `pathlib` + `hashlib` 可完整复现。估算 ~半天。
- **安全**：迁移后**保留并行期 2 周**，Python 版默认 `--dry-run`，观察两轮都无差异再切。

### 3. `brain-asset-dedup.ps1`（纯只读、低频）
- **风险**：最低。输出只是 TSV 报告，从不删文件。
- **迁移工作量**：小。`os.walk` + `hashlib.sha256` + `pandas`/`csv` 即可。估算 ~2 小时。
- **时机**：可作为 Python 迁移的第一刀，建立模式。

### 4. `brain-asset-stats.ps1`（纯只读、高频率被引用）
- **风险**：最低。写 `04-journal/` 目录一个 md 报告。
- **迁移工作量**：小。~2 小时，和 dedup 一起做。
- **产物对接**：Python 版本自然可以顺便写 `telemetry_logs_dir/asset-stats-YYYY-MM-DD.json`，方便后续 `brain ask "资产有多少"` 直接查。

### 5. `brain-asset-overview-cards.ps1`（过去烧 token，已被本地化路径绕开）
- **风险**：低。过去 dry-run 默认，`-Execute` 才启 cursor-agent。
- **结论**：**建议直接删除**。`brain_agents/write_assist.py` 已经能本地生成文档；批量化这件事没有强需求。若之后要做"自动给每个资产簇写一段描述"，应重新设计（走本地 LLM + 写 asset-pointer frontmatter）而不是复活这个脚本。

## 推荐迁移顺序（按风险从低到高）

| 批次 | 迁移项 | 产出 Python 模块 | 预计工时 | 风险 |
|---:|---|---|---:|---|
| B1 | ✅ `brain-asset-stats.ps1` → `brain_agents/asset_stats.py` + CLI `brain asset-stats` (ec3d0e1) | | 2h | 低 |
| B1 | ✅ `brain-asset-dedup.ps1` → `brain_agents/asset_dedup.py` + CLI `brain asset-dedup` (95cdac4) | | 2h | 低 |
| B2 | ✅ `brain-asset-overview-cards.ps1` **已删除**（不迁移） | | 10m | 低 |
| B3 | ✅ `brain-asset-migrate.ps1` → `brain_agents/asset_migrate.py` + CLI `brain asset-scan` + `brain asset-migrate-execute` | | 1d | 中 |
| B4 | `brain-asset-source-cleanup.ps1` | `brain_agents/asset_source_cleanup.py` + CLI | 4h | 中（删源） |
| B5 | 清理 `.reference` profile 的 `gasset-*` 函数，改调 Python CLI | 修 `Microsoft.PowerShell_profile.ps1.reference` | 30m | 低 |
| B6 | 删除 `tools/asset/*.ps1` + 本计划 | 彻底收尾 | 10m | 低 |

**总计**：~2 个工日，分 6 批推进。每批一次 commit，每批后有 rollback 空间。

## 中间态约定（迁移期）

B3 后，PS `brain-asset-migrate.ps1` **保留** 继续可用；Python 版通过
`brain asset-scan` + `brain asset-migrate-execute` 暴露同一流程。**并跑
对拍 3 周**再做 B6 删除。对拍维度：

- 扫描文件总数一致
- 每类（photos / video / audio / fonts / archives / inbox / trash）命中数一致
- 目标路径一致（分月粒度）
- 只允许差异：
  - Python 默认扫到 `.tiff`/`.webp`，PS 只扫 `.jpg/.jpeg/.png/.gif/.bmp/.heic`
    （已在 Python 层显式扩充，符合"新增支持"条）
  - Python 的 exclude 规则比 PS 宽（substring + startswith），PS 只 startswith
    + wildcard；遇到差异优先以 Python 为准（更保守 = 更多排除）

对拍办法：同一源目录分别跑 PS `-DryRun` 和 `brain asset-scan`，diff 两份
manifest 的 `source_path + rule + target_dir` 列。

通过之后再做 B6 删除。

## 绝对不做的事

- ❌ 不在 B3 完成前改用户 profile 里的 `gasset-*`
- ❌ 不在 B4 完成前注销 Task Scheduler 的 asset-source-cleanup 任务
- ❌ 迁移 `brain-asset-migrate.ps1` 时**不引入异步/并发**，保持和 PS 单线程同语义，
  避免引出"半途断网 manifest 只写一半"的新故障面

## 退出标志

- [ ] B1-B6 全部合并
- [ ] `tools/asset/` 目录删除
- [ ] `.reference` profile 里 `gasset`/`gasset-scan`/`gasset-migrate` 三个函数
      改调 `python -m uv run brain asset-*`
- [ ] ROADMAP changelog 加 "A4 收尾 · 弃用 PS asset 脚本" 条目

---

## 决策点

这份计划目前建议：**等用户下一次说"继续推进"时，直接从 B1 开始做。** B1 的
两个脚本（stats + dedup）加一起 ~4 小时，有实打实的产物（统计报告 / 去重
清单），风险接近零——是开刀的最好地方。

## 变更记录

| 日期 | 说明 |
|---|---|
| 2026-04-21 | 首版；列出 5 个文件、风险等级、6 批迁移路线。 |
| 2026-04-21 | B1 完成（stats ec3d0e1 + dedup 95cdac4）；B2 完成（overview-cards 删除 beaea16）。 |
| 2026-04-21 | **B3 完成**：`brain_agents/asset_migrate.py` + CLI `brain asset-scan` / `brain asset-migrate-execute`。30 个新 pytest（classify 所有分支 / exclude / scan 写 TSV / execute copy+mtime+collision+trash+missing+brain-inbox+latest-manifest），全量 139 passed。PS 版暂保留做 3 周对拍。 |
