# Phase 2C — C3 本地先停 barge-in 真机验收报告

日期：2026-08-20。结论：**C3 PASS**（播放中 BOOT 本地先停 + `interrupt` / `cancelOutput` + 同 cid 新上行）。
分支：`phase-2c-eva-voice-bridge`。
证据：`artifacts/phase-02c/c3-live.json`、`c3-serial.log`（gitignored）。
固件 sha256：`d64fe6e909aa8cb672f8c72a871aef694210782709ee7039454dfca889008c10`。

## 验收执行环境

- EVA Voice Bridge（Mac，`GatewayTalkClient`）
- OpenClaw Gateway :18789 → gpt-realtime-2.1，brain=agent-consult
- ESP32-S3-RLCD-4.2；URI `ws://TTT-Macmini.local:8090/voice/v0`
- Watcher：`scripts/phase-02c-c3-live.py`（只认 baseline 之后同 cid 的
  新 `interrupt` + 新上行 + `transcript.done`）

## C3 真机打断证据

用户确认喇叭立即停。Watcher 一轮（cid=6）：

| 侧 | 证据 |
| --- | --- |
| 用户 | 播放中按 BOOT，扬声器马上停 |
| 设备 | `play_done why=button` 后 `interrupt_sent why=utterance`；同 cid |
| Bridge watcher | ok=true；same_conversation；new_interrupts=1；new_cancel_ok=1；uplink 247→500 |
| Talk | `cancelOutput` ok；转写「一个,能听到我说话吗?」 |

后续同会话用户再说「不用再说了」，播放正常 drain，未再误触发自打断。

AEC 重叠残差约 2–9，play_rms 可达 2000–4000：回声远低于人声阈值，未出现
C2 担心的残差自打断。

## 验收中发现并修复

1. **残差 VAD 误打断 / 人声被当回声**：首版过敏感会掐 EVA 回复；收紧后又
   听不到插话。冻结路径：**BOOT 本地先停**；VAD 只按 holdoff 残差地板
   ≥max(800, floor×3) 连续 4 帧，本轮真机 onset 保持 0。
2. **采集窗内 BOOT 只停喇叭、晚发 interrupt**：改为 `mid_utterance`
   立即 `interrupt` 并重开本 turn。
3. **BOOT 建连后看板 flush abort**：`rlcd_flush_cb` SPI DMA
   `ESP_ERR_NO_MEM` 触发 `ESP_ERROR_CHECK` 重启。改为跳过本帧并
   `flush_ready`，不中止语音。

## 测试与构建

- host C voice protocol/VAD 与 `tests.test_bridge_c3` /
  `tests.test_c3_live_watcher` 通过。
- ESP-IDF v6.0.2 构建并烧录成功。

## 未尽事项（不阻塞 C3）

- 语音 VAD 打断未在真机命中；产品打断以 BOOT 为准。C4 可再调。
- 一次唤醒多轮（C4）、恢复矩阵（C5）未做。
- 2A selftest 本轮未重跑。
