# second-brain-hub

**控制中枢 / 规则中央仓库** — 管理 AI 协作规则、任务派发策略、工具集、结构化配置。

与 `brain-content` (内容仓) 分离：本仓库只存**规则与工具**，不存内容。

---

## 架构总览

```
规则中枢 (本仓库)            内容仓库                    本地执行
second-brain-hub      <->    brain-content    <->       Ollama + cursor-agent
  规则 / 工具 / 配置         markdown / PDF / 照片       本地 14B + 云端 agent
  (GitHub 公仓)              (GitHub 私仓, 二进制本地)   (D:\BaiduSyncdisk 冷备)
```

## 目录说明

| 目录 | 内容 | 格式 |
|---|---|---|
| `config/` | 硬数据: 分类枚举, 阈值, 模型选择, 任务路由 | YAML |
| `prompts/` | 投喂 LLM 的 system prompt + few-shot | Markdown + JSON |
| `schemas/` | LLM 结构化输出契约 | JSON Schema |
| `tools/` | 可执行代码: 流水线, 派发器, 兜底队列, MCP server | PS1 / AHK / (未来 Python) |
| `rules/` | 人类可读的政策文档 (AI 行为协议, 隐私, 协作策略) | Markdown |
| `architecture/` | 架构图 + 成本模型 | Markdown |
| `evals/` | 金标数据集 + prompt 回归测试 | JSON + PS1 |
| `telemetry/` | 运行日志 + 成本分析 | JSONL + PS1 |

## 核心文档

- [rules/AGENTS.md](rules/AGENTS.md) — AI 行为总协议
- [rules/cloud-local-delegation.md](rules/cloud-local-delegation.md) — 云-本地协作通用策略
- [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) — 整体架构
- [brain-tools-index.md](brain-tools-index.md) — 工具命令速查

## 快速开始

```powershell
# 安装工具到 PowerShell profile
.\install.ps1

# 跑一次 PDF 分类 pilot
gollama-pilot

# 查看最近 N 天本地 vs 云端调用统计
.\telemetry\analyze.ps1 -Days 7
```

## 与 brain-content 的连接点

脚本通过 `config/paths.yaml` 读取 `brain_content_root`，不直接硬编码路径。
修改内容仓位置只需改一处。

## License

Private / personal use. No warranty.
