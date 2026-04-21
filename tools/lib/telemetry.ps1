#Requires -Version 5.1
<#
.SYNOPSIS
    second-brain-hub telemetry 写入工具.

.DESCRIPTION
    提供统一入口 Write-Telemetry:
      - 自动补 ts (UTC ISO8601)
      - 自动定位 telemetry/logs/YYYY-MM.jsonl
      - output_summary 自动截断到 50 字符
      - task=blocked-tier-c 时自动移除 source 字段
#>

function Get-HubRoot {
    return (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}

function Get-TelemetryLogsDir {
    [CmdletBinding()]
    param()

    $defaultDir = Join-Path (Get-HubRoot) "telemetry\logs"
    $configLoader = Join-Path (Get-HubRoot) "tools\lib\config-loader.ps1"
    if (Test-Path $configLoader) {
        . $configLoader
        if (Get-Command Get-BrainConfig -ErrorAction SilentlyContinue) {
            try {
                $configured = Get-BrainConfig -File "paths" -Key "paths.telemetry_logs_dir"
                if (-not [string]::IsNullOrWhiteSpace($configured)) {
                    return $configured
                }
            } catch {}
        }
    }

    return $defaultDir
}

function Get-TelemetryLogPath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [datetime]$Timestamp = (Get-Date).ToUniversalTime()
    )

    $logsDir = Get-TelemetryLogsDir
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    }

    $month = $Timestamp.ToString("yyyy-MM")
    return (Join-Path $logsDir "$month.jsonl")
}

function Write-Telemetry {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Entry
    )

    # copy to mutable hashtable
    $data = @{}
    foreach ($k in $Entry.Keys) {
        $data[$k] = $Entry[$k]
    }

    if (-not $data.ContainsKey("ts") -or [string]::IsNullOrWhiteSpace([string]$data["ts"])) {
        $data["ts"] = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }

    # 最小必填检查 (剩余字段由各调用方按 schema 负责)
    $required = @("task", "executor", "model", "duration_ms", "schema_valid", "escalated")
    foreach ($key in $required) {
        if (-not $data.ContainsKey($key)) {
            throw "Write-Telemetry 缺少必填字段: $key"
        }
    }

    if ($data.ContainsKey("output_summary") -and $null -ne $data["output_summary"]) {
        $summary = [string]$data["output_summary"]
        if ($summary.Length -gt 50) {
            $data["output_summary"] = $summary.Substring(0, 50)
        }
    }

    # Tier C 事件不落 source 字段
    if ($data.ContainsKey("task") -and [string]$data["task"] -eq "blocked-tier-c") {
        if ($data.ContainsKey("source")) {
            $null = $data.Remove("source")
        }
    }

    $path = Get-TelemetryLogPath -Timestamp ([DateTime]::Parse([string]$data["ts"]).ToUniversalTime())
    $json = $data | ConvertTo-Json -Compress -Depth 8
    Add-Content -Path $path -Value $json -Encoding UTF8

    return $path
}

