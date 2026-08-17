# Phase 1C — Stock Display Skeleton 验收报告

- 日期：2026-08-15
- 结果：通过
- 基线：`69fe3f2`
- 范围：确定性 mock → stock model → 2×2 stock view → LVGL → ST7305 RLCD

## 实现结果

- 新增纯 C99 stock model/mock、4 股 2×2 LVGL view、中文/数字字体子集、host tests 与约 10 秒刷新 service。
- `app_main()` 只启动 `stock_service_start()`；view 创建、mock reset 与首屏同步渲染全部由具有 8192 字节明确栈预算的 `stock_svc` 执行，main task 栈未增大。
- 首屏在 service task 首次延迟前立即显示；后续 deterministic mock 共 24 ticks，覆盖涨、跌、平、涨停、跌停、停牌及穿越昨收。
- display component 提供 LVGL lock 与全帧 flush 计数/耗时指标，业务模型未进入底层显示驱动。

## 自动验证

- `bash scripts/verify-phase-1c.sh`：通过（task-owned startup、19 glyph 字体覆盖、host tests、static checks）。
- `bash scripts/verify-phase-1b1.sh`：通过。
- `bash scripts/build-clean-firmware.sh`：ESP-IDF v6.0.2 完整构建通过；应用大小 `0x125040`，最小 app partition 剩余 92%。
- 构建产物 SHA-256：`addd005d260f343dbaf76f538e5044662f9e7e225f5e1c5ec7332d9bb0c8e8c0`。
- 串口重新探测为 `/dev/cu.usbmodemXXXX`；bootloader、partition table 与应用烧录后均由 esptool 完成 hash 校验。

## 真机证据

- ESP32-S3 从 `SPI_FAST_FLASH_BOOT` 正常启动：16 MB Flash、8 MB octal PSRAM、ESP-IDF v6.0.2、应用版本 `phase-1c`。
- RLCD/LVGL 初始化完成；tick 0 首屏在约 1.58 秒完成，`app_main()` 在约 1.76 秒正常返回。
- Wi-Fi 回归通过：station 连接成功并取得地址；报告不记录凭据。
- 连续观察完整 tick 0→23→0 场景循环约 244 秒，无 FreeRTOS stack overflow、panic、`RTC_SW_CPU_RST` 或循环重启。
- 更新周期约 10.10–10.12 秒；稳定阶段 view wall time 约 107–118 ms，每轮 8 次 full-frame flush。
- 常态 flush 平均约 700–829 µs；观测最大单次 flush 1,586 µs，后续周期恢复正常且无错误。
- internal heap 稳定约 170,171–170,207 B，最大连续块保持 94,208 B；PSRAM free 保持 8,338,364 B，无持续下降。
- 用户目视确认：4 股及中文/价格/涨跌信息正常显示，约 10 秒更新，闪烁/残影与 2–3 米可读性可接受。

## 结论与边界

旧路径的 main task stack overflow blocker 已消除，Phase 1C 验收通过。本阶段未接入真实行情、Stock Gateway、Web 管理、语音或 Phase 1D 能力；Phase 1D 尚未开始。
