# Phase 2B — OpenClaw GPT-Live Realtime Architecture Validation（阶段定义）

> **Historical phase definition** — 开题计划，不是当前架构事实源。
> 状态：**Completed / Accepted for architecture progression**。
> 短报告：[phase-02b-realtime-validation.md](phase-reports/phase-02b-realtime-validation.md)；
> 详细证据：[PHASE2B_REALTIME_VALIDATION_REPORT.md](PHASE2B_REALTIME_VALIDATION_REPORT.md)。

日期：2026-08-18；分支 `phase-2b-realtime`。
本文保留开题时的验证计划，其中若干假设已被实测修正，**不回写为当时已知**：

- OpenClaw Gateway 在 **Mac mini**，不是 NAS（NAS 是 Stock Gateway）。
- 可用模型是 `gpt-realtime-2.1`，不是 `gpt-live-1-codex`。
- R0 浏览器 WebRTC FAIL；产品路径以 R2 `gateway-relay` 为准。
- 正式决策见 [ADR-0005](decisions/0005-openclaw-realtime-gateway-relay.md)。

## 背景：2026-08-18 方向冻结

用户冻结新的语音总体架构，并暂停旧路线：一切基于 “STT → OpenClaw → TTS”
（含自建 AI backend、本地 Whisper/STT 主链、旧 Voice Gateway）的开发停止。
Phase 2A 已验收的语音硬件基线保留，并重新作为开发起点。

```text
ESP32-S3
├─ ES7210 双麦
├─ AEC
├─ VAD
├─ 本地唤醒词 “你好 EVA”
├─ ES8311 扬声器
└─ PCM 音频收发
        │
        ▼
Mac mini
EVA Voice Bridge（薄桥：ESP32 音频协议 ↔ OpenClaw Talk/Gateway）
        │
        ▼
OpenClaw Gateway（NAS）
        │
        ▼
GPT-Live（gpt-live-1-codex）
        │
        ├─ 普通实时语音对话（听/说/VAD/连续对话/打断）
        │
        └─ openclaw_agent_consult
                   │
                   ▼
            OpenClaw EVA Agent
            memory / tools / HA / calendar / automation …
```

职责边界（冻结）：

- **GPT-Live**：实时听、说、VAD、连续对话和打断。
- **OpenClaw EVA Agent**：复杂推理、长期记忆、工具调用和实际行动。
- **ESP32**：不承担 STT、TTS、LLM 或 Agent。
- **Mac mini Voice Bridge**：尽可能薄，只做 ESP32 音频协议与 OpenClaw
  Talk/Gateway 之间的桥接。
- **NAS**：继续运行 OpenClaw Gateway。

用户已在 OpenClaw 中配置 Talk（初始值，实际生效配置以 R0 执行时导出为准）：

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

## 目标（单一）

验证新的 Realtime 主链是否成立（R0/R1/R2），形成测试报告与下一阶段
（ESP32 → Mac Voice Bridge）架构决策依据。**本阶段不实现任何产品语音功能，
不写 ESP32 接入代码。**

## 非目标与禁止（R0–R2 全部 PASS 前）

- 禁止：自建 streaming STT；自建 TTS；Whisper/本地 ASR 主链；复活旧 Voice
  Gateway；ESP32 直连 OpenAI；ESP32 直接承担 OpenClaw 协议；为尚未验证的
  最终架构做大规模重构。
- 不做 ESP32 接入开发；不开始 WakeNet “你好 EVA” 模型选型/训练；不做屏幕
  Voice UI。
- 不修改、不重写 Phase 2A 已验收基线（见下节清单）。
- 在 R0–R2 结果出来前不自行扩大范围。

## Phase 2A 保留基线（不得破坏）

双麦采集（ES7210）；ES8311 扬声器；16 kHz / 16-bit PCM 基线；AEC；
录音/播放测试；稳定性基线。证据见
[PHASE2A_REPORT.md](PHASE2A_REPORT.md)。

## 旧架构实验资产（保留、不删除、不合并）

Phase 2A 之后已在其他分支产生的开发全部保留在原分支，不合并不改写：

- `dev`（`45bc6f8`）：旧 Phase 2B（VOICE_PROTOCOL v1 + Mock Gateway，软件完成）
  及文档重组。
- `phase-2b-r`（`9cd984b`）：ADR-0007 Voice Edge 重构与 VOICE_PROTOCOL v2
  （软件完成即被本方向取代）。

除非 R0–R2 结论确认其与新架构兼容（例如 v2 协议的 conversation/turn 语义
作为 Bridge 设备侧协议参考），不并入本分支。

## 验证项定义与 PASS 判据

R0–R2 均为用户人工执行项（Mac 浏览器 + ChatGPT OAuth + 真人中文语音）；
Agent 负责前置检查、记录模板、结果分析与报告定稿。

### R0 — Browser Realtime（基础可用性）

环境：Mac 浏览器 + OpenClaw Control UI；`gpt-live-1-codex`；
`transport=webrtc`；ChatGPT OAuth 登录；**不使用 OpenAI Platform API key**。

步骤：

1. 前置：确认 NAS 上 OpenClaw Gateway 运行、Control UI 可达、Talk 配置如
   上；浏览器授予麦克风/扬声器权限。
2. 使用 ChatGPT 账号完成 OAuth 登录。若任何环节要求 Platform API key，
   记录为关键发现（OAuth-only 目标失败点）。
3. 中文实时语音对话 ≥ 2 分钟，连续 ≥ 5 轮，不重新连接。
4. 记录延迟：首响应（说完 → 开始听到回答）与轮间间隔（秒表粗测 +
   日志时间戳）。
5. Barge-in ≥ 3 次：播放中直接插话，观察是否立即停止输出并回应新问题。

PASS 判据：OAuth-only 建立会话；中文实时对话连续可用；barge-in ≥ 2/3 成功；
无阻断性错误。记录错误现象、浏览器控制台与 OpenClaw Gateway 日志摘录。

### R1 — Agent Consult（EVA 真实接入）

步骤：

1. 语音会话中让 EVA 记住一个新事实（自选暗号）。
2. 语音中触发一次 tool（EVA 已配置的任一 tool：HA/日历/搜索等，按实际配置选）。
3. 结束语音会话后，在既有 EVA 文本渠道（Telegram/Web 等）验证同一记忆可读
   （durable memory 共享）。
4. 在 OpenClaw Gateway 日志中确认 `openclaw_agent_consult` / agent session
   创建证据。

PASS 判据：consult 确认调用真实 EVA agent；memory 跨渠道一致；至少一次
tool 调用成功；语音回答体现 EVA 人格/记忆而非裸 GPT-Live。

### R2 — Gateway Relay（ESP32 候选传输）

步骤：

1. 将 `transport` 从 `webrtc` 改为 `gateway-relay`，其余参数不变；重载配置。
2. 重复 R0 核心项（OAuth-only 会话建立、中文实时、连续对话、barge-in）与
   R1 的 consult 验证。
3. 记录与 R0（webrtc）的延迟对比。

PASS 判据：`gateway-relay` 下 ChatGPT OAuth-only 能建立 GPT-Live session；
实时语音/打断/consult 正常。

意义：WebRTC 栈对 ESP32 过重；`gateway-relay` 是否可用是 ESP32 Voice
Bridge 传输路径的关键前提，即 R2 的核心问题。

## 交付物（R0–R2 完成后）

- [PHASE2B_REALTIME_VALIDATION_REPORT.md](PHASE2B_REALTIME_VALIDATION_REPORT.md)：
  实际使用的 OpenClaw Talk 配置；R0/R1/R2 每项 PASS/FAIL；实际错误与日志
  摘要；ChatGPT OAuth 与 API key 使用情况；ESP32 Voice Bridge 下一阶段
  接口建议。
- 架构决策已落为 [ADR-0005](decisions/0005-openclaw-realtime-gateway-relay.md)。
- 产品主链验证通过后允许开题 ESP32 → Mac Voice Bridge（R0 浏览器路径失败不阻塞）。

## 风险

- ChatGPT OAuth-only 能否驱动 GPT-Live（尤其 `gateway-relay`）是最大不确定
  点，即 R2 核心问题；任一 FAIL 则回到架构决策而不是绕过。
- 无 API key 情况下的速率/并发/时长限制未知。
- Headless 场景（Mac Voice Bridge 后续无浏览器运行）如何维持 OAuth 会话
  未验证，必须在报告中记录。
- GPT-Live 下行音频采样率/延迟对 ESP32 16 kHz 链路的适配未验证。
- 外部依赖（OpenAI/OpenClaw 版本演进）不可控；本阶段不固化其 API 名称为
  硬件协议。
