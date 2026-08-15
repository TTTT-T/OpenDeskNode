# 项目上下文

最后核验：2026-08-15

## 产品目标

在 Waveshare ESP32-S3-RLCD-4.2 上构建长期稳定、可维护的股票看板与语音终端：

1. 自定义 RLCD/LVGL 界面显示自选行情，并正确表达数据时间、stale 和错误；
2. 正式 ESP-IDF 固件负责本地唤醒词、麦克风和扬声器交互；
3. 后续通过自有 Voice Gateway 连接 OpenAI Realtime API，不依赖 Xiaozhi 官方服务器、账号或激活；
4. GPT 股票问答与屏幕共用同一 Stock Service，不用模型记忆猜价格。

## 已确认事实

- 目标硬件是 Waveshare ESP32-S3-RLCD-4.2 / ESP32-S3-WROOM-1-N16R8：16 MB Flash、8 MB PSRAM、400×300 单色全反射 RLCD、双麦 ES7210、ES8311、BOOT/KEY 等外设。
- Xiaozhi v2.4.2 已在 Phase 1B 完成真机 Boot、RLCD、BOOT 单击和 Wi-Fi 最小验收；该代码现冻结为硬件 reference，不再作为产品固件基底。
- `firmware/product/` 是独立 ESP-IDF v6.0.2 工程，已在真机识别 16 MB Flash、8 MB octal PSRAM，完成 RLCD/LVGL、BOOT 驱动、Wi-Fi station 与 NVS 基础链路。
- 新固件不包含 Xiaozhi Application、激活、OTA、MCP、业务协议或云端 ASR/LLM/TTS，也不访问 Xiaozhi 官方端点。
- 当前 RLCD 底层将 LVGL RGB565 阈值化到 1-bit framebuffer，再通过 ST7305 SPI 全帧发送；适合低频看板，不适合高帧率动画。

## 当前范围

- 固件：干净 ESP-IDF 基线、板级驱动、产品协调层、Dashboard/Overlay、股票 HTTP 客户端、本地唤醒与语音硬件。
- 后端：Stock Service、Voice Gateway、OpenAI Realtime 会话与工具边界。
- 安全：OpenAI Key、行情 Token 和 Wi-Fi 密码不得进入固件、仓库或测试夹具。

## 当前非目标

- Phase 1B.1 不实现音频质量优化、AEC、VAD、唤醒词、OpenAI Realtime/GPT、股票数据或股票 UI。
- 不迁移 Xiaozhi 激活、OTA、WebSocket/MQTT 业务协议、MCP 或云端 ASR/LLM/TTS。
- ESP32 不直连带凭据的行情 Provider，不持有 OpenAI 或行情 API Key。

## 当前假设

- 看板行情刷新周期预计为数秒到十几秒，最终由数据源、缓存和真机测量决定。
- 本地唤醒与 Voice Gateway 的音频格式、延迟和会话协议将在音频硬件基线后单独决策。
- 后端部署位置与行情 Provider 尚未决定。

## 尚未验证

- 实物 PCB/revision 与官方原理图所有 GPIO 的逐项一致性。
- RLCD 中文字体、刷新延迟、残影、多次刷新和长时显示。
- 双麦/参考通道、ES7210、ES8311、扬声器、AEC、VAD、唤醒词、电池、RTC、SHTC3 和 TF 卡。
- 业务负载下的 internal heap、largest block、PSRAM 峰值和长稳。

## 权威来源

- 微雪产品文档：<https://docs.waveshare.com/ESP32-S3-RLCD-4.2>
- 微雪官方示例：<https://github.com/waveshareteam/ESP32-S3-RLCD-4.2>
- Xiaozhi 固件参考：<https://github.com/78/xiaozhi-esp32>
- OpenAI Realtime：<https://developers.openai.com/api/docs/guides/realtime>
- AKShare 股票文档：<https://akshare.akfamily.xyz/data/stock/stock.html>
- Tushare A 股实时分钟：<https://tushare.pro/document/2?doc_id=374>

固定版本与核验结果见 [UPSTREAM_BASELINE.md](UPSTREAM_BASELINE.md)。
