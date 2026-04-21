# Stage 3 · E — 验收清单（总闸）

本清单对应 ROADMAP 中 **Stage 3 验收**：B 达标 + A 全修 + C golden set ≥ 80% + D 抽样报告入库。  
**状态栏**：`[x]` 已满足 · `[ ]` 未满足 / 依赖 Stage 2 · `[~]` 部分满足（见备注）

---

## B · CLI / 冷启动与交互延迟

- [x] **B1–B2**：重型依赖（如 `lancedb` / `fastmcp`）不阻塞 `brain health` / `paths` 等轻命令（懒加载）。  
- [x] **B3**：无独立常驻 daemon 的决策已记录（journal / 本阶段结论：默认轻路径 + `ask --mode deep`）。  
- [x] **B4**：`brain health`、`inbox-list`、`ask`（默认 fast）在目标机器上 **小于 800ms** 量级已测并写入 `04-journal/2026-04-21.md` § `stage-3-b-performance`。  
- [x] **B 回归（本轮）**：2026-04-21 agent 复测 — `health` ~147ms、`inbox-list --limit 1` ~145ms、`ask --mode fast` ~193ms（RTX 4070 / 当前依赖版本）。重大依赖升级后仍需再跑一次。

---

## A · 低风险 UX / 配置

- [x] **A1** `telemetry-append` 非法 JSON 明确报错。  
- [x] **A3** `structure-history` density_split 可执行 hint。  
- [x] **A4** `write --limit` 与 `--source-limit` 别名。  
- [x] **A5** CLI UTF-8  stdout（CJK / Windows）。  
- [x] **A2a** `text_inbox` 阈值与路由关键词等迁入 `config/thresholds.yaml`（默认与旧行为一致）。  
- [ ] **A2b** 用 Stage 2 真实 inbox 调 text-inbox / 展示阈值（依赖真实数据）。  
- [ ] **A-config 收尾**：除 text-inbox 外是否还有硬编码阈值待抽（按需增列）。

---

## C · ask / write 质量（可重复测）

- [x] **C3** 中文 golden set：`tools/py/tests/ask_eval.yaml`（10 例）。  
- [x] **C4** 评估脚本：`tools/py/tests/eval_ask.py`，**topk_hit_ratio ≥ 0.8**（当前基线曾达 1.0）。  
- [x] **C-write**：`brain write --engine template|llm`，默认 `llm` + `BRAIN_WRITE_MODEL` 默认 `qwen2.5:14b-instruct`；约束与重试逻辑已接 `writing-constraints.yaml`。  
- [x] **C 回归（本轮）**：2026-04-21 `eval_ask.py` → `passed: 10`、`topk_hit_ratio: 1.0`、`ok: true`。大改 ask / 索引后仍需再跑。

---

## D · 真实数据质量回归

- [x] **D4** hub-pain triage 报告入库：`architecture/stage3-d4-hubpain-triage.md`。  
- [~] **D1** PDF 指针卡抽样：**初样** 见 `architecture/stage3-d1-pdf-pointer-sample-2026-04-21.md`（10 张 + 缺口说明）。大批次 Stage 2 产出后扩样并补「误分类率」。
- [ ] **D2** 字段缺失 → vision 补摘要（可选能力）。  
- [~] **D3** 联系人 CLI：**初样** 见 `architecture/stage3-d3-people-cli-sample-2026-04-21.md`（`Alice Zhang` / `overdue` / `wxid_*` 空列表对比）。真实联系人替换 demo 后做完整评测。
- [ ] **D0（隐含）** `ginbox` / inbox 噪声与 **A2b** 联动的 before/after 记录（可选 journal 一条）。

---

## E · 总闸 → Stage 4

- [ ] **E 全开**：仍缺 **A2b**（或书面豁免）+ D1/D3 **扩样**；B/C 回归与 D1/D3 **初样** 已具备。  
- [x] **E 部分**：B/A/C 主干 + D4 已完成，**允许并行 Stage 2**，Stage 4 决策前补齐 D 抽样与 A2b。  

**下一步（顺序建议）**：Stage 2 产出 → **D1** 与 **D3** 各做最小抽样 → **A2b** → 勾选 **E 全开** → 再开 `architecture/ROADMAP.md` Stage 4 决策点。

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-04-21 | 首版（E 文档化闭环） |
| 2026-04-21 | 本轮 agent：B/C 回归数据、D1/D3 初样报告链入；E 全开仍待 A2b + D 扩样 |
| 2026-04-21 | Caps+D 统一入口：AHK + PowerShell `gsave` 增加「文件拖放列表」分支 → 选中 PDF 时自动走 `brain pdf-inbox-ingest --path ...`（见 journal `§ caps-d-file-branch`）；新增 `ingest_pdf_paths` + `--path/-p` CLI 参数。文本分支完全不变。 |
| 2026-04-21 | A3 图像分支落地：`brain_agents/image_inbox.py` + `brain image-inbox-ingest`（paddleocr 懒加载，缺库时写 `ocr_status: pending` 指针卡 + `_cursor_queue/` 兜底）；新增 `config/paths.yaml:image_inbox_dir` 与 6 个 pytest 用例（全量 36）。后续 Caps+D 图像分支只需在 `gsave` 的 `CF_HDROP` 路径判断里追加 `.png/.jpg/...` → 调用同一 CLI。 |
