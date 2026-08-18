# 产品路线图

路线图只记录用户确认的当前路线与各阶段状态；当前状态以
[PROJECT_STATE.md](PROJECT_STATE.md) 为准，同一时间只允许一个未验收 Phase。
文档归属见 [DOCUMENT_INDEX.md](DOCUMENT_INDEX.md)。更早基础阶段见
`PROJECT_STATE` 与 [phase-reports/](phase-reports/)。

| Phase | 目标 | 状态 |
| --- | --- | --- |
| 1B | First Flash & Boot | 已完成 |
| 1B.1 | Clean Firmware Bootstrap | 已完成并验收 |
| 1C | Stock Display Skeleton | 已完成并验收 |
| 1D.0 | A-share Provider Bake-off | 已完成并验收（非交易时段；交易时段补测保留） |
| 1D | Stock Gateway | 已完成并验收（NAS/非交易时段；交易时段补测保留） |
| 1E | Live Stock Dashboard | 已完成并验收（真机/非交易时段；交易时段补测保留） |
| 2A | Voice Hardware Bring-up | 已完成并验收（2026-08-18） |
| 2B | OpenClaw Talk gateway-relay + Realtime + EVA consult | **Completed / Accepted for architecture progression**。R1/R2 PASS；R0 浏览器 WebRTC FAIL = non-product path / non-blocking |
| 2C | EVA Voice Bridge Interface & Transport（[定义](PHASE2C_EVA_VOICE_BRIDGE.md)） | **进行中** |

已验证主链（[ADR-0005](decisions/0005-openclaw-realtime-gateway-relay.md) /
[ADR-0006](decisions/0006-eva-voice-bridge-thin-adapter.md)）：

```text
ESP32 音频边缘 → Mac EVA Voice Bridge → Mac OpenClaw Gateway
  → gateway-relay → gpt-realtime-2.1 → agent-consult → EVA
```

NAS 只跑 Stock Gateway。`gpt-live-1-codex` 不可用于 realtime。
旧实验资产保留在 `dev`（VOICE_PROTOCOL v1）与 `phase-2b-r`（协议 v2），
不删除、不合并。

未验收硬件矩阵见 [HARDWARE_BASELINE.md](HARDWARE_BASELINE.md)。

## 延后与 Future（不得提前并入当前路线）

持仓/成本/盈亏、提醒、详情页与 K 线、RLCD partial update、OTA 产品化、
配置页面、OpenClaw Gateway 迁回 NAS、统一设备发现/认证。每项需用户重新
确认并独立 Phase 或 ADR。
