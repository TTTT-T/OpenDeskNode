# Phase 1D — Stock Gateway 验收报告

状态：已完成并验收（NAS 容器与非交易时段运行时证据）；按要求不进入 Phase 1E。
日期：2026-08-16

## 目标与实际完成

已在共享工作树实现 Python 3.11/FastAPI/Pydantic/SQLite 的 LAN-only 模块化
单体，包括：

- `device_id` 多设备、数据库约束的固定四槽唯一 watchlist、device-a 默认四股；
- devices、watchlist、settings/service state 和每个 symbol 的 latest snapshot；
  snapshot 仅保留 quote、当前 session intraday、真实 source timestamp、
  `last_success_at` 与 freshness/error 信息，不建长期行情历史；
- Gateway canonical model 与从 current/previous close 重算 change 的边界；
- easyquotation/Tencent quote primary、Baidu direct intraday supplement、
  adata/Sina quote fallback 的固定组合；due quote 使用一次 primary batch，只有
  primary 缺失/不可用的 symbol 才进入一次 fallback batch，并保留逐 symbol 错误；
  intraday 仍逐股、明确 timeout、有限 retry/backoff；
- XSHG session（PRE_MARKET/TRADING/MIDDAY_BREAK/CLOSED/STANDBY）、Asia/Shanghai
  与绝对 `next_open_at`；历史 XSHG schedule 加当前固定中国节假日覆盖；
- `/healthz`、版本化设备/resolve/confirm/watchlist/reorder/status/preview API 与
  `/api/v1/dashboard/{device_id}` 稳定 JSON；dashboard 访问更新最近 ESP 访问时间；
- 无 CDN 的手机优先管理页、Dockerfile、Compose volume/restart/health/log rotation、
  非 root、`.dockerignore`、`.env.example`、NAS hostname/port 部署文档和 provider
  smoke 命令。

## 自动验证结果

在隔离 `/tmp/esp32-phase-1d-venv` 使用固定依赖运行：

```text
33 tests: OK
```

覆盖 repository persistence/order/multi-device/latest-only snapshot、四槽 SQLite
约束、XSHG session boundaries/2026 holiday、缺依赖时默认初始化失败、provider
conversion/change recompute、一次四股 quote batch 与缺失 symbol fallback、
timeout/retry、partial failure/stale/restart fallback、周末/节假日/盘前 startup
最近交易日分时、dashboard schema、Web/API save/reorder、health 和现有 1D.0
boundary。既有 1D.0 测试仍通过。静态 py_compile、`git diff --check` 和
`scripts/verify-phase-1d.sh` 均已通过；脚本同时完成 Docker/Compose/非 CDN Web
静态交付检查。

## NAS 与 LAN 运行时证据

- 目标：QNAP `reference NAS`，x86_64、Container Station 3.1.2、Docker
  27.1.2-qnap8、Compose 2.29.1-qnap2；项目目录为
  `/share/Container/stock-gateway`。
- 完整 pinned image build 成功，Compose 容器 healthy，LAN 地址
  `http://stock-gateway.local:8000/` 与 `http://gateway-host.local:8000/` 可访问；
  `/data` 为 `stock-gateway_stock_gateway_data` named volume，restart policy 为
  `unless-stopped`。
- 首次真实 refresh 四股 quote 4/4、intraday 4/4、无 partial failure；Tencent
  quote 与 Baidu 2026-08-14 分钟数据由实际上游返回，每股 240 条、09:30–15:00。
  四股依次为贵州茅台、平安银行、宁德时代、中芯国际；涨跌额/幅由 Gateway
  使用 current 与 previous close 重算。
- `/healthz` 返回 database ok、refresh worker running；周日 market 为 STANDBY，
  `next_open_at=2026-08-17T09:30:00+08:00`，calendar source 为
  `exchange-calendars/XSHG + chinese-calendar`。
- 390×844 手机视口实际打开 Web，完成已有代码查询、前两槽重排与明确保存；页面
  同时显示 Provider 状态、最近访问和四股实际行情。容器重启后 API 仍返回临时顺序，
  随后已通过 Web 恢复原顺序。
- 从 NAS 主机终止已核实的 Gateway 主进程后，Docker 自动拉起新 PID，
  `restart_count=1`、health healthy、Provider refresh 恢复，证明应用异常退出自恢复。

## 仍未验证（不伪装通过）

- 没有在下一交易时段验证真实 quote 实时推进、Baidu 当日分钟连续更新、实际
  LIMIT_UP/LIMIT_DOWN/SUSPENDED 样本或 Provider 长期限流行为。离线 fake/provider
  conversion 证据不能替代这些运行时证据。
- 没有执行 NAS 全机重启，因为会中断其他容器且阶段文档要求单独确认；已完成
  container restart 持久化和真实应用进程崩溃自恢复。跨日长稳仍需后续观察。

## 重要实现决定与风险

- `watchlist_slots` 使用每个 device 一行、四个固定 slot 列，利用 SQLite CHECK
  保证恰好四个六位代码且唯一；repository/API 保存使用事务更新，不存在短暂的
  “删空再插入”状态。
- Provider 只使用 Phase 1D.0 已确认的三条固定路径，不引入通用 routing framework。
  Service 先汇总所有 due symbol 做一次 Tencent primary batch，fallback 只在该
  股票 primary 缺失/失败时触发；缺少可靠状态证据时返回 `UNKNOWN`。
- 生产默认 `MarketSessionClock` 不再把 XSHG/chinese-calendar 初始化错误降级为
  `WeekdayCalendar`；依赖缺失会明确阻止服务启动，`WeekdayCalendar` 只由测试显式注入。
  startup force 在 `PRE_MARKET` 使用前一交易日，在 `STANDBY` 使用当日向前最近交易日，
  不请求尚未交易的当前 session。
- `exchange-calendars==4.5.6` 的 XSHG 历史数据止于 2025，因此生产依赖同时固定
  `chinese-calendar==1.11.0` 覆盖当前 2026 已发布节假日并明确排除周末补班日。
  依赖更新后应重新跑 calendar tests；更远年份节假日数据仍需随官方发布更新依赖。
- LAN API 暂不登录是已确认边界；不得把端口暴露到公网，也不要把任何凭据写入
  `.env.example`、镜像、测试或文档。
- `call_with_timeout` 仍为每个阻塞 provider operation 创建 daemon worker；本次 batch
  修补把 primary/fallback quote 的 worker 从逐股降为每个 batch 一个，但 intraday
  仍逐股。没有在本次有界修补中改变并发 timeout 机制或新增 cooldown；若上游永久挂起，
  超时 worker 可能在进程退出前持续占用线程，需后续用 transport timeout/cooldown
  单独处理，不能以本地测试替代长稳验证。

## 验收结论

代码、33 项自动测试、NAS Docker build/health、真实四股数据、移动 Web、版本化
dashboard、SQLite 容器重启持久化和进程崩溃恢复均满足 Phase 1D 可到达的验收
门槛，因此本阶段标记完成并验收。下一交易时段补测、真实特殊状态样本、NAS 全机
重启和跨日长稳继续作为明确限制记录；不连接或修改 ESP32 固件，不进入 Phase 1E。
