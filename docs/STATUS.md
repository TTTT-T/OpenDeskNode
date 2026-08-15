# 当前阶段状态

最后更新：2026-08-15

本文件是阶段状态的唯一入口。新会话只需从这里定位当前 Phase 和最近相关报告，不应默认加载全部历史。

## 进行中 Phase

### Phase 1B.1 — Clean Firmware Bootstrap

- 单一目标：冻结已验收的 Xiaozhi v2.4.2 为硬件参考基线，并建立不继承 Xiaozhi 云平台架构的独立 ESP-IDF 正式固件，重新达到 Phase 1B 的最小硬件能力。
- 非目标：音频质量/AEC/VAD/唤醒词、Xiaozhi 激活/OTA/业务协议/MCP/云端 ASR/LLM/TTS、OpenAI Realtime/GPT、股票数据与股票 UI。
- 预计模块：`firmware/` 下的正式 ESP-IDF 工程、Waveshare board 定义、RLCD/LVGL 最小显示、BOOT 按键、Wi-Fi station、NVS/event loop/system 初始化、构建/验收脚本及架构文档。
- 验收标准：正式固件可重复构建；真机 cold boot/reset 无 boot loop 或 panic；运行时确认 16 MB Flash 与 8 MB PSRAM；显示自定义 clean-firmware 测试页；BOOT 事件可见；Wi-Fi 完成最小 station 连接；代码与运行路径不包含 Xiaozhi 官方服务器、账号或激活依赖。
- 风险与依赖：RLCD 驱动迁移可能暴露对 Xiaozhi Display/Application 的隐式依赖；Wi-Fi 凭据必须通过本地安全配置/运行时配网提供且不得提交；构建通过不能替代真机验收。
- 回滚点：annotated tag `phase-1b-xiaozhi-reference` 指向已验收提交 `5113506`；`firmware/xiaozhi/` 保持原样作为 reference。

## 最近完成

- [Phase 1B — First Xiaozhi Flash & Boot Verification](phase-reports/phase-01b-first-flash-boot.md)（2026-08-15）
- [Phase 1A — USB 、设备身份与原厂备份](phase-reports/phase-01a-usb-identity-backup.md)（2026-08-15）
- [Phase 0A — 产品与 Upstream 基线](phase-reports/phase-00a-product-upstream-baseline.md)（2026-08-13）
- [Phase 0 — Agent 协作与交付基础设施](phase-reports/phase-00-agent-delivery-foundation.md)（2026-08-13）

## 后续阶段

Phase 1B.1 完成后停止，由验收结果决定先进入 Voice Hardware Bring-up 或 Stock Display Skeleton；不再以 Xiaozhi 官方云或 Xiaozhi Server 作为正式产品运行依赖。
