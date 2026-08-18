# Phase 2A — Voice Hardware Bring-up

> **Historical phase definition** — 记录当时计划做什么，不是当前架构事实源。
> 状态：已完成并验收（2026-08-18 用户确认）。
> 短报告：[phase-02a-voice-hardware-bringup.md](phase-reports/phase-02a-voice-hardware-bringup.md)；
> 详细证据：[PHASE2A_REPORT.md](PHASE2A_REPORT.md)。当前架构见 [ARCHITECTURE.md](ARCHITECTURE.md)。

原分支 `phase-2a-voice-hardware-bringup`，基线 commit `f7b7568`。

## 目标（单一）

在产品固件 `firmware/product/` 内把本板音频硬件链路打通并留下可复现证据：
ES7210（ADC：双麦克风 + 回声参考通道）与 ES8311（DAC + PA）经 I2C 初始化、
I2S 双工（TX std + RX TDM）连续采集/播放，用真机抓取的 WAV 与客观指标证明：

1. 双麦通道（MIC0/MIC1）是两个物理独立通道，不是复制；
2. AEC 参考通道确实携带扬声器播放信号，且数据路径明确；
3. 设备端 esp-sr AEC 开/关对照有可量化回声抑制（ERLE 等指标）；
4. BOOT 按键实际行为有日志证据；
5. 音频满负荷 + 股票看板同时运行 60 分钟稳定（无 panic/看门狗/内存单调下降）。

## 非目标

- 不做唤醒词、VAD 管线、云端语音（Phase 2B/2C）。
- 不改已验收股票看板行为；看板仅作回归观察。
- 不做电池、RTC、SHTC3、TF 卡（另行阶段）。
- 不做 24 kHz 采样链：AEC（esp-sr `aec_create`）要求 16 kHz，本阶段全链路
  统一 16 kHz；24 kHz 方案留待 2B 评估。
- 不引入任何云端正端点或凭据。

## 硬件事实（来源：仓库内冻结参考 v2.4.2 板卡配置）

- I2C0：SDA=13、SCL=14；ES8311、ES7210 默认地址。
- I2S：MCLK=16、WS=45、BCLK=9、DOUT=8（→ES8311）、DIN=10（←ES7210）。
- PA 使能：GPIO46。BOOT 按键：GPIO0（参考配置中本板唯一定义的用户按键，
  无独立 KEY 引脚定义）。
- ES7210 以 TDM 4 slot 输出，slot 顺序为 MIC1、MIC3、MIC2、MIC4（参考
  实现注释）。本板参考实现取 slot0(MIC1)=麦克风、slot1(MIC3)=回声参考。
- 本阶段取 slot0(MIC1)=MIC0、slot2(MIC2)=MIC1、slot1(MIC3)=AEC 参考。

## 预计模块与文件

- `firmware/product/components/audio/`：`audio_hw.c/h`（I2C 总线、
  esp_codec_dev ES8311/ES7210 实例、I2S 通道、PA）、`audio_selftest.c/h`
  （采集序列、嵌入式语音激励播放、esp_aec 处理、PSRAM WAV 缓冲、串口
  dump 协议、设备端统计、稳定期循环）、`audio_stimulus.c`（host 生成的
  真实语音 16 kHz PCM16 激励，macOS `say` 合成）。
- `firmware/product/main/app_main.c`：启动音频自检任务；BOOT 短按/双击
  行为接入。
- `scripts/phase-02a-capture.py`（串口日志→WAV 重组+CRC 校验）、
  `scripts/phase-02a-analyze.py`（通道独立性、ERLE、参考有效性等指标）、
  `scripts/verify-phase-2a.sh`（静态断言 + host 单测）。
- `tests/test_phase2a_analyze.py`：分析器纯 host 单测。

## 验收标准（可复现）

1. I2C 探测与初始化：ES7210/ES8311 ACK 与初始化日志（错误码全为 0）。
2. 麦克风：采集非静音（RMS 高于本底）、无持续削波（削波样本比例 < 0.1%）；
   MIC0/MIC1 非逐样本相同（bit-identity 检查不通过=好），窗口化 Pearson
   |r| < 0.99（复制通道恒为 1.0 且样本相同），互相关延迟估计非零或幅度
   统计显著不同。
3. 扬声器/codec：激励播放期间 TX 无 underrun；参考通道与 TX PCM 显著
   相关（播放窗内相关系数 > 0.5），证明 DAC+PA+回路电学活跃。
4. WAV 产物：`playback_reference.wav`、`aec_off.wav`、`aec_on.wav`
   （及 `mic0_mic1.wav`）由串口协议重组成功且 CRC32 校验通过。
5. AEC 指标：同一激励下，回声时段 ERLE（10·log10(P_raw/P_aec)）≥ 10 dB
   且 NLP 后残余显著下降；报告逐窗数值。
6. BOOT：稳定期内实际按键事件（短按、双击）均有日志；无独立 KEY 的
   结论以参考配置为证据记录。
7. 60 分钟稳定：无 panic/reboot/看门狗；internal 与 PSRAM free
   起止差 < 5% 且无单调下降趋势；任务栈水位稳定；股票 Gateway 轮询
   继续返回成功。
8. `bash scripts/verify-phase-2a.sh` 通过；既有 `verify-phase-1c.sh`、
   `verify-phase-1e.sh` 与 Gateway 34 项测试不回归。

## 风险与依赖

- esp_codec_dev ~1.5.6 / esp-sr ~2.4.7 在 IDF 6.0.2 下仅验证过构建，
  真机行为未验证（同版本组合同板在参考工程长期使用）。
- TDM slot↔物理麦克风映射依赖参考注释，用通道统计实证校正。
- GPIO45/46 为 strapping 相关引脚，按参考配置使用。
- AEC 模式与 RAM/CPU 占用实测后记录；模式选择以 VOIP 高性能优先，
  不满足再降级。
- USB CDC 吞吐决定 WAV dump 时长（预计每个 ≤1 分钟），损坏由 CRC 暴露。

## 回滚点

- Git：分支基线 `f7b7568`（工作区当前干净），失败时 `git reset --hard
  f7b7568` 即回到 Phase 1E 完成态。
- 硬件：回滚为重刷 Phase 1E 已验收固件（构建产物 SHA-256 见 Phase 1E
  报告）；本阶段不改分区表，无持久化迁移。
