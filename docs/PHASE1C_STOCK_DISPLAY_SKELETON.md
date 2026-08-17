# Phase 1C — Stock Display Skeleton（当前 Phase 规划）

- 状态：已完成并验收（2026-08-15）
- 入口：[PROJECT_STATE.md](PROJECT_STATE.md)
- 注意：本文件是规划/当前阶段文档；完成后的结果证据按 [DELIVERY_WORKFLOW.md](DELIVERY_WORKFLOW.md) 写入 `docs/phase-reports/`，两者不重复。

## 目标

在 `firmware/product/` 已验收的 RLCD/LVGL 基线上，以确定性 mock 数据打通完整显示链路：

`deterministic mock → stock model → stock view → LVGL → RLCD`

1. 定义 stock model：已确认字段（中文名称、现价、涨跌额、涨跌幅、市场状态、昨收、日内分时序列），并携带 `session` 与 `last_success_update`，为 1E 真实数据与失败降级预留。
2. 单屏 4 个等分面板（4 equal panels），验证中文名称、价格与 2–3 米可读性。
3. 每股渲染日内 sparkline 与昨收基线。
4. mock 场景以约 10 秒节奏确定性轮换，覆盖：上涨、下跌、平盘、涨停、跌停、停牌、上穿/下穿昨收。
5. 测量全帧刷新代价：RLCD 闪烁/残影、CPU、内存与 LVGL 开销。

## 完成结果

`firmware/product/components/stock/` 已实现 model/mock、2×2
LVGL view、约 10 秒刷新 service、CJK/数字字体子集和纯 C99 host test，并加入
`scripts/verify-phase-1c.sh`。这些是 Phase 1C 的实现素材，不是完成态证据。

启动路径已按既定修复边界改为 task-owned：`app_main()` 只调用
`stock_service_start()`；view 创建、mock reset、首屏 view update 与
`lv_refr_now()` 全部在具有明确栈预算（8192 字节）的 stock service task
内、于任务首次约 10 秒延迟之前完成，main task 不再创建或刷新股票 UI，
main task 栈未增大。真机曾观察到旧路径（`app_main()` 直接创建 view、
service start 在 main task 内同步首刷）在 `RLCD and LVGL bootstrap page
ready` 之后触发 main task stack overflow 和 `RTC_SW_CPU_RST` 重启。

该修复已重新构建、烧录并完成写后 hash 校验。真机从 Flash 正常启动，
`app_main()` 返回后 `stock_svc` 完成首屏并稳定跑完整 24-tick 循环，无 stack
overflow、panic 或 reboot；Wi-Fi 正常连接。用户确认 4 股显示、约 10 秒刷新、
闪烁/残影与 2–3 米可读性可接受。完整证据见
[Phase 1C 报告](phase-reports/phase-01c-stock-display-skeleton.md)。

## 非目标

- 不接入真实行情 API、Stock Gateway、Web 管理页或任何配置来源（属 1D/1E）。
- 不实现持仓/成本/盈亏、提醒、详情页（已确认延后，见 [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)）。
- 不实现语音、音频、唤醒词（属 Voice 2A/2B/2C）。
- 不做 loading/stale/error 循环演示；真实失败与降级行为属 1E，本阶段仅在模型中预留字段。
- 不做 RLCD partial update、动画或高帧率刷新。
- BOOT 键只保留已验收的按键捕获，不新增行为。
- 不改动 board/network 已验收行为，除非有明确回归证据。

## 预计模块

- `firmware/product/components/stock/`：stock model、确定性 mock、stock view、刷新 service、字体子集和 host test；业务不进底层驱动。
- `firmware/product/components/display/`：ST7305/LVGL transport、display lock 和全帧刷新指标，不持有股票模型。
- 确定性 mock 数据源与场景表，按约 10 秒节奏轮换上述场景。
- 测量手段：全帧刷新耗时、heap/CPU 与 LVGL 统计的日志或脚本。
- 不创建股票网络客户端空壳（留待 1D/1E 按需实现）。

## 验收标准（实现前可细化）

- `bash scripts/verify-phase-1c.sh` 静态检查与 host test 通过；ESP-IDF 完整构建通过；`scripts/verify-phase-1b1.sh` 静态检查不回归。
- 真机 4 等分面板 skeleton：中文名称/现价/涨跌额/涨跌幅与 `▲ +1.25%`、`▼ -0.86%` 格式用户目视确认可读（2–3 米）。
- sparkline 与昨收基线正确渲染；上穿/下穿昨收场景可辨。
- 10 秒确定性场景完整轮换：上涨、下跌、平盘、涨停、跌停、停牌。
- 产出全帧刷新测量记录：闪烁/残影目视结论、刷新耗时、CPU/内存/LVGL 开销。
- 不引入 Xiaozhi 代码或云依赖；组件边界符合 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 风险

- 400×300 单色屏信息密度与中文字体已经本阶段目视验收；后续真实行情内容密度变化仍需在 1E 重新评估。
- ST7305 全帧刷新延迟与残影可能限制 10 秒刷新体验。

## 回滚点

Phase 开始前记录当前 `main` 的实际 Git 基线（以当时的 `git rev-parse --short HEAD` 为准）；完成后按 [DELIVERY_WORKFLOW.md](DELIVERY_WORKFLOW.md) 产出阶段报告并提交。
