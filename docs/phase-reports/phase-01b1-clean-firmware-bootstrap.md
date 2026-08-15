# Phase 1B.1 — Clean Firmware Bootstrap

- 日期：2026-08-15
- 结果：待屏幕目视与 BOOT 实体按键最终确认
- 详细记录：[PHASE1B1_CLEAN_FIRMWARE_BOOTSTRAP.md](../PHASE1B1_CLEAN_FIRMWARE_BOOTSTRAP.md)

## 结果

- annotated tag `phase-1b-xiaozhi-reference` 冻结 Phase 1B 已验收 Xiaozhi v2.4.2；旧代码和历史未改写。
- `firmware/product/` 建立为独立 ESP-IDF v6.0.2 产品固件，包含 board/display/network 组件，不包含 Xiaozhi Application 或云协议。
- 完整构建、烧录和 cold boot 通过；真机确认 16 MB Flash、8 MB octal PSRAM、RLCD/LVGL 初始化、BOOT 驱动与 Wi-Fi station 实际联网。屏幕可读内容与 BOOT 实体事件仍待用户最终确认，因此本 Phase 尚未标记完成。
- 运行时无 Xiaozhi 服务器、账号、激活、OTA、MCP、业务协议或云端语音依赖。

## 验收命令

```bash
bash scripts/verify-phase-1b1.sh
bash scripts/build-clean-firmware.sh
```

## 保留风险

- ESPTouch/AirKiss 只是最小配网方案，后续需单独产品化。
- 音频硬件、AEC/VAD/唤醒、RLCD 持续刷新与长稳尚未验收。
