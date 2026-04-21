# iPhone 本地备份（给 P3 导入用）

1. **关加密备份**（关键）  
   在 **Apple 设备** / **iTunes** 的 iPhone 摘要里，确保**不勾选**「加密本地备份」，否则通讯录/WhatsApp SQLite 不可用。

2. **整机备份一次**  
   USB 连接 iPhone → 选择本机 → **立即备份**。等待完成后再拔线。

3. **记下备份路径**  
   Windows 通常在 `%USERPROFILE%\Apple\Mobile Sync\Backup\<UDID>`（或 `%LOCALAPPDATA%\Apple Computer\MobileSync\Backup\<UDID>`）。  
   在同一台 PC 上用 hub：`brain backup-ios-locate` → `brain contacts-ingest-ios --dry-run` → `brain whatsapp-ingest-ios --dry-run` 确认能找到 `AddressBook.sqlitedb` / `ChatStorage.sqlite` 后再去掉 `--dry-run`。
