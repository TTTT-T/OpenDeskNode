# PHASE2B — OpenClaw GPT-Live Realtime Architecture Validation Report

状态：**DRAFT — R0/R1/R2 待执行**（模板先行；每项验证完成后回填，全部完成后
定稿并在 PROJECT_STATE 记录结论）。
分支：`phase-2b-realtime`；开题：2026-08-18。
阶段定义：[PHASE2B_GPT_LIVE_REALTIME_VALIDATION.md](PHASE2B_GPT_LIVE_REALTIME_VALIDATION.md)。

## 1. 实际使用的 OpenClaw Talk 配置

PENDING（R0 执行时从 OpenClaw 导出实际生效配置，含版本与所在主机）。
用户提供的初始配置（2026-08-18）：

```json
{
  "provider": "openai",
  "providers": {
    "openai": {
      "speakerVoice": "marin"
    }
  },
  "model": "gpt-live-1-codex",
  "mode": "realtime",
  "transport": "webrtc",
  "brain": "agent-consult"
}
```

## 2. ChatGPT OAuth 与 API key 使用情况

- 计划：ChatGPT OAuth 登录；不使用 OpenAI Platform API key。
- 实际：PENDING（登录方式、账号类型、是否出现 key 要求、token 续期行为、
  headless 可行性观察）。

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

## 4. R1 — Agent Consult：PENDING

| 项 | 结果 | 备注 |
| --- | --- | --- |
| `openclaw_agent_consult` 触发证据（Gateway 日志） | PENDING | |
| durable memory 跨渠道一致（语音 ↔ 文本） | PENDING | 暗号测试 |
| tool 调用成功（≥1 次） | PENDING | 实际 tool：PENDING |
| 回答体现 EVA 人格/记忆 | PENDING | |

错误与日志摘要：PENDING

## 5. R2 — Gateway Relay：FAIL（2026-08-18 20:23 首测，模型不支持）

配置变更：`transport: webrtc → gateway-relay`（20:22:57 热重载生效，其余不变）。

| 项 | 结果 | 备注 |
| --- | --- | --- |
| transport 切换生效 | PASS | Gateway 日志 `config change detected (talk.realtime.transport)`；relay 模式正确要求 `talk.session.create`（UI 误发 `talk.client.create` 被引导纠正） |
| OAuth-only 会话建立 | 强指示 PASS | 请求已通过认证到达 OpenAI 模型校验层（返回模型级 400 而非 401） |
| GPT-Live session 建立 | **FAIL** | OpenAI 报错（UI 捕获）：`Model "gpt-live-1-codex" is not supported in realtime mode. See https://platform.openai.com/docs/models for a list of supported models.` |
| 中文实时语音 / Barge-in / consult | 未执行 | 阻塞于上一项 |

### 诊断记录

- 根因确认：`gpt-live-1-codex` 不在 OpenAI platform realtime 支持模型列表内
  （该名称疑似 ChatGPT 消费端模型，未对 platform realtime API 开放）。
- **R0 的 400 同根因**：浏览器路径丢失了响应体，R2 relay 路径拿回了完整错误。
- 正面信号：OAuth-only（ChatGPT 登录、无 API key）已推进到模型校验层，
  R2 核心问题（OAuth 能否建立 GPT-Live session）的障碍是模型可用性而非认证。
- 下一步（预批准的隔离步骤）：`openclaw config set talk.realtime.model
  gpt-realtime-2.1`（OpenClaw 内置默认 realtime 模型）复测 R2；若 OAuth
  token 对该模型无权限（计费/访问差异），则 OAuth-only 结论需要修正。

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
