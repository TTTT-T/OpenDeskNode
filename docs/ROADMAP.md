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
| 2A | Voice Hardware Bring-up | 未开始 |
| 2B | Wake Word / VAD / AEC | 未开始 |
| 2C | Voice Gateway / OpenAI Realtime | 未开始 |

未验收硬件的检查矩阵见 [HARDWARE_BASELINE.md](HARDWARE_BASELINE.md)。

## 延后与 Future（不得提前并入当前路线）

持仓/成本/盈亏、提醒、详情页与 K 线、RLCD partial update、OTA 产品化、配置页面等；每项需用户重新确认并独立 Phase。
