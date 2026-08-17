# Phase 1D.0 — A 股 Provider Bake-off

- 日期：2026-08-15（周六）
- 结果：非交易日/收盘后验收通过；组合为 quote primary easyquotation/Tencent、intraday supplementary Baidu direct、quote fallback adata/Sina
- 当前边界：Phase 1D.0 已满足非交易时段完整分钟数据门槛并可标记 accepted；下一交易时段实时更新仍待实测，尚未进入完整 Gateway
- 范围：服务端最小 Provider boundary、六条候选路径的真实调用、固定四股、可复现实测配置/脚本/自动测试和审计结果

## 测试对象与固定输入

固定测试集写入 [phase-01d0-provider-bakeoff.json](../../config/phase-01d0-provider-bakeoff.json)：

600519（贵州茅台）、000001（平安银行）、300750（宁德时代）、688981（中芯国际）。

实测候选：

1. AKShare 1.18.88 / Eastmoney（stock_zh_a_spot_em、stock_zh_a_hist_min_em）。
2. adata 2.9.5 / Sina。
3. adata 2.9.5 / Tencent。
4. easyquotation 0.7.7 / Sina。
5. easyquotation 0.7.7 / Tencent；其可选 timekline 也被单独调用。
6. Baidu direct `quotation_minute_ab`；stdlib HTTP/JSON 直连，不经过 adata parser。

所有候选均通过无 token 的公开接口调用；本次没有账户、token 或付费 API
配置，也没有产生可计费调用。这个事实不等于上游长期免费、无 SLA 或没有
限流。

## 环境、安装与 Docker 限制

- 主机：macOS Darwin 26.6.1，arm64，Python 3.9.6；不是 Linux。
- 隔离环境：/tmp/esp32-phase-01d0-venv。
- 实际安装命令：
  python3 -m pip install --disable-pip-version-check --no-cache-dir akshare adata easyquotation
  ，成功安装上述三个版本；固定复现版本另见
  [phase-01d0-provider-bakeoff-requirements.txt](../../config/phase-01d0-provider-bakeoff-requirements.txt)。
- `baidu-direct` 不增加第三方依赖，使用 Python 标准库直连公开
  `finance.pae.baidu.com/selfselect/getstockquotation`；本次主机网络实测成功。
- 开发主机的 command -v docker 和 docker --version 均为 command not found；
  macOS harness 因此记录 docker_available=false。
- Codex 主模型随后在目标 QNAP NAS（x86_64 Linux、Container Station 3.1.2、
  Docker client/server 27.1.2-qnap8）拉取官方 `python:3.11-slim`，用 `--rm`
  临时容器复核推荐组合。10/10 单测通过；固定版 `easyquotation==0.7.7`
  安装成功（PyPI 首次请求一次 15 秒 read timeout 后重试成功）；容器内四股
  Tencent quote 4/4，Baidu direct 四股各 240 条，日期均为 2026-08-14、
  首尾 09:30/15:00。该证据只证明 provider 组合的 Linux/NAS Docker
  兼容性，不等于完整 Gateway 已部署或长稳验收。
- 维护状态只记录可观察的包发布证据，不把它扩大成稳定性承诺：PyPI JSON
  查询显示 AKShare 最新版为 1.18.91（2026-08-13 上传；本次固定安装
  1.18.88），adata 2.9.5 于 2025-12-26 发布，easyquotation 0.7.7 于
  2025-03-25 发布。adata 项目页为
  <https://github.com/1nchaos/adata>，easyquotation 项目页为
  <https://github.com/shidenggui/easyquotation>。

## 最小 Provider boundary

新增 [gateway/stock_provider](../../gateway/stock_provider/)：

    resolve_symbol(symbol)
    get_quotes(symbols)
    get_intraday(symbol, trading_date, start_time, end_time)

每个 adapter 在边界内完成代码前缀、字段、日期和状态转换，向上只返回
canonical SymbolRef、Quote、IntradayBar。没有实现完整 Gateway、cache、
watchlist、web 管理、HTTP API、复杂 routing、数据库或权限设计。

自动测试覆盖接口形状、代码归一化、Tencent quote 的昨收/涨跌停/时间戳转换、
1 分钟行转换、Baidu 中文金额/`oriAmount`/epoch/日期不匹配/malformed response
和 provider-neutral model。原始 provider 行只保留在本次审计的摘要 JSON 中，
不穿透边界。

## 能力矩阵与真实结果

| 候选 | resolve | 四股批量 quote | Quote 字段实测 | 首次/后续延迟（ms） | 1 分钟实测 | 连续稳定性 |
| --- | --- | --- | --- | --- | --- | --- |
| AKShare/Eastmoney | 4/4 | 失败 | RemoteDisconnected，无 quote 结果 | 两次失败 | 同一错误；连续两次后停止 | 未形成成功样本 |
| adata/Sina | 4/4 | 4/4，3 次 | 名称、价、涨跌、昨收（由价-涨跌换算）；无 timestamp/涨跌停，状态 UNKNOWN | 252.1 / 118.3 / 96.6 | None；连续两次后停止 | 3/3 覆盖，canonical 值完全一致 |
| adata/Tencent | 4/4 | 空，连续两次 | 空 DataFrame；无 canonical quote | 两次失败 | None；连续两次后停止 | 无成功样本 |
| easyquotation/Sina | 4/4 | 4/4，3 次 | 名称、价、涨跌、昨收、timestamp；无涨跌停，状态 UNKNOWN | 85.3 / 63.9 / 61.0 | 适配器明确不支持 | 3/3 覆盖，canonical 值完全一致 |
| easyquotation/Tencent | 4/4 | 4/4，3 次 | 名称、价、昨收、涨跌、涨跌幅、timestamp、涨停价、跌停价；状态 NORMAL | 122.7 / 105.2 / 95.3 | 每股 205/208/208/205 行，全部是 2021-10-08 陈旧数据 | 3/3 覆盖，canonical 值完全一致 |
| Baidu direct | 4/4 | 明确不支持 quote | intraday-only；不猜 `stockStatus`/`upDownStatus` 数字语义 | 503.1/259.7/279.4、295.5/301.3/394.3、431.2/368.4/314.1、623.8/254.4/405.5（按四股） | 每股 240 行×3 轮；2026-08-14，09:30–15:00 | 4/4×3，日期一致，无限流标记 |

延迟是每次 provider 进程内的 wall time；quote 的三项是首次/后续两轮，
Baidu direct 的每股三项也是首次/后续两轮，轮间隔 1 秒。审计 harness 在
同一错误连续两次后停止，避免把上游异常扩大成压力测试。

矩阵中的 resolve 4/4 对 adata 和 easyquotation 表示本地六位代码/交易所前缀
归一化；这些库的该调用没有额外远程代码表校验。AKShare 则实际调用了
stock_info_a_code_name 代码表并解析到四股。

### Baidu direct 三轮 intraday 明细

请求日期为 2026-08-14；每项为首次/后续两轮 wall latency，三轮均为 240
条有成交分钟，首尾时间与日期一致。

| 代码 | 第 1 轮 ms | 第 2 轮 ms | 第 3 轮 ms | 行数/轮 | 首尾时间 |
| --- | ---: | ---: | ---: | ---: | --- |
| 600519 | 503.1 | 259.7 | 279.4 | 240 | 09:30–15:00 |
| 000001 | 295.5 | 301.3 | 394.3 | 240 | 09:30–15:00 |
| 300750 | 431.2 | 368.4 | 314.1 | 240 | 09:30–15:00 |
| 688981 | 623.8 | 254.4 | 405.5 | 240 | 09:30–15:00 |

### Quote 字段与昨收

easyquotation/Tencent 的三轮四股结果一致，最终一次的固定样本为：

| 代码 | 中文名 | 现价 | 昨收 | 涨跌 | 涨跌幅 | 状态 | 涨停价 | 跌停价 | vendor timestamp |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| 600519 | 贵州茅台 | 1341.99 | 1355.29 | -13.30 | -0.98% | NORMAL | 1490.82 | 1219.76 | 2026-08-14 16:14:43 +08:00 |
| 000001 | 平安银行 | 11.11 | 11.25 | -0.14 | -1.24% | NORMAL | 12.38 | 10.13 | 2026-08-14 16:14:15 +08:00 |
| 300750 | 宁德时代 | 393.93 | 396.30 | -2.37 | -0.60% | NORMAL | 475.56 | 317.04 | 2026-08-14 16:14:00 +08:00 |
| 688981 | 中芯国际 | 132.87 | 129.44 | +3.43 | +2.65% | NORMAL | 155.33 | 103.55 | 2026-08-14 16:14:36 +08:00 |

本次四股没有处于涨停或跌停，因此没有验证 LIMIT_UP / LIMIT_DOWN 的
真实命中路径。Tencent 的 NORMAL 是 adapter 用 provider 返回的限价和现价
比较得到的；adata/Sina 与 easyquotation/Sina 没有足够的限价字段，保留
UNKNOWN，不猜测成 NORMAL。

本次四股也没有可靠的停牌命中样本；Baidu 响应中的 `upDownStatus` 和其他
状态字段未被映射成 canonical 状态，不猜测其数字或空值语义。`NORMAL` 仅
表示 Tencent 的现价没有命中其返回的涨跌停价，不代表已验证所有市场状态。

## 周六、收盘后与 1 分钟行为

审计运行时间为 2026-08-15 22:49（Asia/Shanghai）。今天是周六；报告把
`observation_date=2026-08-15` 与明确的 `intraday_request_date=2026-08-14`
分开，验证上一交易日完整分钟数据，绝不把旧日期伪装成周六实时数据。下一
交易时段的实时更新仍不在本次验收范围。

- Quote 端点仍能返回上一交易日（2026-08-14）的收盘后快照；timestamp 也反映
  上游最后 tick 时间，不应伪装成 2026-08-15 实时价。
- Baidu direct 直接读取 `Result.priceinfo`，四股连续 3 轮均成功；每股每轮
  240 条有成交分钟，日期均为 2026-08-14，首尾均为 09:30/15:00。响应中
  原始 `price`、`oriAmount` 被保留为 canonical 数值；`amount` 的中文展示
  单位不参与解析。`volume`/`oriAmount` 均为零或 `--` 的闭市补点被明确
  排除，因此不把 15:06–15:30 之类的补点报告成成交分钟。
- AKShare/Eastmoney 的当前日期 1 分钟请求收到
  RemoteDisconnected；不能区分为“周六无数据”还是当前上游连接策略，
  所以不作成功或无数据结论。
- adata/Sina 与 adata/Tencent 的 get_market_min 返回 None。adata 的
  handler 把上游异常吞掉，适配器只能准确记录为空/不可观测。
- easyquotation/Sina 没有当前 1 分钟接口。
- easyquotation/Tencent timekline 返回了四股数据，但所有行的日期都是
  2021-10-08（每股 205 或 208 行），请求日期匹配为 false；这是陈旧数据，
  不是周六待机数据，已明确排除。harness 现在把日期一致性作为每轮独立字段。

## 频率、限流与 fallback

- quote：每个候选最多 3 次四股批量调用，调用间隔 1 秒；不并行、不轮询
  全市场。intraday：每个候选按四股顺序逐一调用，每股 3 轮、轮间隔 1 秒；
  能力缺失或连续两次失败即停止。Baidu direct 的 4 股均完成 3 轮。
- 错误文本没有出现 429、Too Many、rate limit、限流等标记；这只能说明本次
  短调用未观察到限流，不能证明不存在配额。
- 上游来源：AKShare 函数文档/实现指向 Eastmoney；adata 直接走 Sina
  hq.sinajs.cn 或 Tencent qt.gtimg.cn；easyquotation quote 走相应
  Sina/Tencent 端点，timekline 走 Tencent data.gtimg.cn；Baidu direct 使用
  公开 `finance.pae.baidu.com` `quotation_minute_ab` endpoint。
- fallback 难度：quote fallback 容易（easyquotation/Tencent ↔ adata/Sina
  都能稳定覆盖四股），但两者字段不对称，必须在 canonical 层保留
  timestamp/涨跌停缺失语义；intraday supplementary 现在有 Baidu direct，
  但仍需下一交易时段验证实时变化和更长稳定性。

## 默认与备用结论

本阶段给出清晰但仍有边界的组合建议，不把它写成完整生产路由：

- **Quote primary：easyquotation/Tencent。** 四股覆盖、3/3 连续稳定，并同时
  提供昨收、timestamp、涨停价、跌停价和可推导状态。
- **Intraday supplementary：Baidu direct。** 四股×3 轮均返回 2026-08-14
  的 240 条有成交分钟，日期一致；它明确不承担 quote，且不猜
  `stockStatus`/`upDownStatus` 数字语义。
- **Quote fallback：adata/Sina。** 四股覆盖、3/3 值稳定且后续延迟低；代价
  是 timestamp、涨跌停和 intraday 能力缺失，不能独立替换完整 canonical
  provider。
- 不选 AKShare/Eastmoney 或 adata/Tencent 为当前备用：前者两类请求都失败，
  后者 quote 为空且 intraday 为 None。
- 不接受 easyquotation/Tencent 的 timekline 作为 intraday：返回
  2021-10-08 陈旧数据。上述组合只完成 Phase 1D.0 非交易时段验收，不等于
  已验证交易时段实时更新，也不提前实现 Gateway routing。

## 可复现验证与交付物

- bash scripts/verify-phase-1d0.sh：通过，10 个 boundary/config tests passed。
- PYTHONPYCACHEPREFIX=/tmp/esp32-phase-01d0-pycache python3 -m py_compile gateway/stock_provider/*.py scripts/phase-01d0-provider-bakeoff.py tests/test_stock_provider_boundary.py：通过。
- PYTHONPYCACHEPREFIX=/tmp/esp32-phase-01d0-pycache /tmp/esp32-phase-01d0-venv/bin/python scripts/phase-01d0-provider-bakeoff.py --config config/phase-01d0-provider-bakeoff.json --output docs/phase-reports/phase-01d0-provider-bakeoff-results.json：主机网络完成真实调用；Baidu direct 四股各 3 轮成功，失败仍按上文保存。
- NAS Docker 独立复核：`python:3.11-slim` 中 10/10 单测通过；安装
  `easyquotation==0.7.7` 后，推荐组合真实返回四股 quote 4/4 与四股各
  240 条 intraday。一次性容器和测试目录在复核后清理。
- git diff --check：通过。
- 机器可读原始摘要见
  [phase-01d0-provider-bakeoff-results.json](phase-01d0-provider-bakeoff-results.json)；
  顶层 `assessment` 固化了本阶段组合建议与未验证边界；不含 token、密码或
  其他秘密。

## 未解决问题与下一步

1. 下一交易时段复测 quote 实时更新时间、Baidu direct 当日分钟行数/首尾变化和
   更长稳定性；当前周六/上一交易日证据不能替代交易时段实时证据。
2. 本次四股未命中 LIMIT_UP/LIMIT_DOWN，也未形成停牌命中样本；需要可靠
   master-data/限价语义后再扩大状态覆盖，不能猜测 `stockStatus` 数字语义。
3. Provider 组合的 NAS Linux/Docker 兼容性已通过一次性容器验证；完整 Gateway
   的 compose、资源、进程管理、持久化、重启恢复、网络策略和长稳留到 Phase 1D。
