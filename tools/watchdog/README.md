# tools/watchdog/

**L1 auto-restart watchdogs**: 监控后台任务, 死了自动重启 (幂等任务), 通知用户。

## 原则 (对齐 `rules/cloud-local-delegation.md`)

- L1 = **Safe auto-restart**, 不改代码, 不调云端, 不 git commit
- L2 (TODO) = 云端读 log + 写诊断报告到 `_escalation/`, 等人审
- L3 (TODO, 需白名单) = 云端自主 apply patch + restart, 有 branch 隔离 + budget cap

## 文件

| 文件 | 作用 |
|---|---|
| `notify.ps1` | 可复用的通知库: `Show-BrainMessageBox` / `Send-BrainAlert`（静默 MessageBox, 不响铃不强解屏）。 |

> 2026-04-21 清理: `pdf-production-watchdog.ps1` 与其监控对象 `tools/ollama-pipeline/*` 一并
> 随 A3 上线删除。`notify.ps1` 作为通用通知库保留，后续任何 watchdog 都可 `. notify.ps1` 复用。
