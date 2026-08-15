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

## 目标形态：ESP32 + 共享 LAN Gateway

当前已有效的能力是 board/display/network（Phase 1B.1 真机验收）；股票与语音是目标形态，共用同一台自部署 LAN Gateway：

```text
ESP32-S3（轻量客户端）                  自部署 LAN Gateway（同一后端）
┌─ board / display / network ─┐        ┌─ Stock Gateway ──────────────┐
│  dashboard + stock client ──┼─HTTP──▶│  A 股数据 / Provider 适配     │
│  voice hardware/session ────┼─audio─▶│  watchlist / cache / web 管理 │
│  local wake word            │        │  Voice Gateway 路径           │
└─────────────────────────────┘        │  └─ OpenAI Realtime API       │
                                       └──────────────────────────────┘
```

- ESP32 保持轻量：只负责显示、按键、Wi-Fi、音频采集/播放与本地唤醒词；不直连复杂互联网 API，不持有任何第三方凭据。
- Stock Gateway 拥有 A 股行情数据、watchlist（4 股）、cache 与后续 web 管理页；Dashboard 与 GPT 股票问答同源读取。
- Voice Gateway 路径拥有 OpenAI Realtime 凭据与会话；本地唤醒词、麦克风和扬声器由正式固件自主管理。
- OpenAI 与行情 Provider 凭据只存在服务端安全存储，不进入 ESP32 或 Git。

## 不可破坏边界

- Xiaozhi is a reference implementation, not the product firmware base.
- 只迁移已核对的硬件参数与底层实现；不整包引入 Xiaozhi Application 或云平台架构。
- 产品业务不进入 Board、ST7305、Codec 等底层驱动。
- 不把构建通过当作真机验收；显示、按键、Wi-Fi、音频和长稳分别保留实测证据。
- 冻结参考基线不追踪 upstream `main`；更新必须固定 tag/SHA 并重新回归。

当前有效决策见 [DECISIONS.md](DECISIONS.md)（完整历史见 [decisions/README.md](decisions/README.md)），产品需求见 [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)，阶段顺序见 [ROADMAP.md](ROADMAP.md)。
