# Stock Gateway NAS 部署与验收记录

状态：2026-08-16 已部署并完成 Phase 1D NAS/非交易时段验收。目标为 QNAP
`TerrenceNAS`（x86_64、Container Station 3.1.2、Docker 27.1.2-qnap8）；本文不把
`stock-gateway.local` 当作自动存在的地址。

## 地址与边界

容器只监听 `0.0.0.0:8000`（容器内端口），宿主 LAN 端口由
`STOCK_GATEWAY_PORT` 配置。当前可复现 LAN 地址为：

```text
http://terrencenas.local:8000/
http://192.168.31.209:8000/
```

Compose service name `stock-gateway` 只在 Docker 网络内部有效。实现没有启动
mDNS，也不会让容器自动拥有 `stock-gateway.local`。如需稳定名称，应使用 QNAP
主机自己的 hostname/DNS 或路由器静态 DHCP/DNS 记录；不要把 `.local` 当作验收
通过的证据。

## 当前部署

- Compose 项目目录：`/share/CACHEDEV3_DATA/Container/stock-gateway`
- 容器：`stock-gateway-stock-gateway-1`
- image：`stock-gateway-stock-gateway`
- named volume：`stock-gateway_stock_gateway_data`，挂载到 `/data`
- restart policy：`unless-stopped`
- `.env` 从 `.env.example` 创建；本阶段 Provider 无 token，文件未进入 Git。

首次构建期间 Docker Hub 与 PyPI 各发生一次网络超时；基础镜像重试拉取、运行依赖
完全固定并增加有限 pip retry/timeout 后构建成功。这些外部网络错误不属于 Gateway
代码或 NAS 故障。

## 首次部署步骤

在 NAS 上选择一个仅供此项目使用的 Container Station 项目目录，将本仓库交给
Compose，先复制安全默认配置：

```bash
cp .env.example .env
# 按需编辑 STOCK_GATEWAY_PORT、STOCK_GATEWAY_DATA_DIR 和 hostname。
docker compose build
docker compose up -d
docker compose ps
```

`.env` 不应加入 Git；本 Phase provider 不需要 token 或密码。默认使用 Docker
named volume `stock_gateway_data`，容器内挂载为 `/data`，SQLite 文件和应用日志
都会留在该 volume。若改成 QNAP bind path，先确保宿主目录允许 UID 10001
（生产用户 `gateway`）写入；不要因权限方便而把容器改回 root。

## 最小验证

```bash
curl --fail http://127.0.0.1:${STOCK_GATEWAY_PORT:-8000}/healthz
curl --fail http://TerrenceNAS:${STOCK_GATEWAY_PORT:-8000}/api/v1/dashboard/device-a
```

随后打开根路径的手机管理页，确认 `device-a` 的四槽和固定四股。保存一个已
确认代码后检查：

1. `POST /api/v1/devices/{device_id}/watchlist` 返回 `saved: true`；
2. SQLite volume 中配置仍存在；
3. 重启 container 后再次读取同一个 dashboard；
4. dashboard 访问会更新 `device.last_accessed_at`，只读设备/preview/status
   不会更新它；
5. 运行独立的温和真实 Provider smoke（只在主模型授权并选择时间后）：

```bash
python3 scripts/stock-provider-smoke.py --intraday-date YYYY-MM-DD
```

真实 smoke 不是离线测试；遇到节假日或 Provider 上游失败时应保留原始结果，
不要把它改写成伪造成功。

## 备份与日志

停止本 Gateway container 后，再备份 `/data/stock-gateway.sqlite3` 及
`/data/logs/stock-gateway.log*`。不要删除或覆盖其他 QNAP 项目数据。应用同时
写 stdout 和 `/data/logs/stock-gateway.log`，按午夜轮换并保留 3 个备份；Compose
的 Docker `json-file` 日志限制为 `10m × 3`。这两层策略都不是长期历史行情库。

## 验收结果

- [x] `terrencenas.local` 解析与 LAN IP/8000 实际访问。
- [x] Container Station build、启动、healthcheck、非 root、日志策略和
  `restart: unless-stopped`。
- [x] 手机 390×844 视口真实操作：设备列表、四槽、代码查询、中文名、重排、
  明确保存、Provider 状态与四股行情预览。
- [x] 临时调换前两槽后重启容器，SQLite named volume 保留顺序；随后通过 Web
  恢复 `600519/000001/300750/688981` 原顺序。
- [x] 从 NAS 主机终止已核实的 Gateway 主进程，Docker 自动拉起新 PID；
  `restart_count` 从 0 变为 1，health 恢复为 `healthy`。
- [x] dashboard 返回四股 current/previous close/change、真实 vendor/data time，
  每股 240 条 2026-08-14 分钟数据及 STANDBY/next open/freshness。
- [x] 自动测试覆盖单股失败保留旧 snapshot、其他股票继续更新、5 分钟 stale、
  Provider 不可用时重启从 SQLite 返回旧 snapshot。
- [ ] 下一交易时段 quote 实时变化、Baidu 当日分钟连续推进；2026-08-16 为周日，
  当前只能诚实验收上一交易日数据。
- [ ] NAS 全机重启；会中断其他容器，未经单独确认未执行。容器重启与应用崩溃
  恢复已经覆盖本阶段低风险运行时路径。
