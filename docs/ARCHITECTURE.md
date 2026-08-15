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
│  ├─ network/          NVS、event loop、Wi-Fi station/最小配网
│  └─ stock/            Phase 1C model/mock/view/service 与 host test
├─ partitions.csv       16 MB Flash、单 factory app、无 OTA
└─ sdkconfig.defaults   ESP32-S3、octal 8 MB PSRAM、DIO 80 MHz
```

当前控制流：

```text
app_main
  ├─ flash / PSRAM runtime check
  ├─ display_init → esp_lcd SPI → ST7305 → LVGL clean page
  ├─ stock_service_start → stock_svc task（8192 B 栈预算：view 创建、
  │  mock reset、首屏刷新 → 约 10 秒确定性轮换与指标日志）
  ├─ board_button_init → GPIO ISR → debounced event callback
  └─ network_init → NVS + netif + event loop → Wi-Fi station
```

Phase 1C 的当前工作树实现把股票显示限制在 `components/stock/`：`stock_model.c`
和 `stock_mock.c` 保持纯 C99、可在主机编译；`stock_view.c` 只通过 display
组件持有的 LVGL 锁创建/更新 2×2 面板；`stock_service.c` 的 service task 在
其明确栈预算内完成 view 创建、mock reset 与首屏更新，并负责约 10 秒的
确定性 mock 场景轮换和刷新指标日志。display 组件只提供 RLCD
传输、LVGL 锁和全帧刷新指标，不承载股票业务模型。

Phase 1C 已由 commit `c2031a7` 完成并验收。启动边界已是 task-owned：
view 创建、mock reset 与首屏刷新都在具有明确栈预算（8192 字节）的 stock
service task 内执行，`app_main()` 只负责启动 service，main task 不创建/
刷新股票 UI，main task 栈未增大。真机串口、显示、内存与完整循环证据见
[Phase 1C 报告](phase-reports/phase-01c-stock-display-skeleton.md)。

## Phase 1D.0 Provider 边界

Phase 1D.0 只定义可复用的服务端 Provider 边界并完成候选数据源实测，不实现
完整 Stock Gateway、cache、watchlist、web 管理或复杂 routing。唯一依赖方向为：

```text
Stock Service → StockProvider adapter
                  ├─ resolve_symbol(symbol)
                  ├─ get_quotes(symbols)
                  └─ get_intraday(symbol, trading_date, ...)
```

`gateway/stock_provider/` 内的 adapter 负责 provider-specific symbol、字段和
时间格式转换；跨 provider 的 canonical `Quote` / `IntradayBar` 不泄漏原始
字段。Provider 与行情凭据仍只存在服务端，ESP32 只访问后续的自有 LAN
Gateway。

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
