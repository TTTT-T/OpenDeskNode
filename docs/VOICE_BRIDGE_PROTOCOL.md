# EVA Voice Bridge Protocol — draft 0

状态：**Phase 2C 工作草案**，不是已验收合同。
Owner：Phase 2C。[阶段定义](PHASE2C_EVA_VOICE_BRIDGE.md)。
参考：`phase-2b-r` 的 VOICE_PROTOCOL v2 conversation/turn/barge-in 语义。
**不要照搬 v1/v2，也不要把 OpenClaw API 名称写入本协议。**

## 1. 角色

- **Device**：ESP32 Voice Edge。
- **Bridge**：EVA Voice Bridge（本协议服务端）。
- OpenClaw Talk 只存在于 Bridge 下游，设备不可见。

一条 WebSocket 连接同时只承载一个 conversation。

## 2. 传输

- WebSocket，LAN only。建议路径：`ws://<bridge-host>:<port>/voice/v0`。
- 文本帧 = 一条完整 JSON 控制消息。
- 二进制帧 = 16 字节头 + PCM 载荷。
- 连接后第一条必须是 `hello`。版本不匹配：`hello_error` 后关闭。

发现与认证本阶段不做；`hello` 预留 `auth` 字段，v0 忽略。

## 3. 音频合同

| 段 | 格式 | 谁负责 |
| --- | --- | --- |
| ESP32 → Bridge | 16 kHz, s16le, mono, 20 ms 帧（320 samples / 640 B） | Device |
| Bridge 内部（设备侧） | 同上 | Bridge |
| Bridge → Talk `appendAudio` | pcm16 / **24 kHz** / mono / base64 | Bridge 上采样 |
| Talk → Bridge `output.audio.delta` | pcm16 / **24 kHz** / mono / base64 | OpenClaw 硬编码 |
| Bridge → ESP32 | 16 kHz, s16le, mono, 20 ms | Bridge 下采样 |

codec 标识：`pcm_s16le_16k_mono`。双方 `hello` 只接受该值。
时间戳：发送方单调毫秒，仅诊断。seq：每方向每 turn 从 0 递增。
**C1 起二进制 PCM 必须恰好 640 B**；非该长度的帧静默丢弃并计入
`dropped_old`。seq 重复丢弃并计 `seq_dup`；乱序迟到丢弃并计
`seq_reorder`；出现缺口计 `seq_gap`，会话不中断。播放侧 jitter buffer
**C2 已实现**：400 帧 × 320 samples = 8 s @16 kHz 样本环；满则 **drop-newest**
（保已排队播放连续，Realtime 突发时宁可丢尾）。起播预缓冲 6 帧（120 ms）。
C3 起播增加约 16 ms fade-in；预缓冲仍作起始值，真机可再测。`underrun`
为播放诊断，不中断会话、不参与 transport gating。

24 kHz 证据：OpenClaw 2026.7.1-2 `dist/talk-Caq_w59s.js` 创建 relay 时
`audioFormat = REALTIME_VOICE_AUDIO_FORMAT_PCM16_24KHZ`。

## 4. 二进制帧头（16 字节，小端）

| 偏移 | 大小 | 字段 |
| --- | --- | --- |
| 0 | 1 | magic `0xA5` |
| 1 | 1 | version `0` |
| 2 | 1 | flags：bit0=utterance 首帧，bit1=末帧 |
| 3 | 1 | reserved 0 |
| 4 | 4 | conversation_id u32 |
| 8 | 4 | seq u32 |
| 12 | 4 | ts_ms u32 |

未知 conversation 或已结束 conversation 的帧：静默丢弃 + 计数。

## 5. 设备状态

```text
IDLE → (wake/manual) LISTENING → UPSTREAMING → PLAYING
                  ↑                 │
                  └── follow-up ────┘
PLAYING → (local barge-in) INTERRUPTING → UPSTREAMING
any → ERROR → 重连 hello → IDLE
```

设备不实现 Agent conversation engine。

## 6. 控制消息

通用：`type`。涉及会话的带 `conversation_id`。错误：`code` + 可选 `message`。

### Device → Bridge

| type | 字段 | 语义 |
| --- | --- | --- |
| `hello` | `protocol`(=0), `device_id`, `fw_version`, `audio{sample_rate,channels,bits,frame_ms,codec}` | 能力声明 |
| `ping` / `pong` | `ts_ms` | 保活 |
| `wake` | `phrase?` | 本地唤醒（「你好 EVA」或测试按键） |
| `conversation_open` | `reason`(`wake`/`manual`) | 请求会话 |
| `speech_start` | `conversation_id` | 本 turn 采集开始 |
| `speech_end` | `conversation_id` | 本 turn **设备采集结束**。不是 Realtime commit。
  Bridge 在转发后注入 1000 ms @24 kHz 静音，供 server VAD 收尾 |
| `interrupt` | `conversation_id` | **已本地停播**；Bridge 对 Talk `cancelOutput` |
| `cancel` | `conversation_id`, `reason` | 作废当前会话 |
| `conversation_end` | `conversation_id`, `reason`(`timeout`/`user`/`error`) | 设备侧结束 |
| `error` | `code`, `message` | 设备错误 |

### Bridge → Device

| type | 字段 | 语义 |
| --- | --- | --- |
| `hello_ok` | `protocol`, `bridge`, `keepalive_ms` | 接受 |
| `hello_error` | `code` | 随后关闭 |
| `ping` / `pong` | `ts_ms` | 保活 |
| `conversation_opened` | `conversation_id`, `codec`, `frame_ms` | 会话建立（Talk session 已 ready 或即将 ready） |
| `conversation_reject` | `code`(`busy`/`backend_unavailable`/`invalid`) | 拒绝；设备不重试轰炸 |
| `playback_start` / `playback_end` | `conversation_id` | 下行边界 |
| `conversation_end` | `conversation_id`, `reason` | 任一方可发；接收方**不得回复** |
| `error` | `code`, `message` | 协议错误 |

错误码：`unsupported_version` `invalid_message` `unknown_conversation`
`busy` `backend_unavailable` `timeout` `internal`。未知 code 必须容忍。

## 7. 流程

### 唤醒后连续多轮

```text
Device                              Bridge                         Talk
  │ hello / hello_ok                 │                              │
  │ wake / conversation_open ───────▶│ talk.session.create ────────▶│
  │◀──── conversation_opened ────────│◀──── session.ready ──────────│
  │ speech_start + 16k PCM ─────────▶│ resample 24k appendAudio ───▶│
  │ speech_end ─────────────────────▶│ +1000 ms 24 kHz silence ────▶│
  │◀──── playback_start + 16k PCM ───│◀──── output.audio.delta ─────│
  │◀──── playback_end ───────────────│◀──── output.audio.done ──────│
  │   （同一 conversation，无需再唤醒） │                              │
  │ speech_start …                   │                              │
```

### Barge-in（本地先停）

```text
PLAYING 中用户开口
  → Device 立即停 ES8311、清播放队列
  → interrupt
  → Bridge talk.session.cancelOutput
  → speech_start + 新上行
  → 同 conversation 进入新 turn
```

「没事了」等结束语由 Realtime/EVA 判断；Bridge 收到会话结束事件后发
`conversation_end(completed)`。设备不硬编码中文结束词。

## 8. 保活、断线、恢复

- 默认 `keepalive_ms=10000`；2×周期+2 s 无 pong → 断开，指数退避重连
  （1 s 起、×2、上限 60 s、±20% 抖动）。
- 断线后 conversation 作废（v0 不恢复 Talk session）；重连后重新 hello。
- Bridge 重启 / Gateway 重启 / Wi-Fi 闪断：设备必须自行恢复。
  **不得设计成必须重启 ESP32。**
- **C5 recovery 已实现（`HW-ACCEPTANCE-PENDING`，automatic verification: PASS）**：bounded
  backoff 1s→60s、session invalidation、queue/VAD/playback reset、自动 hello。
  禁止 `ESP.restart()`、禁止无限高速重连。Gateway 掉线后不得复用 stale
  Talk sessionId。
- ESP32 断开：Bridge 关闭对应 Talk session 并清理映射。

## 9. 缓冲

- 上行 ring **C1 已实现**：100 帧 × 640 B = 64 KB ≈ 2 s @16 kHz；满则
  drop-oldest。1.5 s 阈值（75 帧 × 20 ms）按**每个 utterance / congestion
  window** 计算：`voice_txq_clear()` 开启新窗口。`dropped_total` 仅为
  lifetime diagnostic，不参与 transport gating；仅当前窗口 `dropped` ≥75
  才判 `transport_error` 并停止本 turn。
- `speech_end` 与 Realtime server VAD 的责任分层（C1 实测后冻结）：
  - 设备：只表示采集结束，不补静音，不感知 OpenAI VAD。
  - Bridge：Talk 无公开 commit API；C0 曾在 host fixture 人工追加 1 s
    静音。该依赖上收到 Bridge：`speech_end` 后追加 1000 ms pcm16@24k
    零样本，再交给 server VAD。可用
    `EVA_VOICE_BRIDGE_COMMIT_SILENCE_MS=0` 关闭（仅诊断）。
  - Realtime：仍负责 turn detection；Bridge 不重做主 VAD/AEC。
- 下行 ring **C2 已实现**：8 s @16 kHz；满则 drop-newest。
  Realtime 常在设备 5 s 采集窗结束前开始下行，因此采集期间**必须接收并
  播放**；不得因 `speaking` 丢弃下行。新 utterance 才清播放队列。
- **C3 barge-in 已实现**：仅 `PLAY_ACTIVE`，playback_start 后 400 ms 且
  `speech_end` 后 400 ms 才检测。holdoff 内学习 AEC 残差地板；之后残差
  ≥max(800, floor×3) 连续 4 帧才打断。命中或 BOOT 先把 ES8311 音量置 0
  再清队列。采集窗内立即 `interrupt` 并重开本 turn。迟到下行在下一
  `playback_start` 前丢弃。Bridge `suppress_downlink` 直到该次 `speech_end`。
   C3 正式验收是 BOOT 本地先停。**播放中 device-side VAD barge-in** 与
   **静音 follow-up LISTENING 下的 VAD** 不是同一场景：前者 C4 不要求证明；
   后者若被用来启动后续轮，则 C4 真机验收必须证明。不得把未做的真机 VAD
   测试写成 PASS。
- **C4 follow-up 已实现**：`playback_end` drain 后（或 `speech_end` 后
   2.5 s 仍无下行）进入 LISTENING，同一 `conversation_id` / Talk session
   等待下一轮 `speech_start`，不必再 `conversation_open`。监听窗 12 s，
   起听 holdoff 400 ms；超时设备发 `conversation_end(timeout)`。BOOT 只
   可替代首次 wake。后续轮由 device-side VAD 在静音 follow-up 窗内触发，
   不得再依赖 BOOT。
- interrupt/cancel/end 后清空上、下行队列；迟到旧 conversation 帧丢弃。
- 不得影响股票看板。

## 10. 兼容

新增可选字段不升版本；消息类型或语义变化升 `protocol`。
忽略未知字段与未知 type。OpenClaw 名称不得进入本协议。
