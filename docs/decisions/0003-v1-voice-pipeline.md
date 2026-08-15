# ADR-0003：v1 采用 Xiaozhi ASR → GPT → TTS

- 状态：Superseded by [ADR-0004](0004-clean-product-firmware.md)
- 日期：2026-08-13
- 决策者：项目用户与 Codex

> 历史保留：Xiaozhi 协议和 Xiaozhi Server 不再是产品语音路径；新目标是本地唤醒与自有 Voice Gateway 接入 OpenAI Realtime API。

## 背景

目标是使用真正的 OpenAI GPT 和股票工具，同时保留可靠的设备语音体验。Xiaozhi 固件与服务端已经提供 Opus、WebSocket、ASR、LLM、TTS、工具和 MCP；OpenAI Realtime 能进一步降低延迟，但会同时引入桥接、双向音频、会话和工具协议的新复杂度。

## 决定

v1 复用 Xiaozhi 固件协议和 `xiaozhi-esp32-server` 的可插拔链路，先实现并独立验收 ASR → OpenAI GPT → TTS。股票工具在后续 Phase 7 接入统一 Stock Service。OpenAI Realtime 作为独立 Future Phase，不与股票、RLCD 或基础语音同时开发。

服务端 v0.9.6 的 OpenAI-compatible Provider 当前使用 Chat Completions。Phase 6 应先验证真正 OpenAI endpoint、模型、流式文本和 function calling；是否迁移到 Responses API 由兼容性与测试决定，不把“OpenAI-compatible”自动等同于当前官方最佳实践。

## 后果

- ASR、LLM、TTS 和工具可分段观测与替换，首版故障定位更直接。
- 相比端到端 Realtime，交互延迟可能更高；这是 v1 接受的代价。
- 设备侧 AEC 基础能力在 Phase 1 验证，不把全双工 Realtime 作为 AEC 验收前提。

## 重评条件

v1 语音稳定通过后，若端到端延迟仍不满足明确目标，且 Realtime 的模型、成本、音频格式和 function calling 均有原型证据，再创建 Realtime ADR；不得直接修改本 ADR 历史结论。
