# Phase 2A — Voice Hardware Bring-up

- 日期：2026-08-17 交付；2026-08-18 用户确认验收
- 结果：通过
- 详细证据：[PHASE2A_REPORT.md](../PHASE2A_REPORT.md)
- 规划（历史）：[PHASE2A_VOICE_HARDWARE_BRINGUP.md](../PHASE2A_VOICE_HARDWARE_BRINGUP.md)

## 结果

- ES7210 双麦 + ES8311 扬声器 + I2S 全双工在 `firmware/product/` 打通。
- 16 kHz / 16-bit PCM 基线、AEC（VOIP_HIGH_PERF）、录音/播放测试已验收。
- 双麦非复制、参考通道有效、ERLE 与 60 分钟稳定有 WAV/日志证据。
- 本阶段不进入唤醒/VAD 产品管线/云端语音。

## 保留风险

- 串口 WAV 在 >16 kHz/更多通道时需重新限速。
- AEC 仅验证 VOIP_HIGH_PERF；音量 0 对照 inconclusive。
