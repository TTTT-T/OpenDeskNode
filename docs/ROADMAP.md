# 产品路线图

路线图只定义阶段目标和退出门槛；当前状态以 [STATUS.md](STATUS.md) 为准。同一时间只允许一个未验收 Phase。

| Phase | 单一目标 | 关键退出门槛 |
| --- | --- | --- |
| 0 | Agent 协作与交付基础 | 已完成：文档职责、验收与 Git 工作流 |
| 0A | 产品与 upstream 基线 | 固定固件/工具链可构建；架构、ADR 和真机计划一致 |
| 1A | USB / Identity Baseline | USB/下载模式可用；原厂 16 MB Flash 双备份一致 |
| 1B | First Flash & Boot | 固定 Xiaozhi 固件可烧录并稳定启动；RLCD、按键和 Wi-Fi 有最小真机证据 |
| 1C | Hardware Baseline | 音频、麦克风、AEC、唤醒、电池、传感器、内存峰值和稳定性有真机证据 |
| 2 | Product UI Foundation | mock data Dashboard、语音 Overlay 与现有 DeviceState 兼容 |
| 3 | Stock Domain & Backend | canonical model、Provider、cache、watchlist 和 HTTP API 有自动测试及一个实盘候选验证 |
| 4 | Live Stock Dashboard | ESP32 显示真实行情并正确表达 loading/error/stale/update time |
| 5 | Stock Detail & Intraday | 分时曲线、昨收线、开高低与缺失数据行为通过验收 |
| 6 | GPT Voice Baseline | 真机完成 ASR → OpenAI GPT → TTS，不含股票工具 |
| 7 | GPT Stock Tools | `get_stock_quote`、`get_watchlist`、`get_stock_intraday` 与 Dashboard 同源 |
| 8 | Product Integration | Dashboard Idle、语音覆盖、自动返回、断网恢复和长时间运行通过 |

## Phase 0A 验收

- 目标板固件在固定 ESP-IDF 上完整构建并产出 merged binary。
- 上游 tag/SHA、来源证据、导入/升级/回滚命令和未验证项均被记录。
- v1 总体架构与 ADR 约束一致，不实现产品业务。
- Phase 1 的每个真机检查都有步骤、证据字段和通过条件。

## Phase 1 验收

Phase 1 以 [HARDWARE_BASELINE.md](HARDWARE_BASELINE.md) 为唯一详细矩阵。最低通过条件：

- 确认实物 SKU/revision、启动芯片信息、16 MB Flash、8 MB PSRAM 与固件 SHA；
- RLCD 初始化、400×300 实际方向、中文、LVGL 静态布局、重复刷新和持续显示通过；
- Wi-Fi 首配、重启重连、断网提示与恢复通过；
- 双麦/参考通道、ES7210、ES8311、扬声器和基础设备 AEC 有录音/播放与日志证据；
- BOOT/KEY/PWR 实际行为、电池电压/百分比/充放电、RTC/SHTC3/TF 卡按范围验证；
- reboot/reset reason、heap/PSRAM 关键快照和至少一次持续运行测试无崩溃或未解释资源下降。

## Future（不得提前并入 v1 Phase）

OpenAI Realtime、AEC 深度优化、真正的 RLCD partial update、OTA 产品化、配置页面、K 线、新闻与更多金融工具。每项需独立证据和 Phase。
