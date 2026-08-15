# Phase 1C — Stock Display Skeleton（当前 Phase 规划）

- 状态：进行中（规划确立，实现与验收尚未开始）
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

## 非目标

- 不接入真实行情 API、Stock Gateway、Web 管理页或任何配置来源（属 1D/1E）。
- 不实现持仓/成本/盈亏、提醒、详情页（已确认延后，见 [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)）。
- 不实现语音、音频、唤醒词（属 Voice 2A/2B/2C）。
- 不做 loading/stale/error 循环演示；真实失败与降级行为属 1E，本阶段仅在模型中预留字段。
- 不做 RLCD partial update、动画或高帧率刷新。
- BOOT 键只保留已验收的按键捕获，不新增行为。
- 不改动 board/network 已验收行为，除非有明确回归证据。

## 预计模块

- `firmware/product/components/display/` 或独立 dashboard 组件：stock model、stock view 与 4 面板布局（业务不进底层驱动）。
- 确定性 mock 数据源与场景表，按约 10 秒节奏轮换上述场景。
- 测量手段：全帧刷新耗时、heap/CPU 与 LVGL 统计的日志或脚本。
- 不创建股票网络客户端空壳（留待 1D/1E 按需实现）。

## 验收标准（实现前可细化）

- ESP-IDF 完整构建通过；`scripts/verify-phase-1b1.sh` 静态检查不回归。
- 真机 4 等分面板 skeleton：中文名称/现价/涨跌额/涨跌幅与 `▲ +1.25%`、`▼ -0.86%` 格式用户目视确认可读（2–3 米）。
- sparkline 与昨收基线正确渲染；上穿/下穿昨收场景可辨。
- 10 秒确定性场景完整轮换：上涨、下跌、平盘、涨停、跌停、停牌。
- 产出全帧刷新测量记录：闪烁/残影目视结论、刷新耗时、CPU/内存/LVGL 开销。
- 不引入 Xiaozhi 代码或云依赖；组件边界符合 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 风险

- 400×300 单色屏信息密度与中文字体渲染未验证；2–3 米可读性待真机确认。
- ST7305 全帧刷新延迟与残影可能限制 10 秒刷新体验。

## 回滚点

Phase 开始前 Git 基线（当前 `main` @ `4081c2b` 或阶段启动提交）；完成后按 [DELIVERY_WORKFLOW.md](DELIVERY_WORKFLOW.md) 产出阶段报告并提交。
