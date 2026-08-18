# Phase 2B — OpenClaw Talk Realtime Validation

- 日期：2026-08-18
- 结果：**Completed / Accepted for architecture progression**
- 详细证据：[PHASE2B_REALTIME_VALIDATION_REPORT.md](../PHASE2B_REALTIME_VALIDATION_REPORT.md)
- 规划（历史）：[PHASE2B_GPT_LIVE_REALTIME_VALIDATION.md](../PHASE2B_GPT_LIVE_REALTIME_VALIDATION.md)
- 决策：[ADR-0005](../decisions/0005-openclaw-realtime-gateway-relay.md)

## 结果

- R2 Gateway Relay：**PASS**（OAuth-only + `gpt-realtime-2.1` + 中文实时 + barge-in）。
- R1 Agent Consult：**PASS**（EVA 调用、MEMORY 写入、跨渠道读回、tool）。
- R0 Browser WebRTC：**FAIL**（`gpt-live-1-codex` 不支持 realtime）。
  **non-product path / non-blocking**。

已验证主链：`ChatGPT OAuth → OpenClaw Talk gateway-relay → gpt-realtime-2.1
→ agent-consult → EVA`。不需要 OpenAI Platform API key。

## 架构事实（不得退回）

- 正式模型：`gpt-realtime-2.1`。`gpt-live-1-codex` 不可用。
- 产品路径：OpenClaw `gateway-relay`，不是浏览器 WebRTC。
- OpenClaw Gateway 在 **Mac mini**，不是 NAS。
- 禁止再把 STT→OpenClaw→TTS 当作产品主链。
