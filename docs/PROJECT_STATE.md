# 项目当前状态

最后更新：2026-08-20

本文件是当前阶段与状态的唯一入口。文档归属见 [DOCUMENT_INDEX.md](DOCUMENT_INDEX.md)。
新会话从这里定位当前 Phase，再按需读取指向的 canonical 文档；不为背景加载
全部阶段报告或 `docs/archive/`。

## 当前 Phase

**Phase 2C — EVA Voice Bridge Interface & Transport**（进行中）。

定义：[PHASE2C_EVA_VOICE_BRIDGE.md](PHASE2C_EVA_VOICE_BRIDGE.md)。
协议草案：[VOICE_BRIDGE_PROTOCOL.md](VOICE_BRIDGE_PROTOCOL.md)。
决策：[ADR-0005](decisions/0005-openclaw-realtime-gateway-relay.md)、
[ADR-0006](decisions/0006-eva-voice-bridge-thin-adapter.md)。

### 目标

冻结 ESP32 ↔ EVA Voice Bridge ↔ OpenClaw Talk 接口，并证明最小双向实时
音频 transport（C0–C5）。不是把完整语音助手做完。

### 非目标

自建 STT/TTS、本地 LLM 语音主链、ESP32 直连 OpenAI、OpenClaw 协议下沉固件、
股票改版、HA/OTA/账户/公网、完整 wake 产品化（可拆 2C.x）。

### 预计模块

`docs/VOICE_BRIDGE_PROTOCOL.md`；`bridge/` 薄服务。C0 host + live Talk 已通。
**C1 已真机验收 PASS**（2026-08-19，见
[phase-02c-c1-live-acceptance.md](phase-reports/phase-02c-c1-live-acceptance.md)）：
4 轮真人中文 `transcript.done`、每轮 drop=0 无跨轮污染、2A selftest 回归
PASS、audio ownership 让权→归还→再上行成功、股票链全程正常。验收中额外
修复 ownership 饥饿、Talk reader 存活、断线 conversation 失效三个缺陷。
**C2 已真机验收 PASS**（2026-08-19，见
[phase-02c-c2-live-acceptance.md](phase-reports/phase-02c-c2-live-acceptance.md)）：
Realtime 回答经 ES8311 可听，frames_rx≈frames_play、underrun=0、drop=0，
股票链全程正常。验收中修复采集窗丢下行与 2 s drop-oldest 卡顿。
播放中 BOOT 本地先停、`interrupt` / `cancelOutput`、同 cid 新上行。
不得破坏 Phase 2A `audio_hw` / codec / I2S / AEC。**C4 `HW-ACCEPTANCE-PENDING`**（automatic verification: PASS）。**C5 `HW-ACCEPTANCE-PENDING`**（automatic verification: PASS）。Wake 仅工程边界，`WAKE MODEL PENDING`。

### 验收标准

C0 Bridge↔Talk（host fixture，已通）；C1 上行中文（**ACCEPTED**，2026-08-19）；
C2 下行播放（**ACCEPTED**，2026-08-19）；C3 本地先停 barge-in
（**ACCEPTED**，2026-08-20）；C4 一次唤醒多轮（**HW-ACCEPTANCE-PENDING**，automatic verification: PASS）；
C5 Bridge/Gateway/Wi-Fi 恢复且不必重启 ESP32（**HW-ACCEPTANCE-PENDING**，automatic verification: PASS）。
交付状态定义见 [DELIVERY_WORKFLOW.md](DELIVERY_WORKFLOW.md) §3.1。
统一真机入口：`bash scripts/accept-hardware.sh`。

### 风险与回滚点

- Talk 24 kHz vs 设备 16 kHz，Bridge 必须重采样。
- headless OAuth 续期未验证（可推迟）。
- 回滚点：`4121dca`。不删除 `dev` / `phase-2b-r`，不 merge 旧实验分支。

## 已验证语音主链（Phase 2B，不得退回）

```text
ESP32 Voice Edge（2A）
  → EVA Voice Bridge（2C，实现中）
  → Mac mini OpenClaw Gateway :18789
  → Talk transport=gateway-relay
  → OpenAI Realtime gpt-realtime-2.1
  → brain=agent-consult
  → EVA Agent（memory / tools / automation）
```

三个服务不得混称：NAS `terrencenas.local:8000` = Stock Gateway；
Mac `:18789` = OpenClaw Gateway；Mac Voice Bridge = 薄协议桥。
迁 OpenClaw 回 NAS 只是 Future / unvalidated。

禁止：自建 STT/TTS、Whisper 主链、ESP32 直连 OpenAI、ESP32 跑 LLM、
把旧 `STT → OpenClaw → TTS` 当产品主链。`gpt-live-1-codex` 不可用于
platform realtime。R0 浏览器 WebRTC FAIL = non-product / non-blocking。

Phase 2A 硬件基线已验收，不得破坏。

### 分支拓扑

- **`phase-2c-eva-voice-bridge`（本分支，基线 `4121dca`）**：从已验收
  realtime 主线切出的 2C 工作分支。
- **`phase-2b-realtime`（`4121dca`）**：2B 验证与 ADR-0005 文档收敛。
- **`dev`（`45bc6f8`）**：旧 VOICE_PROTOCOL v1 + Mock Gateway。不删除、不合并。
- **`phase-2b-r`（`9cd984b`）**：旧 ADR-0007 / 协议 v2。不删除、不合并；
  conversation/turn 语义可参考。
- Phase 1E/1D/1D.0/1C/1B.1 已验收；股票链路不受语音调整影响。

## 当前基线（已验收）

- `firmware/product/`：独立 ESP-IDF v6.0.2。1B.1 真机 Boot/Flash/PSRAM/RLCD/
  BOOT/Wi-Fi；1C mock 看板；1E 真实 4 股看板；2A 音频硬件。
- `firmware/xiaozhi/`：v2.4.2 冻结参考（tag `phase-1b-xiaozhi-reference`）。
- Stock Gateway Phase 1D 已在 NAS/非交易时段验收；交易时段补测保留。
- 语音软件主链 2B 已验证；Voice Bridge C0 已通，C1/C2 已真机验收 PASS
  （2026-08-19）；C3 本地先停 barge-in 已真机验收 PASS（2026-08-20）。
  C4/C5 `HW-ACCEPTANCE-PENDING`（automatic verification: PASS）。

历史阶段的范围/证据只在对应报告，不在本文件展开：
[1E](phase-reports/phase-01e-live-stock-dashboard.md)、
[1D](phase-reports/phase-01d-stock-gateway.md)、
[1D.0](phase-reports/phase-01d0-provider-bakeoff.md)、
[1C](phase-reports/phase-01c-stock-display-skeleton.md)、
[1B.1](phase-reports/phase-01b1-clean-firmware-bootstrap.md)。

## 最近完成

- [Phase 2C — C3 真机验收](phase-reports/phase-02c-c3-live-acceptance.md)（2026-08-20 PASS）
- [Phase 2C — C2 真机验收](phase-reports/phase-02c-c2-live-acceptance.md)（2026-08-19 PASS）
- [Phase 2C — C1 真机验收](phase-reports/phase-02c-c1-live-acceptance.md)（2026-08-19 PASS）
- [Phase 2B — Realtime 主链验证](phase-reports/phase-02b-realtime-validation.md)（2026-08-18）
- [Phase 2A — Voice Hardware Bring-up](phase-reports/phase-02a-voice-hardware-bringup.md)（2026-08-18 验收）
- Phase 1E / 1D / 1D.0 / 1C / 1B.1 / 1B / 1A / 0A / 0（见 `phase-reports/`）

## 交付状态（§3.1）

当前 actively implementing：无（本轮离线实现已完成）。

| 项 | 状态 |
| --- | --- |
| C0 host + live Talk | `ACCEPTED` |
| C1 真机上行 | `ACCEPTED`（2026-08-19） |
| C2 真机下行 | `ACCEPTED`（2026-08-19） |
| C3 BOOT 本地先停 barge-in | `ACCEPTED`（2026-08-20） |
| C3 播放中 device-side VAD barge-in | 未证实；不得写成 PASS |
| C4 same-session multi-turn | `HW-ACCEPTANCE-PENDING`（automatic verification: PASS） |
| C5 Bridge / Gateway / Wi-Fi recovery | `HW-ACCEPTANCE-PENDING`（automatic verification: PASS） |
| 「你好 EVA」WakeNet | `WAKE MODEL PENDING` |

两个 VAD 场景不得混淆：

- **播放中 barge-in VAD**：EVA 播放时 device-side VAD 插话。C3 正式成立的是 BOOT 本地先停；C4 **不要求**证明该路径。
- **静音 follow-up VAD**：`playback_end` 后 LISTENING 窗内由 device-side VAD 启动下一轮。C4 最终真机验收 **必须**证明该触发，而不是再按 BOOT。

## HW-ACCEPTANCE-PENDING 总清单

统一命令：`bash scripts/accept-hardware.sh`

### C4_MULTI_TURN

- 尚未执行：真机一次 BOOT 后至少两轮、不再按键的 follow-up。
- 为什么当前不能执行：用户不在 ESP32 旁。
- 替代证据：host follow-up vs barge-in 分离测试、`tests.test_bridge_c4`、`tests.test_c4_live_watcher`、`bash scripts/verify-phase-2c.sh`。
- 真机步骤：第一次 BOOT → 说第一句 → EVA 回答 → 不按键说第二句（最好第三句）。
- PASS：同一 cid、同一 Talk sessionId、create 不增加、≥2 新 `speech_start`、≥2 新 `transcript.done`、有新上行；串口出现 `PHASE2C_C4 follow_up why=vad`。FAIL：重建 session/cid、第二轮靠 BOOT、或只有历史 transcript。

### C3_LOCAL_STOP（回归）

- 尚未执行：本轮未重做播放中 BOOT 听音。
- 为什么当前不能执行：需要人耳。
- 替代证据：C3 已 ACCEPTED（2026-08-20）；本轮 host C3 回归通过。
- 真机步骤：EVA 播放时按 BOOT。
- PASS：扬声器立即停，且有新 interrupt / cancelOutput / 同 cid。FAIL：喇叭继续响或新开会话。

### C5_BRIDGE_RECOVERY / C5_GATEWAY_RECOVERY / C5_WIFI_RECOVERY

- 尚未执行：重启 Bridge、重启 OpenClaw Gateway、拔网再恢复。
- 为什么当前不能执行：需要现场操作，且不得把未做真机写成 PASS。
- 替代证据：host recovery backoff 测试、`tests.test_bridge_c5`、`tests.test_c5_live_watcher`、固件 bounded reconnect（无 `ESP.restart`）。
- 真机步骤：先建立旧 Talk session → watcher 打印 ARMED → 再制造故障；见 `scripts/accept-hardware.sh`。全程不重启 ESP32。
- PASS：watcher 先锁定旧 sessionId，恢复后 new_session_id ≠ stale_session_id，且有新 speech_start、uplink、transcript.done。仅 reconnect/hello 或 idle 后第一个 session 不得 PASS。FAIL：必须重启 ESP32、复用 stale sessionId、或无新上行。

### STOCK_REGRESSION

- 尚未执行：语音测试期间看板观察。
- 为什么当前不能执行：需要看 UI。
- 替代证据：`stock_service_start` 仍独立；host 未改股票路径。
- PASS：stock task / Gateway 轮询正常、UI 不崩。FAIL：Voice 重连导致看板死亡。

### WAKE_WORD

- 状态：`WAKE MODEL PENDING`。已有 mock/manual 抽象；无已确认「你好 EVA」WakeNet 模型。不得写成 PASS。

## 下一步

1. 用户回到设备旁只跑 `bash scripts/accept-hardware.sh`，按提示完成 Pending 项。
2. 运维（不进固件）：EVA 主模型 zai token；headless OAuth 续期。
3. 旧遗留补测：下一交易时段行情推进；2A WAV 限速与 AEC 模式对比。

## 重要风险与未验证

- headless OAuth 续期；下行 16 kHz 重采样质量；ESP32 AEC 下的产品 barge-in
  （浏览器外放自打断已证明需要硬件 AEC）。
- 2A：>16 kHz WAV 限速；仅验 VOIP_HIGH_PERF；音量 0 对照 inconclusive。
- 交易时段 Gateway 实时推进、NAS 全机重启、跨日长稳未验证。
- 电池、RTC、SHTC3、TF 卡未接入。
- 「你好 EVA」WakeNet 模型与真机唤醒率 Pending。

## 必读 canonical 文档

- 文档清单：[DOCUMENT_INDEX.md](DOCUMENT_INDEX.md)
- 产品需求：[PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)
- 当前架构：[ARCHITECTURE.md](ARCHITECTURE.md)
- 阶段顺序：[ROADMAP.md](ROADMAP.md)
- 当前有效决策：[DECISIONS.md](DECISIONS.md)
- 语音主链：[ADR-0005](decisions/0005-openclaw-realtime-gateway-relay.md)
- Voice Bridge：[ADR-0006](decisions/0006-eva-voice-bridge-thin-adapter.md)
