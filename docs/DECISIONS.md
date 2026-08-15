# 当前有效决策

最后核验：2026-08-15

本文件是“当前哪些长期决策有效”的 canonical 入口，只汇总现状。完整背景、候选方案与决策历史见 [decisions/](decisions/README.md)；本文件不替代 ADR。

## 有效决策

1. **Xiaozhi 仅作参考，产品采用干净 ESP-IDF 固件**（[ADR-0004](decisions/0004-clean-product-firmware.md)，Accepted）
   - 正式产品只在 `firmware/product/` 上发展；`firmware/xiaozhi/`（v2.4.2，tag `phase-1b-xiaozhi-reference`）仅作参考。
   - 只按需迁移硬件参数、板级实现与已验证底层驱动，并记录来源与依赖；不迁移 Xiaozhi Application、激活、OTA、业务协议、MCP 或云端 ASR/LLM/TTS。
   - 语音目标路径：本地唤醒词 + 自有 Voice Gateway + OpenAI Realtime API。
2. **统一 Stock Service 数据边界**（[ADR-0002](decisions/0002-product-and-stock-boundaries.md)，Accepted；其“Xiaozhi 基础设施上的产品层”前提由 ADR-0004 替代）
   - 后端 v1 为模块化单体：Stock Service 拥有 watchlist、canonical models、cache 和 `StockProvider` 适配器。
   - ESP32 Dashboard 与 GPT 工具（`get_stock_quote`、`get_watchlist`、`get_stock_intraday`）只读取同一 Stock Service/cache；首版 HTTP/JSON。
   - Provider 与 OpenAI 凭据只在服务端；ESP32 不持有第三方 Key。
3. **股票与语音共享自部署 LAN Gateway**（用户已确认方向；Stock 侧边界见 ADR-0002，语音侧见 ADR-0004）
   - Stock Gateway 拥有 A 股数据、watchlist、cache 与后续 web 管理页；Voice Gateway 路径接入 OpenAI Realtime；两者部署在同一自托管后端。
   - 不使用 Xiaozhi 官方云或任何第三方托管网关。
4. **ESP32 不直连复杂互联网 API**（ADR-0002/0004 边界的固化）
   - 固件不持有第三方 Key，不直连带凭据的行情 Provider，不做云 ASR/LLM/TTS；行情与语音能力只经自有 Gateway。
5. **先股票后语音**（用户已确认路线，见 [ROADMAP.md](ROADMAP.md)）
   - 先完成 1C/1D/1E 的股票显示链路，再推进 Voice 2A/2B/2C。
6. **看板刷新目标约 10 秒**（用户已确认产品目标，见 [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)）
   - 最终节奏由数据源配额与 Phase 1E 真机实测微调；不为更快刷新预做 partial update 等复杂化。

## 已被替代（仅历史）

- [ADR-0001](decisions/0001-xiaozhi-upstream-integration.md)：Xiaozhi 固件 subtree 集成方式 — Superseded by ADR-0004。
- [ADR-0003](decisions/0003-v1-voice-pipeline.md)：v1 采用 Xiaozhi ASR → GPT → TTS — Superseded by ADR-0004。

## 其他长期工程约束

- 工具链与 upstream 版本固定策略见 [UPSTREAM_BASELINE.md](UPSTREAM_BASELINE.md)：当前 ESP-IDF v6.0.2；LVGL 9.5.0 + `espressif/esp_lvgl_port` 2.8.0~1 由 `dependencies.lock` 固定。
- 冻结参考基线不追踪 upstream `main`；更新必须固定 tag/SHA 并重新回归。
- 当前分区表为单 factory app、无 OTA slot；引入 OTA 属于独立 Future 决策。

变更规则：新决策或推翻旧决策时，先创建/更新 ADR，再同步本文件与 [ARCHITECTURE.md](ARCHITECTURE.md)。
