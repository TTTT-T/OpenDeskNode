# Phase 0A — 产品与 Upstream 基线

完成日期：2026-08-13

## 目标与实际完成

把产品移交转化为可复现的仓库、架构和上游构建基线，不开发股票或语音业务。已完成：

- 以独立 Git subtree 提交导入 `78/xiaozhi-esp32` v2.4.2 / `e8d8a4010788afd60f0c8aa3b2e3d0a7bb8f02e5`；
- 固定项目本地 ESP-IDF v6.0.2，并提供初始化、构建和静态验收脚本；
- 核验 Waveshare 硬件/示例、Xiaozhi 固件与服务端、OpenAI 接口以及股票数据候选；
- 建立产品上下文、当前/目标架构、路线图、三项 ADR、upstream 升级/回滚流程和 Phase 1 真机矩阵；
- 明确 Stock Dashboard 与 GPT 工具必须共用 Stock Service，产品业务不得进入 Board/驱动，凭据不得进入固件或 Git。

## 验收结果

- `bash scripts/build-firmware.sh`：通过；2207/2207 编译任务完成，产出 11,289,121 bytes 的 merged binary。
- merged binary SHA-256：`9bf98a7762916ad0eb5d5463a0fe3f472bea74c19ff77952ff06e3184933cd19`。
- 应用固件 `0x2c9740`；最小 app 分区剩余 `0x1268c0`（29%）。
- `bash scripts/verify-phase-0a.sh`：通过；upstream 62/62 单元测试、板型/AEC 静态检查、本地 Markdown 链接和 `git diff --check` 均通过。
- 未写入任何 OpenAI、股票数据或 Wi-Fi 凭据；`.env.example` 只包含空变量名。

## 重要决定与纠正

- v1 固件基线选择最新稳定 release v2.4.2，不追踪 `main`；upstream 更新使用 subtree 且必须独立验收。
- v1 语音采用 Xiaozhi 的 ASR → GPT → TTS；OpenAI Realtime 留作未来独立 Phase。
- Xiaozhi Server v0.9.6 的 OpenAI-compatible adapter 当前使用 Chat Completions，不把它误写成 Responses API 实现。
- RLCD 当前是 LVGL dirty-area 更新后全 framebuffer 传输；PSRAM 还包含两个 LUT 和 RGB565 buffer，不能只按 15 KB framebuffer 估算。
- AKShare/Tushare 仅是候选；实时权限、条款、稳定性与失败行为要在 Phase 3 实测后决策。

## 已知限制与 workaround

- 硬件未到位；显示、方向、中文、Wi-Fi、双麦、Codec、AEC、按键、电池和稳定性均未做真机验收。
- ESP-IDF/GCC 在当前中文仓库路径下错误生成 `picolibc.specs` response-file 路径；构建脚本用原生 `idf.py -B` 将输出放在纯 ASCII 的 `/private/tmp`，不复制或修改 upstream 源码。
- ESP-IDF 依赖的 `psutil` 在 Codex 沙箱内无法调用受限 `sysctl()`；完整构建已在主机级执行复核。
- 组件 Kconfig 会输出若干 upstream `default False/0` 警告，但配置、编译、链接、分区检查和 merge-bin 均成功；后续升级时继续观察。

## 下一步

等待实物到货后启动 Phase 1，严格按 [Hardware Baseline](../HARDWARE_BASELINE.md) 收集真机证据。在 Phase 1 通过前不启动产品 UI。
