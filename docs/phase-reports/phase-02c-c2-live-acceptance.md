# Phase 2C — C2 下行播放真机验收报告

日期：2026-08-19。结论：**C2 PASS**（Realtime 回答经 Bridge 在 ES8311 播出）。
分支：`phase-2c-eva-voice-bridge`。
证据文件：`artifacts/phase-02c/`（gitignored；关键数字摘录在本文）。
固件 sha256：`675a6fbe7758dc87dfb95202c498c3335acf73454120bcf4e82258bb8cedd3fb`。

## 验收执行环境

- EVA Voice Bridge（Mac，`GatewayTalkClient` 真实 OpenClaw Talk）
- OpenClaw Gateway :18789 → gpt-realtime-2.1，brain=agent-consult
- ESP32-S3-RLCD-4.2；URI `ws://TTT-Macmini.local:8090/voice/v0`
- Watcher：`scripts/phase-02c-c2-live.py`（只认 baseline 之后新增的
  downlink + playback_end + peak>0）

## C2 真机播放证据

用户确认扬声器可听懂回答。最终一轮（cid=5）：

| 侧 | 证据 |
| --- | --- |
| 用户 | 听到回答；轻微滋啦，判定基本可用 |
| 设备 `play_done why=drained` | frames_rx=170 frames_play=169 underrun=0 drop=0 peak=13566 play_ms=3445 |
| Bridge watcher | ok=true；downlink_frames=240 peak=13566 starts=1 ends=1 |
| 上行 | frames=255 drop=0 qpeak=8；转写「你能听到吗?」 |
| 下行 WAV | `c2-downlink.wav` 4.8 s，rms=2208 max=13566 |

`first_audio` 早于 `speech_end`（约 −1.4 s）：Realtime 在 5 s 采集窗内已开始下行。

## 验收中发现并修复

1. **采集窗丢下行**（首轮完全无声）：Realtime 在 `speaking=true` 期间出音频，
   固件 `busy_drop=428` 全丢。修复：采集期间照常入队并播放。
2. **2 s 环 drop-oldest 造成卡顿/中断**：突发填满队列后丢掉正要播的样本
   （qpeak=32000 drop=60–73，play ≈2.3 s / 实长 4–6 s）。修复：8 s 环 +
   **drop-newest**；`CONFIG_ESP_WS_CLIENT_SEPARATE_TX_LOCK` 减轻收发互锁。

修复后再测：drop=0、underrun=0、rx≈play。

## 股票链与 2A 基线

同窗口 `stock-1e cycle=4…13 fetch=ESP_OK data=fresh` 约 11 s 周期，语音播放
期间无中断。C2 未改 `audio_hw` / codec / I2S / AEC；2A selftest 本轮未重跑
（ownership 路径未改）。

## 测试与构建

- `bash scripts/verify-phase-2c.sh`：36/36 Python + host C OK。
- ESP-IDF v6.0.2 构建并烧录成功。

## 未尽事项（不阻塞 C2）

- 轻微滋啦：seq_gap 与采集/播放重叠，C3 barge-in / AEC 再测。
- C3 本地先停、C4 多轮、C5 恢复矩阵未做。
- 2A selftest 本轮未重跑。
