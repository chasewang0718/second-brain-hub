# tools/watchdog/

**L1 auto-restart watchdogs**: 监控后台任务, 死了自动重启 (幂等任务), 通知用户。

## 原则 (对齐 `rules/cloud-local-delegation.md`)

- L1 = **Safe auto-restart**, 不改代码, 不调云端, 不 git commit
- L2 (TODO) = 云端读 log + 写诊断报告到 `_escalation/`, 等人审
- L3 (TODO, 需白名单) = 云端自主 apply patch + restart, 有 branch 隔离 + budget cap

## 文件

| 文件 | 作用 |
|---|---|
| `notify.ps1` | 可复用的通知库: `Show-BrainToast` / `Invoke-BrainBeep` / `Send-BrainAlert` |
| `pdf-production-watchdog.ps1` | 专盯 `brain-asset-pdf-pipeline.ps1 -Production` |

## 典型用法

```powershell
# 独立后台启动 (和 production 同时)
Start-Process powershell.exe -ArgumentList @(
    '-NoProfile','-File',
    'C:\dev-projects\second-brain-hub\tools\watchdog\pdf-production-watchdog.ps1'
) -WindowStyle Hidden -PassThru
```

## 产出

`D:\second-brain-assets\_migration\_watchdog\`:

- `alerts.log` — 所有告警一行一条
- `heartbeat.txt` — 每 30 min 刷新一次的 JSON 状态 (白天查最后更新时间)
- `state.json` — watchdog 退出时写最终结果 (success / max_restarts_exceeded)
- `watchdog-*.log` — watchdog 本身的运行日志

## 扩展成通用 watchdog

明天可以抽象成 `watchdog.ps1 -PidFile X -RestartCmd Y -SuccessPattern Z`, 套给别的
batch 任务 (image-classify, inbox-text-route 等)。现在先专用, 不过度设计。
