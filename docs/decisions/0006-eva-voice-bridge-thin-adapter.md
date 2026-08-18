# ADR-0006：采用 EVA Voice Bridge 薄协议/音频桥，废弃 Compute Node 语音主链

- 状态：Accepted
- 日期：2026-08-18
- 决策者：项目用户与 opencode
- 关联：细化 [ADR-0005](0005-openclaw-realtime-gateway-relay.md) 的 Mac 侧部署边界；
  不改变 ADR-0004 固件基底、不改变 ADR-0002 Stock 边界。
- 证据：[PHASE2B_REALTIME_VALIDATION_REPORT.md](../PHASE2B_REALTIME_VALIDATION_REPORT.md)
- 编号说明：本分支下一号为 0006。历史分支 `dev`/`phase-2b-r` 上的
  `0006-unified-gateway-and-mac-ai-node.md`（Mac 本地 ASR/LLM/TTS Compute Node）
  与 `0007-eva-openclaw-agent-runtime-voice-edge.md`（NAS Adapter）**不是本文件**，
  且已被本决定替代。见 [DOCUMENT_INDEX.md](../DOCUMENT_INDEX.md)。

## 背景与需要解决的问题

此前曾考虑：

```text
ESP32 → Mac local ASR → OpenClaw / LLM → local TTS
```

以及把 NAS Stock Gateway 演进为统一 OpenDeskNode Gateway、Mac 只当 Compute
Node。随后 Phase 2B 对 OpenClaw Talk realtime 做了真实验证。需要把「薄桥」
与「OpenClaw Gateway」在架构层分开，并正式废弃已被否决的语音主链。

## 已确认事实和约束

- Phase 2A 已验收：ES7210 双麦、ES8311、16 kHz/16-bit PCM、AEC、录音/播放。
- Phase 2B 已验证主链：ChatGPT OAuth → OpenClaw Talk `gateway-relay` →
  `gpt-realtime-2.1` → `agent-consult` → EVA（memory / tools）。
- `gpt-live-1-codex` 不可用于 OpenAI Platform realtime。
- 浏览器 WebRTC R0 FAIL，且不是产品路径。
- OpenClaw Gateway 实测在 **Mac mini**（`127.0.0.1:18789`）。
- OpenClaw 2026.7.1-2 源码确认：`gateway-relay` 创建桥时硬编码
  `audioFormat = pcm16 / 24000 Hz / mono`；`talk.session.appendAudio` 接受
  base64 PCM；下行经 `output.audio.delta` / `audioBase64` 返回。
- 股票看板仍是产品核心；Voice 故障不得拖垮 Stock。

## 候选方案

1. Mac 本地 ASR / LLM / TTS Compute Node（历史 ADR-0006）。
2. NAS 统一 Gateway + NAS OpenClaw Adapter（历史 ADR-0007）。
3. ESP32 直连 OpenAI 或直连 OpenClaw 协议。
4. **ESP32 Voice Edge → EVA Voice Bridge → Mac OpenClaw Gateway →
   gateway-relay → gpt-realtime-2.1 → agent-consult → EVA**（本决定）。

## 决定

采用：

```text
ESP32 Voice Edge
  → EVA Voice Bridge
  → OpenClaw Gateway
  → gateway-relay
  → gpt-realtime-2.1
  → agent-consult
  → EVA
```

### EVA Voice Bridge（薄协议/音频桥）

独立服务，物理上可与 OpenClaw Gateway 同机（当前 Mac mini），架构层必须分离。

负责：ESP32 连接、PCM framing、session 映射、turn/event 翻译、buffering、
16 kHz↔24 kHz 重采样、health / reconnect。

**不负责**：STT、TTS、LLM、Tool routing、Memory、Agent reasoning、
Home Assistant、日历、股票业务。

### OpenClaw Gateway

OpenClaw 自身的 Agent / Talk 基础设施。当前已验证实例在 Mac mini。
将来迁回 NAS 只是 Future / unvalidated deployment option，不能冒充当前架构。

### 股票与语音继续解耦

```text
ESP32
  ├── Stock UI → NAS Stock Gateway
  └── Voice Edge → Mac Voice Bridge → Mac OpenClaw Gateway
```

Stock Gateway 与 OpenClaw Gateway 是不同服务。不为「统一 Gateway」合并二者。
统一服务发现/认证/设备注册若需要，另开 ADR。

### 设备侧保留

AEC、VAD、本地唤醒「你好 EVA」、本地 barge-in 立即停播、16 kHz PCM 传输。
Realtime 的 server VAD / turn detection 是云端 conversation behavior，
与设备 VAD 不是同一概念。

## 放弃其他方案的原因

- 方案 1：用户否决；会复制 EVA 的记忆/工具，且与已验证 realtime 主链冲突。
- 方案 2：把语音再绕回 NAS，与已验证的 Mac OpenClaw Talk 路径重复。
- 方案 3：把演进中的外部协议或第三方凭据下沉到 MCU，违反 ADR-0002/0004/0005。

不再开发：streaming STT pipeline、streaming TTS pipeline、Mac 本地 LLM
语音主链、Whisper 主链、ESP32 直连 OpenAI、ESP32 承担 OpenClaw 协议、
ESP32 本地运行 LLM。

## 代价、风险和后果

- Bridge 必须做 16 kHz ↔ 24 kHz 重采样；质量与延迟在 Phase 2C 实测，不先写死。
- headless ChatGPT OAuth 续期仍未验证。
- 设备协议不照搬旧 `VOICE_PROTOCOL` v1/v2；可参考其 conversation/turn/barge-in
  语义，但 endpoint 是 Mac Bridge 而不是 NAS Gateway。
- `dev` 与 `phase-2b-r` 继续作为 historical reference，不删除、不 merge。

## 重新评估的触发条件

- headless OAuth 无法维持；
- `gpt-realtime-2.1` 或 `gateway-relay` 不可用；
- 重采样/延迟使对话不可用；
- 用户重新定义 EVA 与 OpenDeskNode 的关系。

## 对架构、代码、测试和迁移的影响

- 更新 ARCHITECTURE / DECISIONS / PRODUCT_REQUIREMENTS / ROADMAP / PROJECT_STATE。
- Phase 2C 只冻结 ESP32 ↔ Bridge ↔ Talk 接口，并证明最小双向实时音频 transport。
- 不自建 STT/TTS，不改股票系统，不把 OpenClaw 协议写入固件。
