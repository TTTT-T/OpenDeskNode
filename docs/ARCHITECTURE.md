# 当前系统架构

最后核验：2026-08-15

## 固件基线与边界

`firmware/xiaozhi/` 是已验收的 Xiaozhi v2.4.2 冻结副本，用于查阅板级参数、驱动和语音实现。它不是产品固件基底，也不进入正式产品运行路径。已验收状态由 annotated tag `phase-1b-xiaozhi-reference` 保留。

`firmware/product/` 是唯一的正式产品固件工程，是独立 ESP-IDF 项目：

```text
firmware/product
├─ main/                 启动编排与硬件自检
├─ components/
│  ├─ board/            Waveshare GPIO 与 BOOT 键
│  ├─ display/          ST7305 RLCD + LVGL 最小页面
│  └─ network/          NVS、event loop、Wi-Fi station/最小配网
├─ partitions.csv       16 MB Flash、单 factory app、无 OTA
└─ sdkconfig.defaults   ESP32-S3、octal 8 MB PSRAM、DIO 80 MHz
```

当前控制流：

```text
app_main
  ├─ flash / PSRAM runtime check
  ├─ display_init → esp_lcd SPI → ST7305 → LVGL clean page
  ├─ board_button_init → GPIO ISR → debounced event callback
  └─ network_init → NVS + netif + event loop → Wi-Fi station
```

## 网络边界

当前只有 Wi-Fi station 与最小配网能力。为在不保存凭据、不擦除用户 NVS 的前提下验收，新固件可一次性读取冻结基线使用的 `wifi` NVS schema，然后交由 ESP-IDF Wi-Fi NVS 管理。这是数据兼容路径，不是 Xiaozhi runtime dependency。全新设备在无凭据时启动 ESP-IDF SmartConfig。

正式固件不包含 Xiaozhi 激活、OTA、WebSocket/MQTT 业务协议、MCP 或云端 ASR/LLM/TTS，也不访问 `xiaozhi.me`、`api.tenclass.net` 或其他 Xiaozhi 官方服务。

## 产品目标架构（未实现部分）

```text
ESP32 product firmware                    Own backend
┌─ board / display / network ─┐          ┌─ Stock Service ── Provider
│  Product coordinator       │  HTTP    │  canonical models/cache
│  dashboard + stock client  │◀────────▶│
│  voice hardware/session    │  audio   │  Voice Gateway
└─ local wake word          ─┘◀────────▶└─ OpenAI Realtime API
```

- Dashboard 和 GPT 股票问答将共用同一 Stock Service 与标准模型。
- 本地唤醒词、麦克风和扬声器由正式固件自主管理；后续通过自有 Voice Gateway 连接 OpenAI Realtime API。
- OpenAI 与行情 Provider 凭据只存在服务端安全存储，不进入 ESP32 或 Git。

## 不可破坏边界

- Xiaozhi is a reference implementation, not the product firmware base.
- 只迁移已核对的硬件参数与底层实现；不整包引入 Xiaozhi Application 或云平台架构。
- 产品业务不进入 Board、ST7305、Codec 等底层驱动。
- 不把构建通过当作真机验收；显示、按键、Wi-Fi、音频和长稳分别保留实测证据。
- 冻结参考基线不追踪 upstream `main`；更新必须固定 tag/SHA 并重新回归。

有效长期决策见 [decisions/README.md](decisions/README.md)，阶段顺序见 [ROADMAP.md](ROADMAP.md)。
