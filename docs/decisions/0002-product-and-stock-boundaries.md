# ADR-0002：产品层与统一 Stock Service 边界

- 状态：Accepted
- 日期：2026-08-13
- 决策者：项目用户与 Codex

## 背景

设备既显示股票行情，也允许 GPT 回答股票问题。如果 UI 与 GPT 各自访问数据源，价格、时间和错误语义会分叉。股票业务也不能污染 Xiaozhi 的 Board、Display driver 或协议基础设施。

## 决定

- 固件在 Xiaozhi 基础设施之上新增独立 Product Layer：stock client/cache、Dashboard/Detail/Voice Overlay 和 app coordinator。
- 后端 v1 是模块化单体，Stock Service 拥有 watchlist、canonical models、cache 和 `StockProvider` 适配器。
- ESP32 Dashboard 与 GPT 的 `get_stock_quote`、`get_watchlist`、`get_stock_intraday` 只读取同一 Stock Service/cache。
- 股票首版用 HTTP/JSON；语音继续使用 Xiaozhi 协议。协议不为形式统一而合并。
- Provider、OpenAI 和其他秘密只在服务端；ESP32 不持有第三方 API Key/Token。

## 放弃方案

- ESP32 直连行情 Provider：暴露凭据、难缓存、供应商变化会耦合固件。
- GPT 工具自行请求另一行情源：破坏屏幕与语音一致性。
- 首版微服务：部署和故障面超过当前需要。
- 把 Dashboard 写进 RLCD/Board 文件：使业务与硬件耦合并阻碍 upstream 更新。

## 后果

统一模型必须定义单位、时间戳、source、freshness 和缺失值；缓存与错误语义成为后端责任。Provider 尚未选定，Phase 3 必须用契约测试验证候选实现。

## 重评条件

只有 HTTP 轮询经 Phase 4 实测无法满足目标、单体出现可量化独立扩缩容/隔离需求，或 Stock Service 需要独立产品化时，才评估 WebSocket 或服务拆分。
