# 项目上下文

最后核验：2026-08-13

## 产品目标

在 Waveshare ESP32-S3-RLCD-4.2 上构建长期稳定、可维护的桌面信息终端：

1. 默认常驻少量 A 股自选行情，第一版显示名称、代码、价格、涨跌额、涨跌幅和数据时间；
2. 复用 Xiaozhi 的音频、网络和对话基础设施，接入真正的 OpenAI GPT；
3. GPT 回答股票问题时必须调用与屏幕相同的 Stock Service，不能用模型记忆猜价格。

成功标准不是演示动画，而是数据一致、断网可解释、长期运行稳定、上游可升级且硬件能力有实测证据。

## 已确认事实

- 目标硬件是 Waveshare ESP32-S3-RLCD-4.2 / ESP32-S3-WROOM-1-N16R8：16 MB Flash、8 MB PSRAM、300×400 单色全反射 RLCD、双麦 ES7210、ES8311、PCF85063、SHTC3、TF 卡、KEY/BOOT、18650 电池管理。
- `78/xiaozhi-esp32` 从 v2.2.4 起包含该板；当前固定固件基线为 v2.4.2，板级实现包含 SPI RLCD、LVGL、Codec、双麦参考输入、设备侧 AEC 配置、BOOT 键和电池 ADC。
- 当前 RLCD 驱动把 LVGL RGB565 像素阈值化到 1-bit framebuffer；每次 flush 最终发送完整约 15 KB framebuffer。它适合秒级行情刷新，不适合高帧率动画。
- Xiaozhi `Display::SetupUI()` 在 `Application::Initialize()` 中调用；产品 UI 应在显示/Application 扩展层接入，不进入 ST7305 或 Board 驱动。
- `xinnan-tech/xiaozhi-esp32-server` v0.9.6 提供 WebSocket、ASR、LLM、TTS、插件、Function Calling、设备/服务端/接入点 MCP；其 OpenAI-compatible LLM 适配器当前使用 Python SDK 的 Chat Completions 接口。
- OpenAI 官方当前支持 function calling，也提供 Realtime 音频与工具调用；v1 仍选择可分段验证的 ASR → GPT → TTS，Realtime 是后续独立升级。
- 硬件尚未到位。任何显示、音频、AEC、按键、电池、Wi-Fi 或稳定性结论都未通过本项目真机验收。

## v1 范围

- 固件：Xiaozhi 基础设施之上的产品层、股票 Dashboard、语音状态 Overlay、股票 HTTP 客户端。
- 后端：模块化单体，包含 Voice、Stock、Tools 与 ESP32 HTTP API。
- 股票：自选列表、报价、缓存、数据新鲜度、Provider 适配器；后续再加日内分时。
- 语音：Xiaozhi 协议 + ASR + OpenAI GPT + TTS；股票工具复用 Stock Service。
- 安全：OpenAI Key、行情 Token 和 Wi-Fi 密码不得进入固件、仓库、测试夹具或提交历史。

## v1 非目标

- OpenAI Realtime、自研音频栈、K 线、新闻解释、微服务拆分、高帧率动画、无证据的局部刷新优化。
- ESP32 直接访问 AKShare、Tushare 或持有其凭据。
- 把股票业务写入 `waveshare-s3-rlcd-4.2.cc`、`custom_lcd_display.cc` 或其他 Board/驱动文件。

## 当前假设

- 桌面看板所需行情刷新周期预计为数秒到十几秒，最终值由数据源权限、缓存和实测决定。
- 股票数据开发期可用 AKShare，正式候选包括 Tushare；Phase 3 以权限、条款、稳定性和失败行为实测后决定默认 Provider。
- 后端最终部署位置、网络暴露方式和运行资源尚未决定。

## 尚未验证

- 到货硬件的 SKU、硬件 revision、GPIO 与官方资料是否完全一致。
- RLCD 实际方向、中文字体、刷新延迟、残影和持续刷新稳定性。
- 双麦通道、参考通道、AEC、扬声器、按键、电池曲线、RTC、SHTC3、TF 卡的实际行为。
- 固件在语音空闲/活跃、显示活跃时的 internal heap、largest block、PSRAM 和长期稳定性。
- OpenAI 账号可用模型、成本/延迟目标，以及目标股票 Provider 的实际权限。

## 权威来源

- 微雪产品与文档：<https://docs.waveshare.com/ESP32-S3-RLCD-4.2>
- 微雪官方示例：<https://github.com/waveshareteam/ESP32-S3-RLCD-4.2>
- Xiaozhi 固件：<https://github.com/78/xiaozhi-esp32>
- Xiaozhi Server：<https://github.com/xinnan-tech/xiaozhi-esp32-server>
- OpenAI Function Calling：<https://developers.openai.com/api/docs/guides/function-calling>
- OpenAI Realtime：<https://developers.openai.com/api/docs/guides/realtime>
- AKShare 股票文档：<https://akshare.akfamily.xyz/data/stock/stock.html>
- Tushare A 股实时分钟：<https://tushare.pro/document/2?doc_id=374>

版本、SHA 和核验结果见 [UPSTREAM_BASELINE.md](UPSTREAM_BASELINE.md)。
