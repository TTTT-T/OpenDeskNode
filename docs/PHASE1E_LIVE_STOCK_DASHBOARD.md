# Phase 1E — Live Stock Dashboard

状态：已完成并验收
启动日期：2026-08-16
验收日期：2026-08-16
前置基线：Phase 1D 已在 TerrenceNAS 验收

## 单一目标

把 `firmware/product` 的 4 股看板从确定性 mock 切换为自有 LAN Stock
Gateway 真实数据，完成可配置设备身份、约 10 秒轮询、固定 32 点分时、
市场时段、旧数据保留和超过 5 分钟全局异常的真机闭环。

## 已确认实现边界

- ESP32 只请求自有 Gateway 的
  `GET /api/v1/dashboard/{device_id}`；不直连 Provider，不持有行情凭据。
- Gateway 保持默认 Phase 1D 完整响应，增加可选
  `intraday_samples=32` 有界降采样；保留首尾、顺序和每股分时对应关系。
- Gateway base URL 和 `device_id` 使用无秘密的 Kconfig 构建配置；默认使用
  已验证的 LAN IP `http://192.168.31.209:8000` 与 `device-a`。
- stock service 拥有 HTTP、JSON 转换、最后成功 snapshot 和 LVGL 更新；
  `app_main()` 仍只启动 service，不直接触碰股票 UI。
- 首次成功前不显示伪造行情；HTTP、非 2xx、超时、schema 或字段失败时
  保留最后成功数据。连续失败未超过 5 分钟不显示异常，超过后显示
  全局行情异常；Gateway 自身 `stale=true` 立即触发同一降级。
- 生产数据路径不再使用 mock；纯 C99 model/mock 仍保留为回归测试资产。
- 不进入 Voice 2A，不实现详情页、持仓、提醒、OTA、公网访问、
  WebSocket/MQTT/SSE 或新的网关发现协议。

## 预计模块

- `gateway/service.py` / `gateway/app.py`：默认不变的可选分时降采样。
- `firmware/product/components/network/`：只读连接状态，不改 Wi-Fi 凭据模型。
- `firmware/product/components/stock/`：Gateway client/parser、数据状态、轮询
  service 和 2×2 view 状态条。
- `tests/` 与 `scripts/verify-phase-1e.sh`：API 降采样、JSON 转换、非法响应、
  失败保留、超时降级、静态边界和干净构建。

## 验收标准

1. 默认 dashboard API 保持 Phase 1D schema；`intraday_samples=32` 对四股各返回
   最多 32 点且保留首尾，非法参数返回 422。
2. 固件只在 Wi-Fi 就绪后请求配置的 LAN Gateway，严格要求 schema v1、
   四股、有效价格和有界分时；变换为分价定点模型时不泄漏 provider 字段。
3. 真机开机后自动显示 Gateway Web 中 `device-a` 的四股与真实数据，
   价格/涨跌与 API 一致，分时线存在，约 10 秒轮询。
4. 断开 Gateway 或无效响应不清空已显示行情；恢复后无需重启自动回到
   fresh。超过 5 分钟的异常状态用自动测试加可控时钟验收。
5. 交易中、盘前、午间、收盘和休市待机状态从 Gateway canonical
   session 映射；`UNKNOWN` 不猜涨跌停/停牌。
6. Phase 1C model/mock host 回归、Phase 1D API 回归、Phase 1E 脚本、
   `git diff --check` 和 ASCII `/private/tmp` 干净 ESP-IDF v6.0.2 build 通过。
7. 烧录后串口无 panic、stack overflow、reboot loop 或持续内存下降；
   显示与可读性由真机证据验收，不以 build 代替。

## 风险与回滚点

- `.local` 在当前主机检查中曾发生 DNS timeout；默认固件先使用已验证
  NAS LAN IP，后续地址变更通过 Kconfig 构建配置处理。
- 字体覆盖边界为 ASCII、固定 Source Han Sans SC 可提供的基础汉字区
  U+4E00–U+9FEF 及涨跌箭头；
  区间外字符仍不保证显示。
- 返回数据仍来自无 SLA 免费上游；固件只信任 Gateway canonical 字段和
  freshness，不从价格自行推测特殊状态。
- 回滚点为 Phase 1D 已验收提交；固件回滚只恢复 mock service，Gateway
  降采样参数为可选且默认不变，可独立保留。
