# 产品路线图

路线图只记录用户确认的当前路线与各阶段状态；当前状态以 [PROJECT_STATE.md](PROJECT_STATE.md) 为准，同一时间只允许一个未验收 Phase。更早的已完成基础阶段（Agent 基础、upstream 基线、USB/备份等）见 [PROJECT_STATE.md](PROJECT_STATE.md) 与 [phase-reports/](phase-reports/)；历史阶段报告中的旧编号保持原样，不回写。

| Phase | 目标 | 状态 |
| --- | --- | --- |
| 1B | First Flash & Boot | 已完成 |
| 1B.1 | Clean Firmware Bootstrap | 已完成 |
| 1C | Stock Display Skeleton（详见 [Phase 1C 文档](PHASE1C_STOCK_DISPLAY_SKELETON.md)） | 已完成并验收 |
| 1D.0 | A-share Provider Bake-off（quote primary easyquotation/Tencent；intraday supplementary Baidu direct；quote fallback adata/Sina） | 已完成并验收（非交易时段；下一交易时段实时更新待验） |
| 1D | Stock Gateway（自部署行情后端，详见 [Phase 1D 文档](PHASE1D_STOCK_GATEWAY.md)） | 已完成并验收（NAS/非交易时段；交易时段补测保留） |
| 1E | Live Stock Dashboard（真实行情接入，详见 [Phase 1E 文档](PHASE1E_LIVE_STOCK_DASHBOARD.md)） | 已完成并验收（真机/非交易时段；交易时段补测保留） |
| 2A | Voice Hardware Bring-up（详见 [Phase 2A 文档](PHASE2A_VOICE_HARDWARE_BRINGUP.md)、[报告](PHASE2A_REPORT.md)） | 已完成并验收（2026-08-18 用户确认；realtime 方向开发基线） |
| 2B | OpenClaw Talk gateway-relay + OpenAI Realtime + EVA consult 验证（详见 [阶段定义](PHASE2B_GPT_LIVE_REALTIME_VALIDATION.md)、[报告](PHASE2B_REALTIME_VALIDATION_REPORT.md)） | Software Complete（R1/R2 PASS；R0 浏览器 WebRTC FAIL，非产品路径） |
| 2C | ESP32 → Mac EVA Voice Bridge 接口设计与实现（阶段文档待开题） | 可开题 |

已验证主链（[ADR-0005](decisions/0005-openclaw-realtime-gateway-relay.md)）：
`ESP32 音频边缘 → Mac Voice Bridge（未实现）→ Mac OpenClaw Gateway →
OpenAI Realtime gpt-realtime-2.1 → openclaw_agent_consult → EVA`。
NAS 只跑 Stock Gateway。`gpt-live-1-codex` 不可用于 realtime。
旧实验资产保留在 `dev`（VOICE_PROTOCOL v1）与 `phase-2b-r`（协议 v2），不删除、不合并。

未验收硬件的检查矩阵见 [HARDWARE_BASELINE.md](HARDWARE_BASELINE.md)。

## 延后与 Future（不得提前并入当前路线）

持仓/成本/盈亏、提醒、详情页与 K 线、RLCD partial update、OTA 产品化、配置页面等；每项需用户重新确认并独立 Phase。
