# Phase 2A 报告 — Voice Hardware Bring-up

日期：2026-08-16 ~ 2026-08-17（会话内完成）；分支 `phase-2a-voice-hardware-bringup`。
基线：commit `f7b7568`（Phase 1E 完成态）。目标与非目标定义见
[PHASE2A_VOICE_HARDWARE_BRINGUP.md](PHASE2A_VOICE_HARDWARE_BRINGUP.md)。

## 结论

**Phase 2A 全部可执行验收项 PASS**（14/14；1 项不适用于本板硬件，见验收矩阵）。
ES7210/ES8311 + I2S 全双工音频链路在产品固件内打通，双麦独立性与 AEC
有效性有 WAV 级客观证据，60 分钟满负荷稳定无异常。未进入 Phase 2B。

## 实际新增/修改文件

新增：

- `firmware/product/components/audio/`：`audio_hw.c/h`（I2C0 总线、I2S0
  std TX + TDM RX、esp_codec_dev ES8311/ES7210 实例、PA 控制）、
  `audio_selftest.c/h`（自检序列、esp-sr AEC、PSRAM 捕获、串口 WAV 协议、
  统计与稳定期循环）、`audio_stimulus.c/h`（16 kHz 真实语音激励）、
  `CMakeLists.txt`。
- `scripts/phase-02a-capture.py`：串口捕获 + WAV 重组 + CRC32 校验。
- `scripts/phase-02a-analyze.py`：通道独立性/参考有效性/ERLE 客观指标。
- `scripts/phase-02a-gen-stimulus.sh`：激励再生（macOS `say`）。
- `scripts/verify-phase-2a.sh`：静态断言 + host 单测。
- `tests/test_phase2a_analyze.py`：分析器单测（含复制通道反例）。
- `docs/PHASE2A_VOICE_HARDWARE_BRINGUP.md`、本报告。

修改：

- `firmware/product/components/board/include/board.h`：新增音频引脚
  常量（来源冻结参考 v2.4.2）；按键回调改为事件枚举（单按/双击）。
- `firmware/product/components/board/board_button.c`：新增双击识别
  （400 ms 窗口），保留原去抖逻辑。
- `firmware/product/main/app_main.c`、`main/CMakeLists.txt`：接入音频
  自检任务与 BOOT 行为。
- `firmware/product/main/idf_component.yml`、`dependencies.lock`：
  新增 `espressif/esp_codec_dev ~1.5.6`、`espressif/esp-sr ~2.4.7`。
- `docs/PROJECT_STATE.md`、`docs/ROADMAP.md`、`.gitignore`
  （`artifacts/` 大文件不入库，哈希记录于本报告）。

## 最终音频架构与数据流

```
采集（16 kHz PCM16）:
  ES7210 ADC (MIC1, MIC3, MIC2) --TDM 4slot(总16bit)--> I2S0 RX (DMA)
    -> esp_codec_dev_read (slot_mask 0|1|2, 3ch 打包)
    -> audio_hw_read() 解交织: mic0=slot0(MIC1), ref=slot1(MIC3), mic1=slot2(MIC2)

播放（16 kHz PCM16 单声道）:
  audio_hw_write() -> esp_codec_dev_write -> I2S0 TX (std Philips, stereo slot,
    L=R=mono) -> ES8311 DAC -> PA(GPIO46, 5V) -> 扬声器

AEC（设备端）:
  aec_create(16000, filter_len=4, 1 mic, AEC_MODE_VOIP_HIGH_PERF)
  每 256 样本帧: aec_process(aec, mic0, ref, out)  // ref 即上行回采
```

## ES7210 / ES8311 初始化参数（实测生效值）

- I2C0：SDA=13、SCL=14、100 kHz（esp_codec_dev `DEFAULT_I2C_CLOCK`），
  内部上拉。I2C 探测证据：`ES7210 REG00=0x00`、`ES8311 REG31=0x1c`
  读取成功（audio_hw_init 日志）。
- ES7210：`mic_selected = MIC1|MIC2|MIC3`（驱动逐路上电、每路
  0x10 enable + gain）；TDM 模式（SDP_INTERFACE2=0x02）；输入增益
  **30.0 dB**（对齐参考实现 BoxAudioCodec 默认 `input_gain=30.0`；曾实测
  0 dB 时 mic RMS≈10 近静音，30 dB 后 RMS≈290，证明增益真实生效）。
- ES8311：`WORK_MODE_DAC`、`use_mclk=true`、`pa_pin=46`、
  `pa_voltage=5.0`、`codec_dac_voltage=3.3`；输出音量 70（双击可在
  70↔0 切换）。
- I2S0：MCLK=16（256×fs）、WS=45、BCLK=9、DOUT=8、DIN=10；
  DMA 6 描述符 × 240 帧；TX std / RX TDM total_slot=4（收 3 slot）。

## MIC0/MIC1 非复制通道的证明

对真机 `mic0_mic1.wav`（337,097 样本/通道，CRC 校验通过）：

- 逐样本位相同率 **2.50%**（复制通道为 100%；2.5% 全部来自静音段
  0==0 巧合，活动段近似 0）。
- 500 ms 窗最大 Pearson |r| = 0.990，但**最小窗口线性拟合残差比
  1−r² = 0.0195**：复制通道恒为 0（完美线性），两物理麦克风因独立
  ADC 噪声与不同声路径必有非零残差。
- 设备端独立统计 `identical_mic0_mic1=2.50%`（`PHASE2A_STAT` 行）与
  host 分析一致；两通道 RMS 291 vs 308、峰值 3052 vs 3108，统计可区分。
- 分析器含"数字复制通道必被判依赖"的自动反例测试
  （`test_copied_channel_is_detected`）。

## AEC reference 的来源与数据路径

本板参考实现 `AUDIO_INPUT_REFERENCE=true`：ES7210 的 MIC3 输入在板上
布线为编解码器播放回采（electrical loopback，非声学回采）。数据路径：
ES8311 DAC 输出 → 板上回采网络 → ES7210 MIC3 → TDM slot1 →
`audio_hw_read()` 的 `ref` 通道 → `aec_process()` 第三参。

有效性证据（`analysis.json`）：

- 参考通道播放活动/静音对比 **23.4 dB**（首 1 s 静音 vs 次 1 s 播放）；
- 播放窗口内 ref 与 mic0 最大窗 Pearson r=0.416，互相关峰在
  **15 样本（0.94 ms）** 处，即麦克风听到扬声器信号且存在真实声学延迟；
- 参考信号峰值 8664（满量程 26%），无削波，与 TX PCM 内容对应
  （`playback_reference.wav` 可直接听）。

## KEY / BOOT 实际行为（真机日志，20260816-buttons）

- BOOT 单按：`board_button: BOOT press` →
  `audio_p2a: self-test rerun requested` → 完整重跑自检并重新导出 5 个
  WAV（全部 CRC PASS，`selftest_end PASS`）。证据时间戳 32909 s 与
  32961 s 两次。
- BOOT 双击：`BOOT double press` → `volume 0`；再次双击 → `volume 70`
  （0↔70 双向均有日志，含恢复）。
- KEY：冻结参考配置（v2.4.2 `config.h`）本板**只定义 BOOT=GPIO0**，
  无独立 KEY 引脚；按"不凭代码推断"原则记为不适用（N/A），非 FAIL。
- PWR/复位按键不在本阶段范围（见 Phase 2A 文档非目标）。

## 依赖版本（dependencies.lock 实测锁定）

- ESP-IDF **v6.0.2**（commit 7101770d，repo 内 `.tools/` pinned）
- espressif/**esp-sr 2.4.7**（AEC: `aec_create/aec_process`，chunk=256）
- espressif/**esp_codec_dev 1.5.11**（~1.5.6 解析结果；ES8311/ES7210 驱动）
- espressif/esp-dsp 1.8.0、espressif/dl_fft 0.6.0（esp-sr 传递依赖）
- lvgl 9.5.0 / esp_lvgl_port 2.8.0（沿袭 Phase 1B.1，未动）

## 编译结果

- `idf.py build`（esp32s3, /private/tmp 构建目录）：成功，无 warning
  错误；产物 `esp32_s3_rlcd_dashboard.bin` **3,674,832 字节**，
  SHA-256 `cdcf782b38fa1d76d9a02275b29f06703fe7d964ef79388705e50ebc23dec9d7`。
- 同一产物已烧录真机（USB-Serial/JTAG，写入后 hash 校验通过）。

## 自动测试结果

- `bash scripts/verify-phase-2a.sh`：**PHASE_2A_OFFLINE_CHECKS_OK**
  （含 4 项分析器单测，覆盖复制通道反例/独立双麦/参考有效/无抑制反例）。
- `bash scripts/verify-phase-1c.sh`：PHASE_1C_STATIC_CHECKS_OK（回归）。
- `bash scripts/verify-phase-1e.sh`：PHASE_1E_OFFLINE_CHECKS_OK（回归）。
- Gateway + 全量 host 测试：**38/38 OK**（venv: requirements.txt +
  requirements-test.txt）。

## 真机测试结果

1. I2C 探测与两个 codec 初始化：全部 `ESP_OK`，寄存器可读。
2. 自检序列三次执行（开机 1 次 + BOOT 触发 2 次）均
   `PHASE2A_SEQ selftest_end PASS`。
3. 采集通道统计（aec_off 运行）：mic0 RMS 291.1 / mic1 308.3 /
   ref 1355.6；峰值 3052/3108/8664；削波 0；双麦位相同率 2.50%。
4. 扬声器播放激励可闻（TTS 普通话语句），TX 无 underrun 报错；
   音量 70↔0 双击切换可闻差异。
5. 稳定期：音频 RX+AEC+TX 连续运行 63 分钟（验收线 60 分钟），
   `PHASE2A_STAB` 64 条，见下节。

## WAV 产物（全部实际生成并 CRC32 校验通过）

位置 `artifacts/phase-02a/20260816/`（不入 Git，SHA-256 前缀在括号内）：

| 文件 | 字节 | 内容 |
| --- | --- | --- |
| `playback_reference.wav` | 674,238 | AEC 参考通道整段（`1ae953fa…`） |
| `aec_off.wav` | 674,238 | 原始 mic0（AEC 前）（`8d6bf83d…`） |
| `aec_on.wav` | 674,238 | AEC 后 mic0（`6357d0a0…`） |
| `mic0_mic1.wav` | 1,348,432 | 双麦立体声（`39ab2547…`） |
| `mic0_mic1_b.wav` | 1,348,432 | 双麦第二次导出，CRC 与首次一致（导出确定性证据） |

传输完整性：设备端流式 CRC == 设备端独立预扫 CRC == host zlib CRC32，
三方一致；`wavs.json` 记录每次校验布尔值全真。
注：USB-Serial/JTAG 控制台在逐行 printf 洪泛下会整行丢弃，固件已改为
12 行/批 + 批间 1 tick 让速后零丢失（曾复现 11 行/文件丢失并修复）。

## AEC 客观指标（analysis.json，28 个 500 ms 活动窗）

- **ERLE 均值 32.50 dB**（min 24.48 / max 37.46）——阈值 ≥10 dB，通过。
- 设备端实时 ERLE（刺激播放期间窗口均值）：26.76–30.33 dB（三次运行）。
- 全段能量：aec_off RMS 291.06 → aec_on RMS **7.32**（约 -32 dB）。
- 对齐：aec_off↔aec_on 互相关滞后 637 样本（两次播放起拍相位差），
  已按滞后对齐后逐窗计算。
- 非线性残余抑制后近端语音可懂性未做 MOS 打分（非目标）；2B 接入
  VAD/唤醒词时复检。

## 60 分钟稳定性（63 分钟实测）

- `PHASE2A_STAB` 64 条，uptime 713→4493 s；音频帧 3753→240003，
  恒速 **16000 样本/秒**（无丢帧趋势）。
- internal free：起 38,527 → 止 38,515 B（**差 12 B**；区间 21,751–38,727，
  低点为 WAV dump 瞬时占用，结束后恢复）。
- internal largest：止值 21,504 B 不变；PSRAM free：起止均 8,267,912 B
  （区间 8,169,112–8,267,912，同为 dump 瞬时）。
- 任务栈高水位恒定 15,896（无栈增长）。
- 零 panic/看门狗/重启；两次 BOOT 触发的完整自检重跑在稳定期内无泄漏
  （重跑后 free_int 回到同值）。
- 股票看板回归：稳定期内 405/405 次 Gateway 轮询 `ESP_OK`，
  `data=fresh`，view/flush 耗时与 Phase 1E 基线一致。

## 已知问题与剩余风险

1. **串口吞吐边界**：WAV 协议在更高码率（如 24 kHz 或 4 通道全量）下
   需重新评估批量大小；当前 12 行/批 + 1 tick 在 16 kHz 3ch 下零丢失。
2. **音量 0 对照实验 inconclusive**：双击静音期间触发的重跑 mic RMS
   （282/304）与正常（291/308）接近，因环境底噪占主导、回声贡献小于
   底噪；不作为证据使用，也不影响结论（参考有效性由 23.4 dB 对比 +
   互相关延迟独立证明）。
3. **24 kHz 采样率未验证**：esp-sr AEC 限 16 kHz，本阶段全链路 16 kHz；
   2B 若需 24 kHz 须引入重采样或换 AEC 方案（已列入 2B 前置检查）。
4. **AEC 模式单一**：仅验证 VOIP_HIGH_PERF；SR 低成本模式与 NLP 档位
   对比留 2B（当时按唤醒词误触率选型）。
5. **MIC4（TDM slot3）未使用**：本板参考配置只启用 MIC1/2/3；若后续
   发现第四路布线存在再评估。
6. 温度/长时间充电等边界（HARDWARE_BASELINE 矩阵 battery/RTC/SHTC3/TF
   项）不在本阶段，仍为未验证。

## 验收矩阵

| 验收项（Phase 2A 文档 §验收标准） | 结果 |
| --- | --- |
| 1. I2C 探测与 codec 初始化 | **PASS** |
| 2. 麦克风非静音/无削波/非复制 | **PASS** |
| 3. 扬声器播放 + 参考与 TX 相关 | **PASS** |
| 4. 四类 WAV 生成 + CRC | **PASS**（5 个文件，含确定性双导出） |
| 5. AEC ERLE ≥10 dB | **PASS**（32.5 dB） |
| 6. BOOT 单按/双击实测 | **PASS**；独立 KEY 不适用（板卡无此定义） |
| 7. 60 分钟稳定 + 资源平稳 | **PASS**（63 分钟） |
| 8. verify-phase-2a + 1C/1E/Gateway 回归 | **PASS** |
| PWR 按键 / 电池 / RTC / SHTC3 / TF | BLOCKED_ON_HARDWARE（不在 2A 范围，
  参考配置无 PWR 用户键定义，其余外设未接入） |

## 回滚点

分支基线 `f7b7568` 可随时 `git reset --hard` 恢复 Phase 1E 完成态；
真机回滚 = 重刷 Phase 1E 固件（分区表未改动，NVS 无迁移）。

## 最终 commit

`feat(phase-2a): deliver voice hardware bring-up`（分支
`phase-2a-voice-hardware-bringup`，基线 `f7b7568`）。一个提交无法包含
自身哈希；准确哈希记录于 `docs/PROJECT_STATE.md` 最近完成条目
（`docs(phase-2a): record phase-2a completion hash` 提交内）。
