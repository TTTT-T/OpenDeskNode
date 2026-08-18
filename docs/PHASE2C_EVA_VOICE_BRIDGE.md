# Phase 2C — EVA Voice Bridge Interface & Transport

状态：**进行中**（2026-08-18 开题）。结论以后续 `phase-reports/` 为准。
分支：`phase-2c-eva-voice-bridge`；基线 `4121dca`（`phase-2b-realtime` 文档收敛态）。
决策：[ADR-0005](decisions/0005-openclaw-realtime-gateway-relay.md)、
[ADR-0006](decisions/0006-eva-voice-bridge-thin-adapter.md)。
工作协议：[VOICE_BRIDGE_PROTOCOL.md](VOICE_BRIDGE_PROTOCOL.md)。

> 本阶段第一目标不是「把整个语音助手做完」，而是冻结
> ESP32 ↔ EVA Voice Bridge ↔ OpenClaw Talk 的接口，并证明最小双向实时
> 音频 transport 可以成立。

## 目标（单一）

冻结设备协议与音频合同，实现独立薄 Bridge，并用 C0–C5 证明：

```text
ESP32 Voice Edge ↔ EVA Voice Bridge ↔ OpenClaw Talk gateway-relay
  ↔ gpt-realtime-2.1 ↔ agent-consult ↔ EVA
```

可以建立 session、上下行 PCM、本地 barge-in、连续多轮与故障恢复。

## 非目标

禁止扩大到：完整智能家居产品化、Home Assistant 功能扩张、股票语音控制、
OTA、配置 Web UI、用户账户、云端设备管理、多设备 fleet、公网暴露、
自建 STT/TTS、本地大模型语音主链、ESP32 直连 OpenAI、重写 Phase 1 股票、
大规模 UI 改版。Wake 模型未最终选定不得阻塞 transport。

## 接口边界

| 层 | 职责 | 不做 |
| --- | --- | --- |
| ESP32 Voice Edge | 采集/播放、AEC、VAD、本地唤醒、本地立即停播、16 kHz PCM | STT/TTS/LLM/Agent/OpenClaw 协议 |
| EVA Voice Bridge | 连接、framing、session 映射、事件翻译、buffer、16↔24 kHz 重采样、health | STT/TTS/LLM/tools/memory/HA/日历 |
| OpenClaw Gateway | Talk session、gateway-relay、OAuth、consult | 设备 PCM 协议、股票 |
| OpenAI Realtime | 听/说/server VAD/连续对话/打断 | 设备声学 |
| EVA Agent | 记忆/工具/自动化 | 音频边缘 |

两个 VAD 层级必须分开写：

- **设备 VAD**：决定何时上行、何时本地 barge-in 停播。
- **Realtime server VAD / turn detection**：云端 conversation behavior。
  Bridge 不重做第二套主 VAD/AEC。

## 已调查：OpenClaw Talk 音频合同（2026.7.1-2）

来源：本机 `/opt/homebrew/lib/node_modules/openclaw`，不是猜测。

| 项 | 结论 | 出处 |
| --- | --- | --- |
| 创建 session | `talk.session.create({ mode:"realtime", transport:"gateway-relay", brain:"agent-consult" })` | `docs/gateway/protocol.md`、`docs/plugins/sdk-migration.md` |
| 上行 | `talk.session.appendAudio({ sessionId, audioBase64, timestamp? })`；base64 PCM | 同上；`dist/talk-Caq_w59s.js` |
| 下行 | `talk.event` / relay `type:"audio"` + `audioBase64`；对应 `output.audio.delta` | `dist/talk-Caq_w59s.js` |
| 取消输出 | `talk.session.cancelOutput`（barge-in）；`talk.session.cancelTurn` | protocol.md |
| 关闭 | `talk.session.close` | protocol.md |
| **硬编码格式** | 创建 relay 时 `audioFormat = pcm16 / 24000 Hz / mono` | `dist/talk-Caq_w59s.js` L262 |
| Provider 能力 | OpenAI 声明 pcm16@24k 与 g711_ulaw@8k | `dist/realtime-voice-provider-CS4oALRb.js` |
| 设备基线 | 16 kHz / 16-bit / mono PCM（Phase 2A） | PHASE2A_REPORT |
| **重采样** | **必须由 Bridge 做 16k ↔ 24k** | 上述两端不一致 |

endianness：Talk 侧按 raw PCM buffer + base64，与 OpenAI realtime pcm16
一致，按 **little-endian signed 16-bit** 处理。设备协议同样 s16le。

## 连续对话语义

```text
「你好 EVA」→ 本地唤醒 → session active → 用户说话 → Realtime → 下行播放
→ 回答后继续等待一段时间 → 可直接下一轮，不必再唤醒
```

结束可由：本地/语义超时、用户说「没事了」等自然结束（由 Realtime/EVA
判断，不在 ESP32 硬编码中文结束词）、显式 cancel、网络故障。

Barge-in：

```text
assistant speaking → 用户开口 → ESP32 立即停 ES8311
→ Bridge 发 cancelOutput → Realtime 取消输出 → 新 input turn
```

**本地停播不能等待云端返回。**

设备有限状态：`IDLE | LISTENING | UPSTREAMING | PLAYING | INTERRUPTING | ERROR`。
不在设备侧重造 Agent conversation engine。

## 预计模块

- `docs/VOICE_BRIDGE_PROTOCOL.md`：设备协议草案。
- `bridge/`（本阶段后半实现）：独立薄服务。建议具备 device connection、
  session registry、audio up/down、Talk client、event translation、
  health endpoint、structured logs、reconnect、metrics。
- `firmware/product/components/voice/`：仅在 C1 起需要时增量加入 transport；
  不得破坏 2A `components/audio/`。
- 测试：host PCM fixture（C0）、协议单测、2A/1E 回归。

旧 `dev` / `phase-2b-r` 的 VOICE_PROTOCOL 只作设计参考，不整体 merge。

## 未知项

| 项 | 分类 |
| --- | --- |
| 1. `talk.session.create` / realtime Talk 真实接口 | **2C 必须**（已从源码确认形状；C0 实测） |
| 2. gateway-relay audio ingress | **2C 必须**（base64 pcm16@24k） |
| 3. gateway-relay audio egress | **2C 必须**（`output.audio.delta` / audioBase64） |
| 4. output sample rate | **2C 必须**（24 kHz，源码硬编码） |
| 5. 是否必须 resample | **2C 必须**（是，Bridge 负责） |
| 6. event / cancellation semantics | **2C 必须**（`cancelOutput` / `cancelTurn` / `turn.cancelled`） |
| 7. reconnect semantics | **2C 必须**（设备重连不得要求重启 ESP32） |
| 8. session recovery | **可推迟**（草案：断线作废 session，重新 hello） |
| 9. OAuth token 生命周期 | **可推迟**（记录；C0 用现有已登录 Gateway） |
| 10. headless OAuth renew | **可推迟**（运维项，不阻塞 transport） |
| 11. Gateway restart 后 Bridge 行为 | **2C 必须**（C5） |
| 12. ESP32 disconnect 后 session cleanup | **2C 必须**（C5） |
| 13. LAN device discovery | **可推迟** |
| 14. device authentication | **可推迟**（LAN-only；协议预留字段） |
| 15. 「你好 EVA」WakeNet 模型 | **可推迟**（可拆 2C.x；C4 可用按键/fixture 代替唤醒） |

## 验收矩阵

| ID | 链 | PASS |
| --- | --- | --- |
| C0 | Bridge → Talk → gpt-realtime-2.1 → audio → Bridge（host PCM / fixture，不接 ESP32） | 稳定建 session，上下行 audio/event |
| C1 | ESP32 mic → AEC/VAD → Bridge → Realtime | 真人中文进入 realtime |
| C2 | Realtime audio → Bridge → ESP32 → ES8311 | 设备可播放回答 |
| C3 | EVA 说话 → 用户插话 → 本地立即停播 → cancel → 新 turn | 必须成功 |
| C4 | 唤醒一次后多轮连续对话 | 不必每轮再唤醒（可用按键代替 wake） |
| C5 | Bridge restart / Gateway restart / ESP32 Wi-Fi 断连重连 / session 异常关闭 | 不得必须重启 ESP32 才能恢复 |

性能先测量、不写死：wake→session ready、speech end→first assistant audio、
barge-in→speaker stop、reconnect、up/down buffer、丢包、heap、PSRAM、
queue depth、underrun/overrun。

## 风险与回滚

- Talk API / OpenClaw 小版本变化由 Bridge 吸收，不得写入固件硬件协议。
- 24 kHz 重采样质量未知。
- OAuth headless 未验证；C0 依赖已有 Mac Gateway 会话。
- 回滚点：`4121dca`。失败只回退本分支 2C 新增文件与文档，不 reset 用户工作，
  不删除 `dev` / `phase-2b-r`。

## 实现顺序（本开题之后）

1. 冻结协议草案与音频合同（本文 + VOICE_BRIDGE_PROTOCOL）。
2. C0：Mac 上最小 Bridge skeleton + host fixture。
3. C1/C2：ESP32 transport 增量接入 2A 音频。
4. C3/C4/C5。
5. Wake PoC 不阻塞；做不完拆 Phase 2C.x。
