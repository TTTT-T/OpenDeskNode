# 当前系统架构

最后核验：2026-08-13

当前仓库已固定 Xiaozhi 固件 upstream，但尚未实现产品业务层或后端。以下“已存在”与“目标结构”必须区分：目录计划不等于已完成代码。

## 已存在的运行时基线

`firmware/xiaozhi/` 是 `78/xiaozhi-esp32` v2.4.2 的固定 subtree。目标板现有链路为：

```text
Application / DeviceState
  ├─ Wi-Fi + Xiaozhi protocol + OTA + MCP
  ├─ AudioService → ES7210 / ES8311 / I2S / device AEC
  └─ Display::SetupUI → LVGL RGB565
                         → threshold
                         → 400×300×1-bit framebuffer
                         → ST7305 full-frame SPI transfer
```

目标板板级代码只负责 GPIO、I2C、SPI、Codec、Display、Button、Battery 和能力声明。它不是产品业务层。

## v1 目标结构

```text
ESP32 Firmware                              Backend modular monolith
┌──────────────────────────────┐           ┌─────────────────────────────┐
│ Xiaozhi Infrastructure       │  voice    │ Voice                       │
│ board/network/audio/protocol │◀─────────▶│ ASR → OpenAI GPT → TTS      │
├──────────────────────────────┤           ├─────────────────────────────┤
│ Product Layer                │  HTTP     │ Stock Service               │
│ app coordinator              │◀─────────▶│ watchlist/cache/provider    │
│ stock client + cache         │           ├──────────────┬──────────────┤
│ dashboard/detail/overlay     │           │ HTTP API     │ GPT tools    │
└──────────────────────────────┘           └──────────────┴──────────────┘
```

股票显示与 GPT 工具只能依赖同一组标准模型和 Stock Service：

```text
StockProvider → canonical StockQuote / IntradaySeries → cache
                                                   ├─ HTTP API → ESP32 UI
                                                   └─ get_stock_* → GPT
```

## 主要控制流

```text
BOOT → CONNECTING → IDLE/DASHBOARD
                       ↓ user voice
                   LISTENING → THINKING → SPEAKING
                       └──────────→ IDLE/DASHBOARD
```

不创建与 Xiaozhi `DeviceState` 竞争的第二套全局状态机。产品协调器订阅或适配现有状态；Dashboard 是 Idle 的产品视图，语音状态以 Overlay/Chat 临时覆盖。

## 接口边界

| 边界 | v1 选择 | 约束 |
| --- | --- | --- |
| ESP32 ↔ Stock | HTTP/JSON | 超时、stale 时间和最后成功值必须显式；首版不用 WebSocket |
| ESP32 ↔ Voice | Xiaozhi 现有协议 | 不为股票统一协议，不重写音频链路 |
| GPT ↔ Stock | 服务端工具调用 | 工具只调用 Stock Service，不直接调用 Provider |
| Stock ↔ Provider | `StockProvider` 适配器 | 业务层不出现 AKShare/Tushare 字段或凭据 |
| Secrets | 服务端安全存储/环境 | 固件和 Git 只知道非秘密端点与变量名 |

## 标准股票模型最低字段

`StockQuote` 至少包含 `symbol`、`name`、`price`、`change`、`change_pct`、`prev_close`、`open`、`high`、`low`、`volume`、`turnover`、`timestamp`、`source` 和 `freshness`。金额、成交量和时间必须有明确单位/时区；Provider 缺字段时返回显式缺失，不伪造零值。

## 资源边界

- RLCD 1-bit framebuffer 约 15 KB；当前实现另外在 PSRAM 分配约 240 KB 像素 index LUT、120 KB bit LUT 和约 240 KB RGB565 LVGL buffer，精确值以 map/运行日志为准。
- 股票 UI 禁止持续动画和高频滚动；先接受 upstream 全帧刷新，只有 Phase 4/5 实测瓶颈才评估 dirty-region 优化。
- Phase 1 必须记录 boot、idle、display active、voice active 的 internal heap、largest free block 与 PSRAM；Build passed 不能替代真机资源证据。

## 不可破坏边界

- 产品业务不进入 Board、ST7305、Codec 或底层协议驱动。
- OpenAI/行情凭据不进入 ESP32。
- Dashboard 和 GPT 股票问答不建立两套行情路径。
- 不直接追 upstream `main`；任何升级先固定 tag/SHA、构建、审查 patch，再真机回归。
- 已验收的 Xiaozhi 基础设施优先复用；大规模 fork 修改需要新 ADR。

有效长期决策见 [decisions/README.md](decisions/README.md)，阶段顺序见 [ROADMAP.md](ROADMAP.md)。
