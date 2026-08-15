# Phase 1A — USB 、设备身份与原厂备份

- 目标：在不写入设备的前提下建立 USB/串口、芯片、Flash 与安全状态基线，并完成两份原厂 Flash 备份。
- 结果：Mac 稳定枚举 Espressif `303a:1001` 与 `/dev/cu.usbmodem3101`；设备为 ESP32-S3 revision v0.2、16 MB Flash、8 MB PSRAM，Secure Boot 和 Flash Encryption 均未启用。
- 备份：两次独立读取 `0x1000000` bytes，两份文件均为 16,777,216 bytes，SHA-256 均为 `d3daff70d8ab60c521e2dc944e2f6b0540280b0dcec2d09d4a29a48bd0c99913`，`cmp` 逐字节一致。
- 保存：备份位于被 Git 忽略的 `.tools/phase-01/factory-backup-2026-08-15/`，目录权限 `0700`，文件权限 `0600`。备份可能包含原厂配置，不得提交或公开。
- 恢复边界：只在需要回滚且再次确认设备身份后，使用 esptool 将任一已校验的完整备份从 `0x0` 写回；不把恢复命令当作普通烧录流程。
- 未验收：本阶段未写入新固件，也未验收启动、显示、按键、Wi-Fi 或音频。

