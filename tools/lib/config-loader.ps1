#Requires -Version 5.1
<#
.SYNOPSIS
    second-brain-hub 配置读取工具 (Phase 1 最小版).

.DESCRIPTION
    为了兼容 Windows PowerShell 5.1 (无 ConvertFrom-Yaml),
    这里提供一个轻量 YAML 读取器, 支持当前 config/*.yaml 的结构:
      - 2 空格缩进
      - key: value 标量
      - 嵌套对象
    不支持数组和复杂 YAML 语法.
#>

function Get-HubRoot {
    return (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}

function ConvertFrom-SimpleYaml {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        throw "YAML 文件不存在: $Path"
    }

    $lines = Get-Content -Path $Path -Encoding UTF8
    $root = [ordered]@{}
    $stack = New-Object System.Collections.ArrayList
    [void]$stack.Add([PSCustomObject]@{
        Indent = -1
        Node   = $root
    })

    foreach ($rawLine in $lines) {
        if (-not $rawLine) { continue }

        $line = $rawLine.TrimEnd()
        if ($line.Trim() -eq "") { continue }
        if ($line.TrimStart().StartsWith("#")) { continue }
        if ($line.Trim() -eq "---") { continue }

        $match = [regex]::Match($line, '^(?<indent>\s*)(?<key>[A-Za-z0-9_.-]+)\s*:\s*(?<value>.*)$')
        if (-not $match.Success) {
            continue
        }

        $indent = $match.Groups["indent"].Value.Length
        $key = $match.Groups["key"].Value
        $valueRaw = $match.Groups["value"].Value.Trim()

        while ($stack.Count -gt 0 -and $indent -le $stack[$stack.Count - 1].Indent) {
            [void]$stack.RemoveAt($stack.Count - 1)
        }
        $parent = $stack[$stack.Count - 1].Node

        if ($valueRaw -eq "") {
            $newNode = [ordered]@{}
            $parent[$key] = $newNode
            [void]$stack.Add([PSCustomObject]@{
                Indent = $indent
                Node   = $newNode
            })
            continue
        }

        $value = $valueRaw
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        } elseif ($value -match '^(true|false)$') {
            $value = [bool]::Parse($value)
        } elseif ($value -match '^-?\d+$') {
            $value = [int]$value
        } elseif ($value -match '^-?\d+\.\d+$') {
            $value = [double]$value
        }

        $parent[$key] = $value
    }

    return $root
}

function Get-BrainConfigFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("paths", "thresholds", "task-router")]
        [string]$Name
    )

    $hubRoot = Get-HubRoot
    $file = Join-Path $hubRoot "config\$Name.yaml"
    return $file
}

function Get-BrainConfig {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("paths", "thresholds", "task-router")]
        [string]$File,

        [Parameter(Mandatory = $false)]
        [string]$Key
    )

    $path = Get-BrainConfigFile -Name $File
    $obj = ConvertFrom-SimpleYaml -Path $path

    if (-not $Key) {
        return $obj
    }

    $parts = $Key.Split(".")
    $cur = $obj
    foreach ($part in $parts) {
        if ($cur -is [System.Collections.IDictionary] -and $cur.Contains($part)) {
            $cur = $cur[$part]
        } else {
            throw "配置键不存在: $File.$Key"
        }
    }
    return $cur
}

