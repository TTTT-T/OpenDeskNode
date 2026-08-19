# Phase 2C — C1 上行链真机验收报告

日期：2026-08-19。结论：**C1 PASS**（真人中文上行进入 Realtime）。
分支：`phase-2c-eva-voice-bridge`；hardening 提交 `cfd25cd` + 验收期修复提交（见下）。
证据文件：`artifacts/phase-02c/`（gitignored；关键数字摘录在本文）。

## 验收执行环境

- EVA Voice Bridge（Mac，`GatewayTalkClient` 真实 OpenClaw Talk，非 FakeTalk）
- OpenClaw Gateway :18789 → gpt-realtime-2.1，brain=agent-consult
- ESP32-S3-RLCD-4.2 完整断电再上电后烧录（USB-JTAG 卡死经断电恢复）
- 固件 Bridge URI：`ws://TTT-Macmini.local:8090/voice/v0`（mDNS，非硬编码 IP）

## C1 真人上行证据（5 轮）

Watcher `scripts/phase-02c-c1-live.py` 只认 baseline 之后新增的
`transcript.done`（session 过滤 + monotonic eventSeq 关联）。

| 轮 | 触发 | frames | drop/drop_total | qpeak | transcript.done |
| --- | --- | --- | --- | --- | --- |
| 1 | BOOT 长按 | 249 | 0/0 | 2 | 你好,Eva,这是ESP32。 |
| 2 | BOOT 长按 | 249 | 0/0 | 2 | 你好一万,这是第三轮麦克风测试。 |
| 3 | BOOT 长按 | 249 | 0/0 | 2 | 你好伊娃,这是最后一轮测试。 |
| 4 | BOOT 长按（selftest 后，WS 曾断开） | 306 | 0/0 | 20 | 自检之后的上行测试。 |

（另有一次上行发生在 selftest 占用期间 frames=0，为 ownership 语义正确行为。）

累计：设备 996+ 帧 / 637 KB+ AEC PCM；bridge 侧 seq_gap=1（首轮，无增长）、
seq_dup=0、seq_reorder=0、dropped_old=0（重连修复后）。heap 稳定
~16-28 KB internal 波动、PSRAM 8.17 MB free。每轮独立干净，
**跨轮 queue/drop 污染实测不存在**（对应 per-utterance drop 窗口修复）。

## Audio ownership 让权→归还（真机两次）

```
PHASE2C_C1 audio_ready (voice 持有)
→ audio_owner: released 1 (voice 让权)
→ PHASE2A_SEQ selftest_end PASS（5 WAV，crc32 流式与预计算全部一致）
→ audio_owner: released 2 (selftest 归还)
→ PHASE2C_C1 tick 恢复 + 后续真人上行成功（第 4 轮）
```

Phase 2A 回归：`PHASE2A_STAT` mic/ref RMS、clip=0、AEC chunk=256
VOIP_HIGH_PERF 正常；`PHASE2A_STAB` 资源正常。

## 股票链

全程（约 55 分钟 uptime）`stock-1e cycle=N fetch=ESP_OK data=fresh`
约 11 s 周期持续，语音上行/selftest 并发期间无中断。

## 验收中发现并修复的缺陷（全部带 host 回归）

1. **ownership 饥饿**（827b795 存在）：voice 让权后立即重抢，
   `audio_owner_acquire` 覆写 `s_wanted` 销毁 selftest 请求 →
   selftest 3 s 超时 FAIL。修复：acquire 不再改 `s_wanted`；
   voice 等待 owner 清空再重取。真机 A/B：修复前 FAIL / 修复后 PASS。
2. **Talk reader 脆弱**：设备 WS 断连时 listener 异常炸掉共享 Talk 读循环
   （`talk_connected:false`）。修复：listener 分离 try/except。
3. **WS 断开→conversation 残留**：长 selftest 期间设备 WS 被关，
   重连后设备不重发 open，speech_start 被拒、163 帧全废。修复：
   断开事件与 `error.code=unknown_conversation` 均清 `conversation_id`，
   下轮自动重开（第 4 轮 cid=4 验证）。

## Hardening 项（验收前完成，见 cfd25cd）

- TX queue drop 阈值改 per-utterance 窗口（1.5 s），lifetime 计数仅诊断。
- voice audio task 所有失败路径释放 owner/AEC/缓冲。
- watcher baseline 防陈旧证据：只认新增 `transcript.done`，带
  sessionId/eventSeq/ts。
- Bridge URI 可移植：git 默认 `eva-bridge.local` 占位 + mDNS 查询启用；
  真实地址只在 gitignored sdkconfig。

## 测试与构建

- `bash scripts/verify-phase-2c.sh`：30/30 OK（含 8 个 watcher 回归）。
- ESP-IDF v6.0.2 clean build ×3 OK（最终二进制
  sha256 751f3641522e4c168764f2aee3ced3e0865cb7e94ed2978caadccaae6ed1f30b）。

## 未尽事项（不阻塞 C1）

- 下行播放未做（C2）：第 1-3 轮 bridge 已收到 478 帧下行
  `output.audio.delta`，设备侧播放静音占位（C1 范围外）。
- "EVA" 常被转写为「一万/伊娃」：Realtime 侧现象，与 transport 无关。
- 双击误触发风险：BOOT 400 ms 双击窗口内两次长按间隔过近会被判
  double press（操作注意即可，不改代码）。
