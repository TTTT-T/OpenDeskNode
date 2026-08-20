# 当前系统架构

最后核验：2026-08-19

文档归属见 [DOCUMENT_INDEX.md](DOCUMENT_INDEX.md)。本文只描述**当前有效系统**，
不堆叠已废弃方案。决策理由见 [DECISIONS.md](DECISIONS.md) /
[ADR-0005](decisions/0005-openclaw-realtime-gateway-relay.md) /
[ADR-0006](decisions/0006-eva-voice-bridge-thin-adapter.md)。

## 产品定位

OpenDeskNode 当前核心是桌面股票看板；语音是附加能力。Voice / Mac / OpenClaw
不可用时，NAS Stock 与看板必须继续工作。

## 语音拓扑（ADR-0005 / ADR-0006）

```text
ESP32-S3
│
├─ ES7210 双麦
├─ Hardware/Device-side AEC
├─ VAD
├─ Local wake word: “你好 EVA”
├─ local barge-in / stop playback
├─ ES8311 playback
└─ PCM audio transport
        │
        ▼
Mac mini
┌──────────────────────────────┐
│ EVA Voice Bridge             │
│                              │
│ - ESP32 device connection    │
│ - PCM framing                │
│ - session mapping            │
│ - turn/event translation     │
│ - buffering                  │
│ - resampling 16k ↔ 24k       │
│ - health / reconnect         │
│                              │
│ NO STT                       │
│ NO TTS                       │
│ NO LLM                       │
│ NO Agent logic               │
└──────────────┬───────────────┘
               │
               ▼
Mac mini OpenClaw Gateway :18789
               │
               ▼
OpenClaw Talk
transport = gateway-relay
brain = agent-consult
               │
               ▼
OpenAI Realtime
model = gpt-realtime-2.1
               │
               ▼
EVA Agent
               │
        ┌──────┼─────────┐
        ▼      ▼         ▼
      Memory  Tools   Automation
                    / HA / Calendar
```

- **EVA Voice Bridge** 与 **OpenClaw Gateway** 物理上可同机，架构层必须分离。
- **三个服务不得混称**：NAS `terrencenas.local:8000` = Stock Gateway；
  Mac `127.0.0.1:18789` = OpenClaw Gateway；Mac Voice Bridge = 薄桥。
- ESP32 不直连 OpenAI，不实现 OpenClaw 协议，不持有第三方 Key。
- `gpt-live-1-codex` 不能用于 platform realtime，不得写入目标拓扑。
- 旧主链 `STT → OpenClaw → TTS`、Whisper、自建 streaming STT/TTS、
  Mac 本地 LLM 语音主链、ESP32 本地 LLM **不是**当前架构。
- 迁 OpenClaw Gateway 回 NAS 只是 Future / unvalidated。

### 音频合同（已从 OpenClaw 2026.7.1-2 源码确认）

| 段 | 格式 |
| --- | --- |
| ESP32 ↔ Bridge | 16 kHz / s16le / mono / 20 ms（Phase 2A） |
| Bridge ↔ Talk gateway-relay | pcm16 / **24 kHz** / mono / base64 |
| 重采样 | Bridge 负责 |

设备协议工作草案：[VOICE_BRIDGE_PROTOCOL.md](VOICE_BRIDGE_PROTOCOL.md)。

### 两层 VAD

- 设备 VAD：上行时机与本地 barge-in 停播。
- Realtime server VAD：云端 turn detection。不是同一职责。
  Bridge 不重做主 VAD/AEC。

## 股票与语音解耦

```text
ESP32
    │
    ├── Stock UI
    │      │
    │      ▼
    │   NAS Stock Gateway :8000
    │
    └── Voice Edge
           │
           ▼
       Mac Voice Bridge
           │
           ▼
       Mac OpenClaw Gateway :18789
```

不为「统一 Gateway」合并 Stock 与 OpenClaw。统一发现/认证另开 ADR。

## 固件基线与边界

`firmware/xiaozhi/` 是已验收的 Xiaozhi v2.4.2 冻结副本，用于查阅板级参数、
驱动和语音实现。它不是产品固件基底。已验收状态由 annotated tag
`phase-1b-xiaozhi-reference` 保留。

`firmware/product/` 是唯一正式产品固件工程：

```text
firmware/product
├─ main/                 启动编排与硬件自检
├─ components/
│  ├─ board/            Waveshare GPIO 与 BOOT 键
│  ├─ display/          ST7305 RLCD + LVGL 最小页面
│  ├─ network/          NVS、event loop、Wi-Fi station/最小配网
│  ├─ stock/            model/view、Gateway HTTP/JSON client 与 host test
│  ├─ audio/            ES7210/ES8311、I2S、AEC、owner、2A 诊断自检
│  └─ voice/            C1 起 Voice Runtime：Bridge WS 与 16 kHz 上行
├─ partitions.csv       16 MB Flash、单 factory app、无 OTA
└─ sdkconfig.defaults   ESP32-S3、octal 8 MB PSRAM、DIO 80 MHz
```

当前控制流：

```text
app_main
  ├─ flash / PSRAM runtime check
  ├─ display_init → esp_lcd SPI → ST7305 → LVGL clean page
  ├─ stock_service_start → stock_svc task（16384 B 栈：view、Wi-Fi 就绪、
  │  约 10 秒 Gateway 轮询、解析/降级、刷新与指标日志）
  ├─ audio_selftest_start → 诊断任务（不默认占用 I2S；双击 BOOT 才抢权）
  ├─ voice_runtime_start → 默认音频 RX/TX owner + Bridge 上下行
  ├─ board_button_init → 单击 Talk / 双击 2A 诊断
  └─ network_init → NVS + netif + event loop → Wi-Fi station

 产品运行时只有一个音频 RX/TX owner（`audio_owner`）。Voice Runtime 是
 默认 owner；Phase 2A selftest 仍可调用，但必须先让 Voice 让权。C1 上行
  + C2 下行播放（ES8311）已真机验收。C3 本地先停 barge-in 已真机验收
  （BOOT 路径）。C4 一次会话多轮进行中；C5 重连本轮不做。
```

Phase 1E 仍把股票业务限制在 `components/stock/`：`stock_model.c` 与测试用
`stock_mock.c` 保持纯 C99；`stock_gateway_client.c` 只访问配置的 LAN
Gateway，`stock_gateway_parser.c` 严格转换 schema v1；`stock_view.c` 只通过
display 组件持有的 LVGL 锁更新 2×2 面板。service 在首次成功前显示连接态，
成功后保留 last-good snapshot；本地连续失败超过 5 分钟或 Gateway 报 stale
才进入全局异常。

Gateway dashboard 默认响应保持 Phase 1D 兼容；ESP32 请求可选
`intraday_samples=32` 投影。市场 session 由 Gateway canonical 数据提供。
24 px 字体覆盖 ASCII、U+4E00–U+9FEF 与涨跌箭头。

## Stock Gateway（NAS，已验收）

```text
FastAPI v1 API + 手机 Web
          │
          ▼
StockGatewayService
          ├─ SQLiteRepository（devices / 四槽 / settings / latest snapshots）
          └─ easyquotation/Tencent quote + Baidu direct intraday
             + adata/Sina quote fallback
```

容器只提供 LAN HTTP，部署在 TerrenceNAS `terrencenas.local:8000`。
NAS 全机重启与交易时段实时推进仍未验证。部署记录见
[NAS_STOCK_GATEWAY.md](NAS_STOCK_GATEWAY.md)。

## 网络边界

当前只有 Wi-Fi station 与最小配网。新固件可一次性读取冻结基线 `wifi` NVS
schema，然后交由 ESP-IDF Wi-Fi NVS 管理。这是数据兼容路径，不是 Xiaozhi
runtime dependency。全新设备在无凭据时启动 ESP-IDF SmartConfig。

正式固件不包含 Xiaozhi 激活、OTA、WebSocket/MQTT 业务协议、MCP 或云端
ASR/LLM/TTS，也不访问 Xiaozhi 官方服务。

## 不可破坏边界

- Xiaozhi is a reference implementation, not the product firmware base.
- 只迁移已核对的硬件参数与底层实现。
- 产品业务不进入 Board、ST7305、Codec 等底层驱动。
- 不把构建通过当作真机验收。
- 冻结参考基线不追踪 upstream `main`。

产品需求见 [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)，
阶段顺序见 [ROADMAP.md](ROADMAP.md)。
