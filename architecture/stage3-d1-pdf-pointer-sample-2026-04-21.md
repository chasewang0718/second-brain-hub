# D1 · PDF 指针卡最小抽样（10 张）— 2026-04-21

> 目的：在 **无大规模批处理报告** 的前提下，对 **Tier A 指针卡** 做一轮可重复的结构化扫样，供 `stage3-e-acceptance` 勾选 D1 **初样** 使用。  
> 方法：在 `D:\second-brain-content` 中按 `asset_type: pdf` 路径抽 10 张，人工读 frontmatter + 标题/摘要区段。

## 样本表

| # | 相对路径 | 标题 | 标签/域 | 摘要 | 备注 |
|---|----------|------|---------|------|------|
| 1 | `03-projects/inbox-auto-pdf/asset-0-20.md` | 0-20 | `asset, pdf, pointer-card, auto-ingest` | **TODO 桩** | 大文件 21MB，A3 未解析正文；**质量缺口**、需批处理/重跑后评 |
| 2 | `03-projects/chase-photo-video-productions/asset-factuur-20230009.md` | Factuur 20230009 — … | `invoice, factuur, netherlands, photo-video, …` | 有：服务类型、日期、号、**无敏感金额** | 与 `sensitive: true` 一致，结构规范 |
| 3 | `03-projects/chase-photo-video-productions/asset-kvk-uittreksel-2023-04-02.md` | （KVK 类） | 商业登记 | 同系一致 | 与 2 同项目、可对比版式 |
| 4 | `07-life/finance/tax/aangifte-inkomstenbelasting-2021-c-wang.md` | Fiscaal rapport 2021 | `tax, netherlands, IB, 2021` | 有：页数、结构、**无 BSN/金额** | 税务类模板好例 |
| 5 | `07-life/finance/tax/2020-kilometer-registratie-4e-kwartaal-overview.md` | 公里登记 | `tax, netherlands, 2020, Q4` | 有 | 与 4 同域 |
| 6 | `07-life/finance/tax/chase-photo-btw-2020-kw4-overview.md` | BTW 概览 | 税 / 经营 | 有 | 与业务线 cross-link 可验 |
| 7 | `07-life/finance/invoices/invoice-ykzqdqf8-0001-xai-supergrok.md` | xAI Grok | `invoice, SaaS` | 有摘要 | SaaS 发票形态 |
| 8 | `07-life/finance/invoices/factuur-n1357437-antagonist-chasewang-hosting.md` | Antagonist hosting | hosting | 有 | 周期性费用类 |
| 9 | `07-life/finance/invoices/factuur-29088721-123inkt.md` | 123inkt | commerce | 有 | 消费电子类 |
| 10 | `01-concepts/biology/t-cell-differentiation-memory-models-figure.md` | （生物学概念图） | `biology, pdf` | 非发票域 | **多样性**：科学 PDF vs 财务 PDF |

## 结论（粗）

- **完备性**：财务/税务类样本 **title / tags / AI 摘要 / asset_path / sensitive** 普遍齐全；符合隐私条款的「摘要不含敏感明细」执行一致。  
- **缺口**：`asset-0-20.md` 为 **批处理 pilot 桩**，摘要 TODO —— 代表 **D2 / 重跑管线** 的改进面，不等同于「误分类」，而是 **未完成解析**。  
- **误分类**：本批未做「物理路径 vs 标签」逐条审计；建议 Stage 2 大批次后再做 **比例估计**。

## 后续

- Stage 2 PDF 批次继续跑满后：在本表基础上扩至 **20+** 张并补一列「路径路由是否正确」。
