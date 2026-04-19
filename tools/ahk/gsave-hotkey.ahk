#Requires AutoHotkey v2.0
#SingleInstance Force

; ============================================================
; Chase's second-brain-hub · Gemini/剪贴板 一键归档热键 (带诊断日志)
; ============================================================
; 行为:
;   1. 按 CapsLock+D 触发
;   2. 先尝试对当前选中文字执行 Ctrl+C (用户不再需要手动复制)
;   3. 若没选中任何内容 → 降级使用原剪贴板内容
;   4. 调用 PowerShell 的 gsave 函数写入 D:\brain\99-inbox\
;   5. TrayTip 通知结果
; ============================================================

LOG_FILE := "C:\dev-projects\second-brain-hub\telemetry\logs\gsave-log.txt"

LogMsg(msg) {
    global LOG_FILE
    ts := FormatTime(A_Now, "yyyy-MM-dd HH:mm:ss")
    FileAppend ts . "  " . msg . "`n", LOG_FILE
}

; 启动记录
LogMsg("==== AHK 脚本启动, PID=" . ProcessExist())

CapsLock & d:: {
    LogMsg("▶ CapsLock+D 触发")

    ; 保存原剪贴板作为降级方案 (保留所有格式)
    savedClip := ClipboardAll()

    ; 清空后发 Ctrl+C 尝试复制选中文字
    A_Clipboard := ""
    Send "^c"

    ; 等最多 500ms 看选中文字是否被复制进来
    copiedOk := ClipWait(0.5)

    if (copiedOk) {
        LogMsg("  ✅ 已从选中文字复制, 长度 = " . StrLen(A_Clipboard))
    } else {
        ; 没选中文字 → 恢复原剪贴板作为降级
        A_Clipboard := savedClip
        LogMsg("  ℹ 无选中文字, 降级使用原剪贴板, 长度 = " . StrLen(A_Clipboard))
    }

    clipLen := StrLen(A_Clipboard)
    if (clipLen = 0) {
        LogMsg("  → 选中为空, 剪贴板也为空, 退出")
        TrayTip "second-brain-hub", "没选中文字, 剪贴板也空, 什么都没保存", 0x2
        SetTimer () => TrayTip(), -3000
        return
    }

    preview := SubStr(A_Clipboard, 1, 80)
    if (StrLen(A_Clipboard) > 80) {
        preview .= "..."
    }
    LogMsg("  剪贴板预览: " . SubStr(preview, 1, 60))

    LogMsg("  调用 PowerShell (RunWait)...")
    exitCode := RunWait('powershell.exe -Command "gsave"', , "Hide")
    LogMsg("  ← PowerShell 退出码 = " . exitCode)

    TrayTip "已存入 brain inbox", preview, 0x1
    LogMsg("  弹出成功气泡")
    SetTimer () => TrayTip(), -3000
}
