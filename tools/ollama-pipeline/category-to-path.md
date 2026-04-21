---
title: category -> Tier A / Tier B 路径映射表
purpose: 给本地模型看, 决定每个 category 该去哪个目录
updated: 2026-04-19
---

# 分类到目录的映射表

本地模型输出的 `category` 字段决定 Tier A 指针卡和 Tier B 原文件的去向.

说明:
- Tier A = `D:\second-brain-content\` 下 (Markdown 指针卡, 进 git)
- Tier B = `D:\second-brain-assets\` 下 (PDF 原文件, 不进 git)
- 两边目录大多对称, 少数例外 (如 book 类 Tier A 简短 Tier B 大块分散)

## 映射表

| category | Tier A dir | Tier B dir | 典型内容 |
|----------|-----------|-----------|----------|
| `invoice` | `07-life/finance/invoices` | `07-life/finance/invoices` | Factuur, Commercial invoice, 电商收据 |
| `tax` | `07-life/finance/tax` | `07-life/finance/tax` | Belastingdienst, IB, BTW, fiscaal rapport |
| `bank-statement` | `07-life/finance/bank-statements` | `07-life/finance/bank-statements` | ING afschrift, 月/季度对账单 |
| `housing` | `07-life/housing` | `07-life/housing` | 过户信、notaris 文件、房产合同 |
| `identity` | `07-life/identity` | `07-life/identity` | 护照、ID 复印件、BSN 相关 |
| `medical` | `07-life/health` | `07-life/health` | 医疗报告、处方、诊断书 |
| `contract` | `07-life/contracts` | `07-life/contracts` | 非房产的合同、协议、聘书 |
| `education` | `07-life/education` | `07-life/education` | 成绩单、学校证明、儿童成绩 |
| `inburgering` | `07-life/dutch-inburgering` | `07-life/dutch-inburgering` | KNM/Begrijpend lezen/Schrijven 练习册 |
| `business` | `03-projects/chase-photo-video-productions` | `03-projects/chase-photo-video-productions` | Chase Photo 公司发票/合同/授权书 |
| `certificate` | `07-life/certificates` | `07-life/certificates` | 培训证书、diploma、getuigschrift |
| `picture-book` | `01-concepts/picture-books` | `16-books/picture-books` | 中文儿童绘本、汉字识字图书 |
| `book` | `01-concepts/books` | `16-books` | 技术/学科长书、大块 PDF 教材 |
| `paper` | `01-concepts/papers` | `01-concepts/papers` | 学术论文、研究 PDF |
| `latex-project` | `03-projects/<proj-slug>` | `03-projects/<proj-slug>` | LaTeX 源码配套 PDF, slug 要识别项目 |
| `code-snippet` | `02-snippets/<lang-or-topic>` | — | 通常是小脚本/示例, 只需 Tier A |
| `design` | `17-design` | `17-design` | 海报、宣传物料、排版稿 |
| `other` | `99-inbox` | `98-staging` | 暂时无法归类, 等人审 |

## 特殊规则

1. **business 子分类**: 如果是 Chase Photo 公司的发票, `category=business` 且 `subcategory=invoice` 比 `category=invoice` 优先
2. **picture-book vs book**: 32 页以内、有大量图、儿童语言 -> `picture-book`; 否则 -> `book`
3. **sensitive 判断**:
   - 看到 BSN (荷兰身份证号, 9 位数字) -> sensitive=true
   - 看到 IBAN / 完整银行账号 -> sensitive=true
   - 看到具体金额 (除了公开的商业发票单价) -> sensitive=true
   - 看到完整家庭地址 (门牌号 + 街道 + 城市) -> sensitive=true
   - 看到他人姓名（非公众人物） -> sensitive=true
4. **confidence < 0.7 处理**:
   - 进 `proposal/low-confidence/` 池
   - QA 阶段 cursor-agent 优先抽查这些
   - 最终要么补分类, 要么进 `98-staging/` 人工
5. **多主题 PDF**: 只能分一个 category, 选"文档主要目的"那个. 在 `tags` 里加其他主题.

## 目录不存在时

本地模型只输出路径, 真实建目录和移动是 `brain-asset-pdf-apply.ps1` 做. 目录不存在就建.
