# 产品需求（v1）

最后核验：2026-08-18

本文件是产品行为的 canonical 需求入口，只记录已确认需求；假设与待定项单独标注，不得当作已确认事实。产品目标原文与历史讨论见 `docs/archive/`。

## 产品定位

在 Waveshare ESP32-S3-RLCD-4.2（ESP32-S3-WROOM-1-N16R8：16 MB Flash、8 MB PSRAM、400×300 单色全反射 RLCD、双麦 ES7210、ES8311 codec、BOOT/KEY 等外设）上构建长期稳定、可维护的 A 股桌面看板。语音是附加能力，经 Mac EVA Voice Bridge → OpenClaw Talk → EVA 接入，不是独立 Voice Terminal，也不是看板运行依赖。

## 已确认：4 股 A 股看板行为

以下均为用户已确认的 v1 产品行为，不是待定项。

### 数据与来源

1. 市场为 A 股；单屏固定同时显示恰好 4 只自选股。
2. 行情只来自自有 LAN Gateway（Stock Gateway）；ESP32 不直连任何行情 Provider，不持有任何行情凭据。
3. Gateway 后续提供 web 管理页，可动态编辑这 4 只自选股；无需重新烧录固件即可切换标的。

### 已确认：Gateway 的最小 Provider 边界

4. Stock Service 在服务端通过可复用 Provider adapter 获取行情；ESP32 只访问自有 LAN Gateway。
5. Provider adapter 的最小操作为 `resolve_symbol`、`get_quotes`、`get_intraday`；adapter 将各来源的字段转换为统一 canonical Quote/Intraday。
6. Provider 选择、调用频率与失败降级由 Gateway 负责；本阶段不要求 ESP32 直连、持有 token 或理解 provider-specific 字段。

### Phase 1D Gateway 交付边界（已在 NAS 验收）

7. Gateway 使用版本化 HTTP/JSON dashboard；每个 `device_id` 独立保存恰好四个
   有序且唯一的 slot，保存 watchlist 后无需重新烧录即可供下一次 ESP 轮询读取。
8. Gateway 保存每只股票最后成功 snapshot（quote、当前交易日分钟数组、真实
   data timestamp、`last_success_at` 和 freshness），Provider 暂时不可用时保留
   SQLite 旧数据，不建立长期历史行情库。
9. Gateway 的已确认实现组合为 easyquotation/Tencent quote primary、Baidu direct
   intraday supplementary、adata/Sina quote fallback；缺少可靠状态证据时保持
   `UNKNOWN`。LAN 内暂不登录，但不把服务设计为公网暴露。

### 每只股票的展示（无详情页）

10. v1 没有股票详情页；任何按键都不进入单股详情界面。
11. 每只股票显示：中文名称（不显示股票代码）、现价、涨跌额、涨跌幅。
12. 涨跌用前缀符号表达，不依赖颜色（单色 RLCD）：上涨 `▲ +1.25%`，下跌 `▼ -0.86%`。
13. 每只股票一条日内分时 sparkline，以昨收价为基线。
14. 每只股票带市场状态：`NORMAL` / `LIMIT_UP` / `LIMIT_DOWN` / `SUSPENDED`。

### 刷新与可读性

15. 刷新目标约 10 秒（最终由数据源配额与真机实测微调）。
16. 2–3 米外一眼可读（glance readability）。
17. 信息密度均衡：不过载也不空旷；像素级排版在真机上调优。

### 交互与开机行为

18. 开机自动行为：上电后自动连接 Wi-Fi 并进入看板，无需人工操作。
19. BOOT 键后续作为设置入口；在承担该职责之前，固件只保留按键捕获。

### 失败与降级

20. 行情失败时保留最后一次成功数据继续显示，并显示最后更新时间；失败未超过 5 分钟不显示错误；超过 5 分钟显示全局失败状态。

### 市场时段

21. 盘前：显示盘前市场状态与开盘倒计时。
22. 午间：显示“午间休市”和下午开盘倒计时。
23. 周末与节假日：待机显示（standby）。

## 已确认：明确延后（不属于 v1）

- 持仓、成本、盈亏（P&L）。
- 价格提醒（alerts）。
- 股票详情页、K 线、开高低等扩展交互。

以上能力不在当前路线内，除非用户重新确认。

## 已确认：语音方向（附加能力，ADR-0005 / ADR-0006）

1. 正式固件本地管理唤醒词、麦克风、扬声器、AEC、VAD 与本地 barge-in 停播；不包含 Xiaozhi 激活、OTA、MCP 或云端 ASR/LLM/TTS，也不访问 Xiaozhi 官方端点。
2. 实时听说经 Mac EVA Voice Bridge → OpenClaw Talk `gateway-relay` 接入 OpenAI Realtime `gpt-realtime-2.1`；自然语言与工具经 `eva` agent consult。ESP32 不直连 OpenAI，不实现 OpenClaw 协议。
3. 目标唤醒词为「你好 EVA」（真机唤醒率 Pending；当前无自定义 WakeNet 模型）。一次唤醒后连续多轮，不必每轮再唤醒。
4. 股票问答若发生，必须经 NAS Stock Gateway 同源数据，不用模型记忆猜价格。
5. 设备音频基线：16 kHz/16-bit/mono PCM（Phase 2A）。Talk 侧为 pcm16/24 kHz；重采样在 Bridge。设备协议见 Phase 2C 草案。

## 最终产品验收口径

开机自动连接并进入看板，稳定显示 4 只自选股，约 10 秒刷新，最少人工干预。

## 待定项（不得当作已确认）

- ESP32 ↔ Mac Voice Bridge 设备协议细节与延迟口径（Phase 2C 草案，未验收）。
- 「你好 EVA」WakeNet 模型获取/训练与真机唤醒率。
- headless Bridge 的 ChatGPT OAuth 续期方式。

## 安全与凭据约束

- OpenAI Key、行情 Token 与 Wi-Fi 密码不得进入固件、Git、仓库文档或测试夹具。
- 凭据只存在服务端安全存储；ESP32 不持有任何第三方 API Key。

## 权威来源

- 微雪产品文档：<https://docs.waveshare.com/ESP32-S3-RLCD-4.2>
- 微雪官方示例：<https://github.com/waveshareteam/ESP32-S3-RLCD-4.2>
- Xiaozhi 固件参考（冻结副本上游）：<https://github.com/78/xiaozhi-esp32>
- OpenAI Realtime：<https://developers.openai.com/api/docs/guides/realtime>
- AKShare 股票文档：<https://akshare.akfamily.xyz/data/stock/stock.html>
- Tushare A 股实时分钟：<https://tushare.pro/document/2?doc_id=374>

固定工具链与 upstream 版本核验见 [UPSTREAM_BASELINE.md](UPSTREAM_BASELINE.md)。
