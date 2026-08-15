# Phase 1D — Stock Gateway

状态：已完成并验收（NAS 容器与非交易时段运行时证据；交易时段补测保留）
启动日期：2026-08-15；验收日期：2026-08-16
前置基线：Phase 1D.0 commit `9546c90`

## 单一目标

在 NAS Docker 上交付可长期运行的 LAN-only Stock Gateway：以统一 canonical
model 为多个 ESP32 device 提供固定四槽 watchlist、真实 A 股 quote 与当日
1 分钟分时、market session、cache/freshness/失败降级、手机优先 Web 管理页和
版本化 HTTP/JSON dashboard API。

## 已确认实现边界

- Python + FastAPI + SQLite + Docker Compose 的模块化单体。
- quote primary 为 easyquotation/Tencent，intraday supplementary 为 Baidu
  direct，quote fallback 为 adata/Sina；只保留清晰 adapter boundary，不实现
  通用多 Provider routing framework。
- 每个 `device_id` 独立拥有恰好四个有序 slot；Web 输入六位 A 股代码后解析
  中文名，显式保存后立即持久化。
- ESP32 后续只轮询 `GET /api/v1/dashboard/{device_id}`；本 Phase 不连接或修改
  ESP32 固件。
- SQLite 只保存 devices、watchlist、配置、最后成功 snapshot 与必要服务状态；
  不建立长期历史行情库。
- Gateway 负责 A 股 session/交易日、`next_open_at`、provider 刷新频率、timeout、
  retry/backoff、per-stock `last_success_at` 和整体 freshness；超过 5 分钟未成功
  刷新标记 stale/error，旧 snapshot 必须保留真实时间戳。
- LAN 内暂不登录、不做公网暴露；凭据不得进入镜像或 Git。稳定地址优先使用
  NAS 的可验证局域网 hostname；若 `stock-gateway.local` 在 QNAP Docker 中不
  可靠，记录可复现替代方案。

## 实现与验收状态

Phase 1D 的 Gateway、离线测试、Docker/Compose、独立 provider smoke、手机 Web
和部署文档已写入仓库，并已部署到 TerrenceNAS。`terrencenas.local:8000`、健康
检查、四股真实 quote/分钟数组、手机 Web 保存与重排、named volume 容器重启
持久化、`unless-stopped` 进程崩溃自恢复均有运行时证据。完整结果见
[Phase 1D 报告](phase-reports/phase-01d-stock-gateway.md)。下一交易时段实时推进、
真实涨跌停/停牌样本和 NAS 全机重启仍明确保留为未验证项；不影响本阶段按已到达
时段的边界验收，也不得把这些项目写成已通过。

## 非目标

- ESP32 联调、Phase 1E、firmware/product 股票 UI 修改。
- Voice、OpenAI、持仓/P&L、alerts、详情页、K 线、长期历史、WebSocket、MQTT、
  SSE、公网访问、账号与复杂权限。
- 为未来供应商预建复杂动态 routing、插件系统或微服务拆分。

## 预计模块

- `gateway/`：应用入口、配置、canonical models、provider adapters、SQLite
  repository、refresh/cache service、market calendar/session、API 与 Web 页面。
- `tests/`：repository、provider conversion、refresh/failure、session、API/Web
  contract 与 persistence tests；真实 Provider/NAS 验收使用独立命令记录。
- `Dockerfile`、`compose.yaml` 与部署文档：healthcheck、`restart: unless-stopped`、
  SQLite volume、约 3 天日志、LAN port/hostname。
- canonical docs 与 `docs/phase-reports/phase-01d-stock-gateway.md`。

## 验收标准

1. NAS Docker 常驻、health 正常、container restart 后自动恢复且 SQLite 配置不丢。
2. Web 手机视口可管理多个 device；每个 device 恰好四槽，可查代码/确认中文名、
   调整顺序并显式保存；状态页显示 provider、最后成功、设备、最近访问与行情预览。
3. 真实四股获得 current price、previous close、change amount/percent、状态字段、
   vendor/data timestamp 与完整当日/上一交易日 1 分钟数组。
4. `/api/v1/dashboard/{device_id}` 一次返回 device、四槽 quote/intraday、market
   session、`next_open_at`、gateway/data timestamp 与 freshness/stale；schema 稳定。
5. 单股失败保留其旧 snapshot、其他股票继续更新；整体超过 5 分钟无成功时 stale；
   Gateway 重启且 Provider 不可用时仍可从 SQLite 返回旧 snapshot，不伪装新数据。
6. cache、timeout、有限 retry/backoff、拉取频率和约 3 天日志策略有自动测试或
   可观察证据；不依赖 Xiaozhi，不修改 Phase 1C UI，不连接 ESP32。
7. 下一交易时段补测 quote 与 Baidu intraday 的实时推进；若本阶段结束时尚未到
   交易时段，必须保留为明确未验证项，不伪装通过。

## 风险、依赖与回滚点

- 免费公开上游无 SLA，字段/反爬策略可能变化；严格日期校验和旧 snapshot 是
  必需边界。真实 LIMIT_UP/LIMIT_DOWN/SUSPENDED 样本尚未命中，不猜状态码。
- QNAP mDNS/container networking、Python 依赖下载和 NAS 全机重启均需要单独
  实测；全机重启会影响其他服务，未经单独确认不执行。
- 回滚点为 commit `9546c90`；实现提交只包含 Phase 1D 文件。部署回滚为停止并
  移除本 Gateway container/compose，保留 SQLite volume 备份，不影响其他容器。
