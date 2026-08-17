# Phase 1E — Live Stock Dashboard 验收报告

- 日期：2026-08-16
- 结果：通过
- 前置基线：Phase 1D commit `6f3e103`
- 范围：LAN Stock Gateway → HTTP/schema v1 → stock model → LVGL → ST7305 RLCD

## 实现结果

- Gateway 保持默认 Phase 1D dashboard 响应兼容，增加可选
  `intraday_samples=32` 端点保持降采样；非法范围返回 422。
- 固件只在 Wi-Fi 就绪后访问 Kconfig 配置的 LAN Gateway，严格解析 schema v1、
  恰好四股、有效定点价格、canonical 市场状态和最多 32 个分时点。
- `stock_svc` 约 10 秒轮询并持有 last-good snapshot。短时 HTTP/schema/网络
  失败不清屏，超过 5 分钟才显示全局异常及最后成功时间；Gateway stale 立即
  进入同一状态。
- 盘前和午间状态显示下一次开盘的分钟倒计时；周末/节假日显示休市待机。
- 24 px 字体覆盖 ASCII、U+4E00–U+9FEF 与涨跌箭头，常规 Web 管理的 A 股
  简称不依赖固件名称白名单；LVGL 使用大字体索引。

## Gateway 与自动验证

- NAS 一次性测试容器运行完整 34 项测试通过；生产容器重新构建后 health 为
  healthy，refresh worker 正常，quote primary 与 intraday supplementary 为
  OK，未触发的 quote fallback 保持 UNKNOWN。
- 真实 dashboard 完整响应约 361 KB，32 点投影约 52356–52378 B；四股均为
  32 点，首尾点与完整响应一致。
- `bash scripts/verify-phase-1c.sh`、`bash scripts/verify-phase-1e.sh` 与
  `git diff --check` 通过；包括纯 C99 model/mock、严格 cJSON parser、5 分钟
  failure grace、完整声明字形区间和 Gateway 降采样回归。
- ESP-IDF v6.0.2 干净构建通过；应用大小 `0x2c7b50`，15 MiB app partition
  剩余 81%。最终固件 SHA-256：
  `7fa1c1eab02f89b8fa382d0917ac1ac6624ce1adb76e2e241454bd5949b98e3d`。

## 部署与真机证据

- NAS 只替换 `gateway/app.py` 与 `gateway/service.py`，原文件保存在
  `.phase1e-backup-20260816-133309/`；未重启 NAS 或其他容器。
- 在既有双份 16 MB 原厂备份门槛已满足的前提下，通过
  `/dev/cu.usbmodemXXXX` 无 erase-all 烧录；bootloader、partition table 与
  application 均由 esptool hash 校验。
- 真机启动识别 ESP32-S3 rev v0.2、16 MB Flash、8 MB PSRAM 和应用
  `phase-1e`；Wi-Fi 自动连接后每轮取得约 52 KB 响应并刷新 4 股。
- 同一 HTTP/parser/view 路径连续观察 20 个周期，TCP `TIME_WAIT` 缓存收敛后
  internal heap 稳定约 157.86 KB，PSRAM 稳定约 8.338 MB；最终固件再次观察
  连续成功周期，无 panic、stack overflow 或 reboot loop。
- 用户提供的真机照片显示贵州茅台、平安银行、宁德时代、中芯国际四股名称、
  价格、涨跌百分比、四条分时线和“休市待机 09:30”完整可见；数值与 Gateway
  一致，未见缺字、截断、重叠或明显残影。

## 结论与保留边界

Phase 1E 的真实 4 股 LAN 看板闭环通过验收。2026-08-16 为非交易日，本报告不把
下一交易时段 quote/分钟实时推进、真实涨停/跌停/停牌样本、NAS 全机重启或跨日
长稳伪装为已验证；这些仍作为后续补测。Voice 2A 未开始。
