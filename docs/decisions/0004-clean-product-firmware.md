# ADR-0004：Xiaozhi 冻结为 reference，产品采用独立 ESP-IDF 固件

- 状态：Accepted
- 日期：2026-08-15
- 决策者：项目用户与 Codex
- 替代：[ADR-0001](0001-xiaozhi-upstream-integration.md) 的产品基底决策和 [ADR-0003](0003-v1-voice-pipeline.md)

## 背景与证据

Phase 1B 已证明 Xiaozhi v2.4.2 可在目标板启动，并验证 RLCD、BOOT 与 Wi-Fi 基础链路。但 Xiaozhi Application 同时携带官方激活、OTA、业务协议和云端 ASR/LLM/TTS 架构，与产品“本地唤醒 + 自有 Voice Gateway + OpenAI Realtime”目标不一致。

## 候选方案

- 继续在 Xiaozhi Application 上删减官方云：起步快，但会长期继承其状态机、协议和升级耦合。
- 整包复制后逐步重写：来源与依赖难以审查，容易无意保留云端路径。
- 冻结 Xiaozhi 为硬件参考，建立独立 ESP-IDF 工程，只按需迁移底层实现。

## 决定

- 保留 `firmware/xiaozhi/` 和已验收历史，用 annotated tag `phase-1b-xiaozhi-reference` 标记参考基线。
- 正式产品只在独立 `firmware/product/` ESP-IDF 工程上发展。
- 允许参考硬件参数、Waveshare 板级实现、ESP-IDF/Espressif 组件与已验证的底层驱动；每次迁移必须记录来源和依赖。
- 不迁移 Xiaozhi Application、激活、OTA、业务协议、MCP 或云端 ASR/LLM/TTS。
- 语音目标路径改为本地唤醒词 + OpenAI Realtime；后端编排由 [ADR-0005](0005-openclaw-realtime-gateway-relay.md) 定为 OpenClaw Talk `gateway-relay` + EVA consult，不再自建 NAS Voice Gateway。

## 后果与风险

- 产品运行时与 Xiaozhi 官方平台解耦，模块边界和凭据边界可自主设计。
- 已验收 Xiaozhi 代码不丢失，但新固件需逐项重建并真机验收板级与音频能力。
- 任何为了快速跑通而引入上层 Xiaozhi 组件的做法都需先停止并重评架构。

## 重评触发条件

只有在正式固件无法以可维护方式独立驱动硬件，或新的实测证据证明自有语音路径不可行时，才创建新 ADR 重评；不回写本记录。
