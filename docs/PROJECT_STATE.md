# 项目当前状态

最后更新：2026-08-15

本文件是当前阶段与状态的唯一入口。新会话从这里定位当前 Phase 与最近相关报告，再按需读取指向的 canonical 文档；不为背景加载全部阶段报告或 `docs/archive/`。

## 当前 Phase

**[Phase 1C — Stock Display Skeleton](PHASE1C_STOCK_DISPLAY_SKELETON.md)** — 进行中（规划已确立，实现与验收尚未开始）。

目标：在 `firmware/product` 现有 RLCD/LVGL 基线上，以确定性 mock 打通 stock model → stock view → LVGL → RLCD 链路：4 等分面板、中文名称/价格/涨跌格式、sparkline+昨收基线、约 10 秒场景轮换（涨/跌/平/涨停/跌停/停牌/穿越昨收），并测量全帧刷新的闪烁/残影/CPU/内存/LVGL 开销。不接入真实行情。

## 当前基线（已验收）

- `firmware/product/`：独立 ESP-IDF v6.0.2 产品固件（唯一正式固件工程）。Phase 1B.1 已在真机验收 Boot、16 MB Flash、8 MB octal PSRAM、RLCD/LVGL、BOOT 按键与 Wi-Fi station。详见 [Phase 1B.1 报告](phase-reports/phase-01b1-clean-firmware-bootstrap.md)与[详细记录](PHASE1B1_CLEAN_FIRMWARE_BOOTSTRAP.md)。
- `firmware/xiaozhi/`：Xiaozhi v2.4.2 冻结硬件参考（annotated tag `phase-1b-xiaozhi-reference`），不是产品固件基底，默认不读取。
- 后端 Stock Gateway / Voice Gateway 尚未开始（Phase 1D 起）。

## 最近完成

- [Phase 1B.1 — Clean Firmware Bootstrap](phase-reports/phase-01b1-clean-firmware-bootstrap.md)（2026-08-15）
- [Phase 1B — First Xiaozhi Flash & Boot Verification](phase-reports/phase-01b-first-flash-boot.md)（2026-08-15）
- [Phase 1A — USB、设备身份与原厂备份](phase-reports/phase-01a-usb-identity-backup.md)（2026-08-15）
- [Phase 0A — 产品与 Upstream 基线](phase-reports/phase-00a-product-upstream-baseline.md)（2026-08-13）
- [Phase 0 — Agent 协作与交付基础设施](phase-reports/phase-00-agent-delivery-foundation.md)（2026-08-13）

## 下一步

完成 1C 后进入 Phase 1D — Stock Gateway（自部署行情后端：Provider 适配、cache、watchlist 与 web 管理、HTTP API），再 1E Live Stock Dashboard；语音链路在 Voice 2A/2B/2C 推进。顺序见 [ROADMAP.md](ROADMAP.md)。

## 重要风险与未验证

- RLCD 中文字体、2–3 米可读性、信息密度与持续刷新/残影（1C 真机验证）。
- 音频链路（双麦/参考通道、ES7210、ES8311、扬声器、AEC、VAD、唤醒词）、电池、RTC、SHTC3、TF 卡、业务负载下的内存与长稳。
- 行情 Provider 选型与 Gateway 部署位置未定（1D 决策）。
- 已验收历史能力默认不重新验证，除非当前改动可能引起回归。

## 必读 canonical 文档

- 产品需求：[PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)
- 当前架构：[ARCHITECTURE.md](ARCHITECTURE.md)
- 阶段顺序：[ROADMAP.md](ROADMAP.md)
- 当前有效决策：[DECISIONS.md](DECISIONS.md)
