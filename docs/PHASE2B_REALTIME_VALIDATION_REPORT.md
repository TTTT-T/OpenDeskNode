# PHASE2B — OpenClaw GPT-Live Realtime Architecture Validation Report

状态：**DRAFT — R0/R1/R2 待执行**（模板先行；每项验证完成后回填，全部完成后
定稿并在 PROJECT_STATE 记录结论）。
分支：`phase-2b-realtime`；开题：2026-08-18。
阶段定义：[PHASE2B_GPT_LIVE_REALTIME_VALIDATION.md](PHASE2B_GPT_LIVE_REALTIME_VALIDATION.md)。

## 1. 实际使用的 OpenClaw Talk 配置

实际生效（2026-08-18 20:26 起，`~/.openclaw/openclaw.json`）：

```json
{
  "provider": "openai",
  "model": "gpt-realtime-2.1",
  "mode": "realtime",
  "transport": "gateway-relay",
  "brain": "agent-consult",
  "providers": { "openai": { "speakerVoice": "marin" } }
}
```

变更史：用户初始配置 `model=gpt-live-1-codex, transport=webrtc`；R0 webrtc
FAIL（400）→ R2 切 `gateway-relay` 后模型报错 → 隔离步骤换
`gpt-realtime-2.1` 后 R2 核心验证通过。

## 2. ChatGPT OAuth 与 API key 使用情况

- 认证 profile：`openai:terrencettt1996@gmail.com`（mode=oauth，2026-08-18
  08:22 授权）。
- **全程未使用 OpenAI Platform API key**；R2 成功 session 为 OAuth-only。
- 源码确认 OAuth 是 OpenClaw realtime 合法平台认证
  （`PLATFORM_AUTH_PROFILE_TYPES = ["api_key", "oauth"]`）。
- 未验证项：OAuth token 对模型/用量的长期稳定性；headless（无浏览器）场景
  的 token 维持方式（Bridge 阶段必须解决）。

## 3. R0 — Browser Realtime：FAIL（2026-08-18 19:48 首测，原因未定论）

| 项 | 结果 | 备注 |
| --- | --- | --- |
| 前置（Gateway 运行 / Control UI / 麦克风权限） | PASS | Gateway 18789 running，探针 ok；Control UI webchat 连接正常 |
| OAuth-only 会话建立（无 API key） | 部分 | OAuth profile `openai:terrencettt1996@gmail.com` (mode=oauth) 当日 08:22 授权成功；`talk.client.create` ✓（1193ms） |
| WebRTC 建立 | **FAIL** | 浏览器 JS 报 `Realtime WebRTC setup failed (400)` |
| 中文实时对话 / 延迟 / Barge-in | 未执行 | 阻塞于上一项 |

### 诊断记录（源码级，OpenClaw 2026.7.1-2）

- 失败点：浏览器直接 POST `https://api.openai.com/v1/realtime/calls`（SDP
  offer + Gateway 签发的 ephemeral clientSecret Bearer），OpenAI 返回 400。
  该请求不经过 Gateway，故 Gateway 日志无任何报错（已核 19:48–19:55 窗口）。
- 链路前段正常：`talk.client.create` ✓；OAuth 为 OpenClaw realtime 合法认证
  （`PLATFORM_AUTH_PROFILE_TYPES = ["api_key", "oauth"]`），排除"必须 API
  key"假设。
- 主要疑点：`gpt-live-1-codex` 在 OpenClaw dist 中零出现（内置默认
  `gpt-realtime-2.1`），自定义模型名随 session 下发，疑似 OpenAI 端拒绝。
  400 响应体未捕获（仅存在于浏览器 Network 面板，未留存）。
- 网络排除：Mac 直连 `api.openai.com` 正常（0.7 s）；Clash Verge 未运行与
  此无关（chatgpt.com 403 为另一独立现象，不影响 api.openai.com）。

### 处置决定（用户，2026-08-18）

R0 webrtc 路径不是 ESP32 产品路径，直接转 R2（gateway-relay）。R0 记 FAIL
（未定论），不静默跳过；若 R2 出现模型类错误，候选隔离步骤为临时换
`gpt-realtime-2.1` 复测（待用户批准，不属于本阶段范围变更）。

## 4. R1 — Agent Consult：部分 PASS（2026-08-18 20:42–20:43）

session `30d93db0-da54-49f5-952d-2328c1da2f97`（gateway-relay / agent-consult）。

| 项 | 结果 | 备注 |
| --- | --- | --- |
| consult 调用真实 EVA agent | **PASS** | 日志 `lane=session:agent:eva:main`；`runId=talk-call_TXlwVWfxNt6TpTTy-…` |
| durable memory 写入 | **PASS** | `workspace-eva/MEMORY.md` 20:43:02 写入「备用2号 = 蓝鲸7号」 |
| 跨渠道读回（Telegram 问暗号） | 待用户执行 | 写已证实；读回是剩余人工项 |
| tool 调用 | **PASS** | 多次 `tool.call`→`tool.result`；`exec.approval.waitDecision` + `resolve`；Telegram 出站 7612/7613 |
| EVA 主模型 | 降级成功 | `zai/glm-5.2` 返回 `401 令牌已过期`；failover 到 `deepseek-v4-flash` 后 `candidate_succeeded` |
| 浏览器声学 | **已知缺陷** | 扬声器回灌麦克风 → 自打断循环（20:43:15–20:43:46 密集 transcript/output 循环）；浏览器路径无硬件 AEC |

### 诊断记录

- agent-consult 链路成立：语音 → OpenAI Realtime → consult EVA agent → 工具/记忆。
- EVA 主模型 zai token 过期是独立运维问题，不否定 consult 架构；本次靠 fallback 完成。
- 自打断是**浏览器外放测试环境**的声学问题，不是协议失败。产品路径依赖 Phase 2A 已验收的 ESP32 硬件 AEC，此缺陷反向证明设备侧 AEC 的必要性。

## 5. R2 — Gateway Relay：核心验证 PASS（2026-08-18 20:26，gpt-realtime-2.1）

配置变更：`transport: webrtc → gateway-relay`（20:22:57）；模型隔离步骤
`model: gpt-live-1-codex → gpt-realtime-2.1`（20:26:03 热重载生效）。

| 项 | 结果 | 备注 |
| --- | --- | --- |
| OAuth-only + gateway-relay 会话建立（核心问题） | **PASS** | `session.ready`（realtime / gateway-relay / agent-consult / openai），sessionId `d668a102…`；ChatGPT OAuth、全程无 API key |
| 中文实时语音对话 | **PASS** | 用户确认测试通过；日志 20:26:36–20:26:52 多轮 `transcript.done`/`output.audio.done`/`output.text.done` |
| Barge-in | **PASS（≥1 次，日志证实）** | 20:26:46 `turn.cancelled`（talkFinal）后同 session 立即新 `turn.started`——播放中插话取消输出并开始新 turn |
| 会话正常关闭 | PASS | `session.closed`（talkFinal） |
| agent-consult 实际调用 EVA | 待 R1 显式验证 | brain=agent-consult 已在 session 参数中激活，但未做 memory/tool 交叉验证 |
| 延迟对比 vs webrtc | 未测（webrtc 路径未通过） | 主观体感待用户补充；后续可用日志时间戳量化 |

### 首测 FAIL 记录（20:23，保留为隔离证据）

`gpt-live-1-codex` 被OpenAI 拒绝：`Model "gpt-live-1-codex" is not supported in
realtime mode`。根因：该模型不在 platform realtime 支持列表（疑似 ChatGPT
消费端模型）。换 `gpt-realtime-2.1`（OpenClaw 内置默认）后即通——同时反推
R0 浏览器 webrtc 的 400 同根因。

### 关键架构结论

1. **R2 核心问题得到肯定答案**：ChatGPT OAuth-only 可以经 gateway-relay 建立
   realtime 语音 session，无需 OpenAI Platform API key。ESP32 Voice Bridge
   的传输前提成立。
2. **实际可用模型是 `gpt-realtime-2.1`**，不是 `gpt-live-1-codex`。架构图与
   文档中的"GPT-Live / gpt-live-1-codex"表述需统一修正。
3. OpenClaw relay 路径的服务端错误可完整落日志（对比浏览器路径 400 丢细节），
   适合作为 Bridge 的下游。

## 6. 总结判定

- R0：PENDING；R1：PENDING；R2：PENDING。
- 是否允许进入 ESP32 → Mac Voice Bridge 接口设计：PENDING（需三项全 PASS）。
- 结论与下一步架构决策：PENDING。

## 7. ESP32 Voice Bridge 下一阶段接口建议（R2 后填写）

待验证后填写。开题时列出的候选要点（非结论）：

- 传输：优先评估 `gateway-relay`（WebRTC 栈对 ESP32 过重）；R2 结论是关键
  输入。
- Bridge 职责边界：终结 ESP32 PCM（16 kHz/16-bit/mono）链路 ↔ OpenClaw
  Talk/Gateway 协议翻译；不做 STT/TTS/推理/agent 语义。
- ESP32 侧保留：WakeNet “你好 EVA”（模型待获取/训练）、VAD、AEC、本地
  barge-in 停播、Phase 2A 冻结音频基线。
- 待解决问题：headless bridge 的 OAuth 会话维持；GPT-Live 下行音频重采样
  至 16 kHz；会话映射与设备身份；LAN 发现与配置。
- 旧实验资产参考：`phase-2b-r` 分支的 VOICE_PROTOCOL v2（conversation/turn
  语义、barge-in 本地停播、有界缓冲）可作 Bridge 设备侧协议设计参考；未
  合并，按需评估。
