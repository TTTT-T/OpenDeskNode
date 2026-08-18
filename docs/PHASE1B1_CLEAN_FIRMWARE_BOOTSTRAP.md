# Phase 1B.1 — Clean Firmware Bootstrap

> **Historical phase definition / 详细记录** — 不是当前架构事实源。
> 短报告：[phase-01b1-clean-firmware-bootstrap.md](phase-reports/phase-01b1-clean-firmware-bootstrap.md)。

日期：2026-08-15

## 架构纠偏

Phase 1B 使用 Xiaozhi v2.4.2 完成了真机 bring-up，结果保留且不视为失败。为避免正式产品长期继承 Xiaozhi 官方激活、OTA、业务协议和云端语音架构，该版本从此冻结为“硬件参考基线 / bring-up reference”。

- 参考代码：`firmware/xiaozhi/`（保留原样）
- 参考标记：anotated tag `phase-1b-xiaozhi-reference`
- 标记目标：Phase 1B 已验收提交 `5113506`
- 正式固件：`firmware/product/`

## 新固件目录

```text
firmware/product/
├─ CMakeLists.txt
├─ sdkconfig.defaults
├─ partitions.csv
├─ dependencies.lock
├─ main/
│  ├─ CMakeLists.txt
│  ├─ idf_component.yml
│  └─ app_main.c
└─ components/
   ├─ board/       GPIO 定义、BOOT 中断与去抖
   ├─ display/     ST7305 SPI、1-bit framebuffer、LVGL 页面
   └─ network/     NVS、netif、event loop、station、SmartConfig
```

`main` 只编排启动和状态回调；板级、显示和网络各自保持独立组件边界。本阶段没有创建 stock 或 voice 空壳。

## 来源与迁移记录

| 项目 | 新实现 | 来源 | 分类与依赖 |
| --- | --- | --- | --- |
| 板型、分辨率、GPIO | `components/board/include/board.h` | `firmware/xiaozhi/main/boards/waveshare/esp32-s3-rlcd-4.2/config.h` | Waveshare 硬件参数；无 Xiaozhi Application 依赖 |
| ST7305 初始化序列 | `components/display/display_rlcd.c` | 冻结基线 `custom_lcd_display.cc` 的板级部分 | 保留 Phase 1B 已验证面板时序；使用 ESP-IDF `esp_lcd` |
| landscape 1-bit 像素映射与 RGB565 阈值 | `display_rlcd.c` | 同上 | 只改写底层算法，未迁移 Xiaozhi `Display` 类/LUT/Application |
| BOOT GPIO0 | `components/board/board_button.c` | 冻结基线板级定义 | GPIO ISR + FreeRTOS queue + 50 ms 去抖；无上层依赖 |
| Wi-Fi NVS schema 兼容 | `components/network/network_wifi.c` | 冻结基线 `components/78__esp-wifi-connect/ssid_manager.cc` 的 `wifi/ssid/password` key | 只用于一次性导入现有本地凭据；不链接该组件 |
| Wi-Fi station/配网 | `network_wifi.c` | ESP-IDF 官方 `esp_wifi`、`nvs_flash`、`esp_netif`、`esp_event`、`esp_smartconfig` | Espressif 官方组件 |
| LVGL 运行 | managed dependency | LVGL 9.5.0 + `espressif/esp_lvgl_port` 2.8.0~1 | 组件版本由 `dependencies.lock` 固定 |

没有复制 Xiaozhi Application、DeviceState、资产、音频服务、协议、OTA、MCP 或云端逻辑。

## 配置选择

- Target：`esp32s3`
- Flash：16 MB，DIO，80 MHz；运行时通过 `esp_flash_get_size()` 比对 16 MiB
- PSRAM：octal，80 MHz，纳入 heap；运行时通过 `esp_psram_get_size()` 比对 8 MiB
- Partition table：NVS `0x9000/0x6000`，PHY `0xf000/0x1000`，factory app `0x10000/0xF00000`
- OTA：本阶段明确不包含 OTA slot 或 Xiaozhi OTA
- Wi-Fi 凭据：不编译进固件、不记录到日志。优先使用 ESP-IDF 已保存配置；可一次性导入旧 NVS schema；新设备启动 ESPTouch/AirKiss SmartConfig

## 初始化路径

RLCD：`app_main()` → `display_init()` → SPI3/`esp_lcd_panel_io` → ST7305 reset/command sequence → 15,000-byte PSRAM framebuffer → LVGL display/flush → clean test page。

Wi-Fi：`app_main()` → `network_init()` → NVS recovery → `esp_netif_init()` → default event loop → Wi-Fi station → stored/reference-schema credential or runtime SmartConfig → station IP event。

## 验收证据

### 已验证

- 静态检查：`bash scripts/verify-phase-1b1.sh` 输出 `PHASE_1B1_STATIC_CHECKS_OK`。
- 构建：ESP-IDF v6.0.2 完整构建通过；最终 app 约 1.19 MB，15 MB factory partition 仍有 92% 空间。
- 烧录/启动：最终固件写入并通过 hash verify；cold boot 进入 `SPI_FAST_FLASH_BOOT`，无 boot loop、panic 或 abort。
- Flash：bootloader 和应用均确认 16 MB，应用日志为 16,777,216 bytes。
- PSRAM：识别 8 MB octal PSRAM @ 80 MHz，内存测试 OK，应用日志为 8,388,608 bytes。
- RLCD/LVGL：驱动完成 ST7305 初始化和页面提交，串口报告 `RLCD and LVGL bootstrap page ready`。
- RLCD 实体显示：用户目视确认最终 `phase-1b.1` 镜像的 `ESP32-S3 Dashboard / Clean Firmware` 测试页显示正常。
- BOOT：GPIO0 驱动与事件回调初始化成功；用户短按后串口捕获 `board_button: BOOT press` 和 `bootstrap: BOOT button press captured`。
- Wi-Fi：从保留的本地 NVS schema 导入一组 station 凭据，获得 IP 并输出 `Wi-Fi station connected`；未使用 Xiaozhi 账号或激活。

### 未验证

- 音频、AEC、VAD、唤醒词、电池、RTC、SHTC3、TF 卡和长时运行；均超出本阶段。
- SmartConfig 在全新/已擦除 NVS 设备上的手机端完整配网交互尚未实测；本次连接使用已保留的本地凭据。

## Xiaozhi 残余依赖

- 构建依赖：无。`firmware/product` 不编译、链接或 include `firmware/xiaozhi`。
- 运行时依赖：无。不需要 Xiaozhi 官方服务器、账号、激活、OTA 或业务协议。
- 数据兼容：保留一个可选的本地 NVS schema 导入路径，只读取 SSID/password 并交给 ESP-IDF Wi-Fi NVS；不调用 Xiaozhi 代码或网络服务。
- 源码参考：冻结的 board/display 参数继续留在仓库供审查。

## 已知风险

- ESPTouch/AirKiss 仅是 bring-up 最小配网；产品化前应单独设计更可观测、可重置、安全边界更清晰的 onboarding。
- ST7305 当前是全帧刷新，未验证残影、持续刷新与局部刷新。
- 一次性 NVS 兼容路径会读取旧 schema；为保留用户数据，本阶段不删除旧 namespace。

## 下一阶段建议

建议先做 **Voice Hardware Bring-up**，范围仅限 ES7210、ES8311、I2S、麦克风录音、扬声器播放和资源快照。原因是清理 Xiaozhi 产品基底后，音频是风险最高、依赖硬件实测最多的未验证边界；而 Stock Display Skeleton 已有独立 RLCD/LVGL 基线，稍后接入不会隐藏音频底层风险。下一阶段仍不应接入 OpenAI Realtime、AEC、VAD 或唤醒词。
