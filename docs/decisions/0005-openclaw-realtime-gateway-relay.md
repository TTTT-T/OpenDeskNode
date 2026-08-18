# ADR-0005：语音主链为 OpenClaw Talk gateway-relay + OpenAI Realtime + EVA consult

- 状态：Accepted
- 日期：2026-08-18
- 决策者：项目用户与 opencode
- 关联：细化 [ADR-0004](0004-clean-product-firmware.md) 的语音后端路径（原表述
  “自有 Voice Gateway + OpenAI Realtime API”）；不改变 ADR-0004 的固件基底，
  不改变 [ADR-0002](0002-product-and-stock-boundaries.md) 的 Stock 边界。
  Bridge 与 Gateway 分离、废弃 Compute Node 主链见
  [ADR-0006](0006-eva-voice-bridge-thin-adapter.md)。
- 证据：[PHASE2B_REALTIME_VALIDATION_REPORT.md](../PHASE2B_REALTIME_VALIDATION_REPORT.md)

## 背景与需要解决的问题

Phase 2A 已验收音频硬件基线。原 ADR-0004 假定 NAS 上自建 Voice Gateway 并直连
OpenAI Realtime。用户于 2026-08-18 冻结新方向：实时听说由 OpenAI Realtime
承担，复杂推理/记忆/工具由 OpenClaw EVA 承担；ESP32 只做音频边缘。Phase 2B
用受控 R0/R1/R2 验证该主链。

## 已确认事实和约束

- OpenClaw Gateway 实测运行在 **Mac mini**（`127.0.0.1:18789`，bind=loopback），
  不是 NAS。NAS 上的是 OpenDeskNode **Stock Gateway**（`terrencenas.local:8000`）。
  二者不得混称。
- ChatGPT OAuth（无 Platform API key）可驱动 OpenClaw Talk。
- `gpt-live-1-codex` 被 OpenAI 拒绝：`not supported in realtime mode`。
- 可用组合：`model=gpt-realtime-2.1`、`transport=gateway-relay`、
  `brain=agent-consult`、`mode=realtime`。
- R1：consult 调用 `eva` agent；MEMORY.md 写入；Telegram 跨渠道读回；tool 执行。
- 浏览器外放无硬件 AEC，出现自打断；产品路径依赖 Phase 2A ESP32 AEC。
- ESP32 不持有第三方 Key，不直连 OpenAI，不实现 OpenClaw 协议。

## 候选方案

1. NAS 自建 Voice Gateway + OpenAI Realtime（ADR-0004 原路径）。
2. 浏览器 WebRTC 直连 OpenAI（R0）：失败（模型/路径不适合 ESP32）。
3. 自建 STT → OpenClaw → TTS：用户否决。
4. **Mac 薄 Voice Bridge + OpenClaw Talk gateway-relay + OpenAI Realtime +
   EVA consult**（本决定）。

## 决定

- 实时听说/VAD/连续对话/打断：OpenAI Realtime `gpt-realtime-2.1`。
- 人格/记忆/工具/行动：OpenClaw `eva` agent，经 `openclaw_agent_consult`。
- 传输：OpenClaw Talk `gateway-relay`（`talk.session.create`）。不把 WebRTC
  下沉到 ESP32。
- 认证：ChatGPT OAuth-only（已验证）；不把 Platform API key 写入固件或文档。
- Mac mini 承载 OpenClaw Gateway 与未来 EVA Voice Bridge（薄：PCM ↔ Talk）。
- NAS 只继续承载 Stock Gateway；语音流量不经过 Stock 服务。
- ESP32 只保留：采集/播放、AEC、VAD、本地唤醒「你好 EVA」、有界 PCM 传输。

## 放弃其他方案的原因

- 方案 1 在 NAS 重造 Voice Gateway，与已运行的 OpenClaw Talk 重复。
- 方案 2 的 `/v1/realtime/calls` 浏览器路径对 ESP32 不可用，且 R0 已 FAIL。
- 方案 3 被用户明确否决，且会复制 EVA 的记忆/工具。

## 代价、风险和后果

- headless Bridge 如何维持 OAuth 会话尚未验证，必须在 Bridge 阶段单独解决。
- 下行音频重采样到 16 kHz 未验证。
- EVA 主模型（zai）token 过期是运维项；consult 已证明可 fallback，但不等于
  主模型健康。
- OpenClaw/OpenAI API 演进由 Mac 侧吸收，不得固化进 ESP32 硬件协议。

## 重新评估的触发条件

- OAuth-only 在 headless 下无法维持；
- `gpt-realtime-2.1` 下线或质量不可用；
- gateway-relay 延迟使对话不可用；
- 用户重新定义 EVA 与 OpenDeskNode 的关系。

## 对架构、代码、测试和迁移的影响

- 更新 ARCHITECTURE / DECISIONS / PRODUCT_REQUIREMENTS / ROADMAP / PROJECT_STATE。
- 下一阶段只设计 ESP32 ↔ Mac Voice Bridge；不自建 STT/TTS，不直连 OpenAI。
- `phase-2b-r` 的 VOICE_PROTOCOL v2 仅作设备侧协议参考，不自动合并。
