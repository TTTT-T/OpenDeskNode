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

## 3. R0 — Browser Realtime：PENDING

| 项 | 结果 | 备注 |
| --- | --- | --- |
| 前置（Gateway 运行 / Control UI / 麦克风权限） | PENDING | |
| OAuth-only 会话建立（无 API key） | PENDING | |
| 中文实时对话 ≥2 min / ≥5 轮连续 | PENDING | |
| 首响应延迟 | PENDING | 秒表粗测 + 日志时间戳 |
| 轮间延迟 | PENDING | |
| Barge-in ≥3 次（成功次数） | PENDING | |

错误与日志摘要：PENDING

## 4. R1 — Agent Consult：PENDING

| 项 | 结果 | 备注 |
| --- | --- | --- |
| `openclaw_agent_consult` 触发证据（Gateway 日志） | PENDING | |
| durable memory 跨渠道一致（语音 ↔ 文本） | PENDING | 暗号测试 |
| tool 调用成功（≥1 次） | PENDING | 实际 tool：PENDING |
| 回答体现 EVA 人格/记忆 | PENDING | |

错误与日志摘要：PENDING

## 5. R2 — Gateway Relay：PENDING

配置变更：`transport: webrtc → gateway-relay`（其余不变）。

| 项 | 结果 | 备注 |
| --- | --- | --- |
| OAuth-only + gateway-relay 会话建立 | PENDING | 核心问题 |
| 中文实时语音 / 连续对话 | PENDING | |
| Barge-in | PENDING | |
| agent-consult | PENDING | |
| 延迟对比 vs webrtc | PENDING | |

错误与日志摘要：PENDING

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
