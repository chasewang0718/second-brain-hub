# config/

**机器可读的硬数据** (YAML). 所有阈值、映射、枚举、路由的**单一真相源**.

代码直接读这里的 yaml, 不要在代码里硬编码数字/路径.

## 文件

| 文件 | 作用 |
|---|---|
| `paths.yaml` | 全局路径: brain_content_root, logs_dir, escalation_dir |
| `categories.yaml` | PDF/文档分类枚举 + Tier A/B 路径映射 + 敏感度 |
| `thresholds.yaml` | 置信度阈值, timeout, token 预算 |
| `models.yaml` | 任务 -> 模型选择 (local 14b / cloud opus / 等) |
| `task-router.yaml` | **通用委派表**: 每类任务的 primary/fallback/escalate 策略 |

## 修改约束

- 改 yaml 必须更新 [CHANGELOG.md](../CHANGELOG.md)
- 改 `categories.yaml` 必须同步跑 `evals/pdf-classify/run-eval.ps1` 验证无回归
- 路径类字段 (Windows) 用 `D:\\brain-content\\...` 双反斜杠, 或用 `D:/brain-content/...` 正斜杠
