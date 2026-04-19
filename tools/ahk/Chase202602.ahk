#Requires AutoHotkey v2.0

; ========================================================
; 1. 核心组合键：Tab 体系 (关闭、截图)
; ========================================================

; Tab + W -> 智能关闭 (原 F1 功能)
Tab & w::
{
    if WinActive("ahk_class CabinetWClass")     ; 资源管理器
    or WinActive("ahk_exe chrome.exe")          ; Chrome
    or WinActive("ahk_exe msedge.exe")          ; Edge
    or WinActive("ahk_class MozillaWindowClass") ; Firefox
    {
        Send "^w"
    }
    else
    {
        Send "!{F4}"
    }
}

; Tab + Q -> 截图 (原 F2 功能)
Tab & q::Send "{PrintScreen}"

; 【还原】单按 Tab -> 恢复制表符 (Tab) 的功能
; 因为 Tab 参与了组合键 (Tab & w/q)，所以必须显式定义单按时的行为
Tab::Send "{Tab}"


; ========================================================
; 2. 核心编辑键位：CapsLock 体系 (剪切、撤销、重做、全选、保存、粘贴)
; ========================================================

; --- CapsLock 组合键 ---
CapsLock & q::Send "^x"    ; 剪切 (Ctrl+X)
CapsLock & w::Send "^z"    ; 撤销 (Ctrl+Z) - [新增]
CapsLock & e::Send "^y"    ; 重做 (Ctrl+Y) - [新增]
CapsLock & a::Send "^a"    ; 全选 (Ctrl+A)
CapsLock & s::Send "^s"    ; 保存 (Ctrl+S)

; --- 单键功能 ---

; 单按 CapsLock -> 粘贴 (Ctrl+V)
; (注意：只有在松开 CapsLock 且没有按其他组合键时触发)
CapsLock::Send "^v"


; ========================================================
; 3. 特殊逻辑：Shift 单按复制
; ========================================================

; 单按 Shift -> 复制 (Ctrl+C)
~LShift Up::
{
    if (A_PriorKey = "LShift")
        Send "^c"
}

~RShift Up::
{
    if (A_PriorKey = "RShift")
        Send "^c"
}

; ========================================================
; 4. 功能还原与紧急开关
; ========================================================

; 恢复大写锁定功能：Shift + CapsLock
+CapsLock::
{
    if GetKeyState("CapsLock", "T")
        SetCapsLockState "AlwaysOff"
    else
        SetCapsLockState "AlwaysOn"
}

; 恢复 Shift+Tab (反向缩进)
+Tab::Send "+{Tab}"

; 紧急开关：F12
F12::Suspend

; ========================================================
; 5. 常用文本扩展
; ========================================================

:*:;mail::info@chasewang.nl
:*:;web::chasewang.nl
:*:;tel::+31 630925750
:*:;addr::Kastanjelaan 9, 9741CN Groningen

:*:;date::
{
    CurrentDate := FormatTime(, "yyyy-MM-dd")
    SendText CurrentDate
}