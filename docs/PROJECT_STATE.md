# 项目当前状态

最后更新：2026-08-18

本文件是当前阶段与状态的唯一入口。新会话从这里定位当前 Phase 与最近相关报告，再按需读取指向的 canonical 文档；不为背景加载全部阶段报告或 `docs/archive/`。

## 当前 Phase

**[Phase 2B — OpenClaw GPT-Live Realtime Architecture Validation]
(PHASE2B_GPT_LIVE_REALTIME_VALIDATION.md)** — Software Complete
（[报告](PHASE2B_REALTIME_VALIDATION_REPORT.md)）。产品主链 R1/R2 PASS；
R0 浏览器 WebRTC FAIL（模型不支持，非产品路径）。允许进入 ESP32 Voice
Bridge 接口设计。

2026-08-18 用户冻结新的语音架构方向并暂停旧路线：

- 新主链：ESP32（音频边缘：双麦/AEC/VAD/本地唤醒“你好 EVA”/ES8311/PCM）→
  Mac mini **EVA Voice Bridge**（薄桥）→ NAS **OpenClaw Gateway** →
  **OpenAI Realtime `gpt-realtime-2.1`**（实时听说/VAD/连续对话/打断）→
  `openclaw_agent_consult` → **OpenClaw EVA Agent**（memory/tools/HA/日历/自动化）。
- ESP32 不承担 STT/TTS/LLM/Agent；一切基于 “STT → OpenClaw → TTS” 的旧开发
  停止。R0–R2 全部 PASS 前禁止：自建 streaming STT/TTS、Whisper 主链、旧
  Voice Gateway、ESP32 直连 OpenAI、ESP32 承担 OpenClaw 协议、为未验证架构
  大规模重构、ESP32 集成开发（禁止清单见阶段定义）。
- **Phase 2A 已由用户验收**（2026-08-18 确认），其硬件基线重新作为开发起点，
  不得破坏：双麦采集（ES7210）、ES8311、16 kHz/16-bit PCM、AEC、录音/播放
  测试、稳定性基线（证据：[PHASE2A_REPORT.md](PHASE2A_REPORT.md)）。
- R0–R2 为用户人工执行项（Mac 浏览器 + ChatGPT OAuth + 真人中文语音）；
  Agent 负责记录模板、结果分析与报告定稿。
- ADR-0006 中 “Mac 本地 ASR/LLM/TTS Compute Node” 路线自 2026-08-18 起停止
  驱动开发；正式 ADR 变更待 R0–R2 结论后随下一阶段架构决策创建。

### 分支拓扑（2026-08-18 起）

- **`phase-2b-realtime`（本分支，基线 `6982053`）**：自 Phase 2A 验收态切出，
  新的语音开发主线。固件为纯 2A 状态（无 voice 组件）。
- **`dev`（`45bc6f8`）**：保留旧 Phase 2B（VOICE_PROTOCOL v1 + Mock Gateway，
  软件完成）与文档重组；实验资产，不删除、不合并。
- **`phase-2b-r`（`9cd984b`）**：保留 ADR-0007 Voice Edge 重构与协议 v2
  （软件完成即被 realtime 方向取代）；实验资产，不删除、不合并（其
  conversation/turn 语义可在 Bridge 设备侧协议设计时参考）。
- 历史阶段状态不变：Phase 1E/1D/1D.0/1C/1B.1 已完成并验收，股票链路不受
  语音方向调整影响。

### Phase 1E（已完成并验收，2026-08-16）

用户于 2026-08-16 要求继续开发，原“停在 Phase 1D”指令已解除；本阶段只完成
ESP32 读取自有 LAN Stock Gateway 的真实 4 股看板，不进入 Voice 2A。

实现、NAS 部署、串口运行与用户照片目视验收已完成：Gateway 完整 34 项测试
通过，默认响应兼容，32 点投影在真实数据上由 361277 B 降至约 52370 B；
最终固件已无擦除烧录，连续轮询返回 `ESP_OK`，无 panic、重启或持续内存下降。
四股中文名称、价格、涨跌、分时线和休市待机状态在真机照片中完整可见，
无缺字、截断或重叠。验收报告见
[Phase 1E 报告](phase-reports/phase-01e-live-stock-dashboard.md)；下一交易时段
实时推进仍是独立补测。
（2026-08-16 复核：`verify-phase-1e.sh` 与 34 项 Gateway 测试在干净 venv
中重跑全部通过。）

Phase 1C 已完成并验收（commit `c2031a7`）；Phase 1D.0 已完成并验收
（commit `9546c90`），推荐 quote primary easyquotation/Tencent、intraday
supplementary Baidu direct、quote fallback adata/Sina。Phase 1D Gateway 已在
TerrenceNAS Container Station 部署并完成 LAN Web/API、真实四股数据、SQLite
volume、容器重启持久化和进程崩溃自动恢复验收；不连接 ESP32、不修改 Phase 1C
UI，不进入 Phase 1E。

## Phase 1D.0 范围与验收

### 目标

在服务端定义最小可复用 Provider boundary，并用固定四股对
AKShare/Eastmoney、adata/Sina、adata/Tencent、easyquotation/Sina、
easyquotation/Tencent 和 Baidu direct 做真实、低频、短连续调用，记录 quote
与上一交易日 1 分钟行为、字段覆盖、延迟、稳定性、限流/失败、部署限制和
维护风险。Baidu direct 通过公开 `quotation_minute_ab` endpoint 绕过 adata
失效 parser；2026-08-15 为周六，本次只验收非交易日/收盘后表现，交易时段
实时更新留待下一交易时段实测。

### 非目标

- 不实现完整 Stock Gateway、cache、watchlist、web 管理、HTTP API 或复杂 routing。
- 不改 `firmware/product`，不读取 `firmware/xiaozhi`，不接入 ESP32 真行情。
- 不做数据库/schema、权限、安全/认证设计，不引入 provider token。
- 不把一次周六观察写成下一交易时段实时能力；不把 provider 容器兼容性
  验证扩大成完整 Gateway 已部署或长稳通过。

### 预计模块与文件

- `gateway/stock_provider/`：Provider protocol、canonical `Quote`/`IntradayBar`
  与 adapter-local conversion。
- `config/phase-01d0-provider-bakeoff.json` 及 pinned requirements：固定测试集、
  候选和可复现安装配置，无秘密。
- `scripts/phase-01d0-provider-bakeoff.py`、`scripts/verify-phase-1d0.sh`、
  `tests/test_stock_provider_boundary.py`：实测 harness、自动测试和配置检查。
- `docs/phase-reports/phase-01d0-provider-bakeoff.md` 与同目录 JSON 审计结果。

### 验收标准

- 配置固定且实际调用四股 `600519`、`000001`、`300750`、`688981`；
  quote 首次/后续延迟、四股批量覆盖、中文名、现价、昨收、状态、涨跌停、
  timestamp、1 分钟日期和异常均有机器可读证据。
- 六个候选路径均有实际结果或准确失败记录；Baidu direct 四股各 3 轮、每轮
  行数/首尾时间/日期一致性/延迟均有机器可读证据；安装版本、token、费用、Linux/
  Docker 可用性、上游、维护和 fallback 难度均有审计结论。
- `resolve_symbol`、`get_quotes`、`get_intraday` 三项 boundary 和
  adapter 内 canonical conversion 有自动测试；不实现完整 Gateway。
- `bash scripts/verify-phase-1d0.sh` 通过；报告明确默认/备用为条件性建议，
  并明确交易时段仍未验证。

### 本次修补验收结果

- Baidu direct 公开 endpoint 在主机网络完成固定四股各 3 轮 intraday；每股每轮
  240 条有成交分钟，首尾 09:30/15:00，观察日期均为 2026-08-14，日期一致。
- `bash scripts/verify-phase-1d0.sh`、带隔离 pycache 的 `py_compile` 和
  `git diff --check` 均通过；机器结果见
  [phase-01d0-provider-bakeoff-results.json](phase-reports/phase-01d0-provider-bakeoff-results.json)。
- Codex 主模型在目标 QNAP NAS（x86_64 Linux、Container Station 3.1.2、
  Docker 27.1.2-qnap8）用一次性 `python:3.11-slim` 容器复核：10/10 单测
  通过，`easyquotation==0.7.7` 安装成功，四股 Tencent quote 4/4，四股
  Baidu direct intraday 各 240 条且日期/首尾时间一致。
- 因此 1D.0 可标记为非交易时段 completed/accepted；下一交易时段实时更新、
  状态实际命中和完整 Gateway 的 NAS 部署/重启/长稳仍是明确未验证项。

### 风险与回滚点

- 实测结果显示候选之间 quote 与 intraday 能力不对称；easyquotation/Tencent
  quote 字段最完整，Baidu direct 可作为 intraday supplementary；其 timekline
  仍返回陈旧的 2021-10-08 数据，不能作为生产 intraday。
- 组合验收结论为 quote primary easyquotation/Tencent、intraday supplementary
  Baidu direct、quote fallback adata/Sina；本次四股未实际命中涨停/跌停或停牌，
  不猜测 `stockStatus`/`upDownStatus` 数字语义。
- AKShare/Eastmoney 请求收到 `RemoteDisconnected`；adata/Tencent 返回空，
  adata/Sina 缺 timestamp/涨跌停且 1 分钟接口返回 `None`。这些是本次真实
  网络/上游证据，不是伪造的成功。
- 当前回滚点为 commit `c2031a7` 加本任务开始前的用户文档 diff；回滚时只移除
  1D.0 新增文件和本阶段文档段落，保留 `AGENTS.md`、`HARDWARE_BASELINE.md`
  及用户已有的 `ARCHITECTURE.md`/`DECISIONS.md` 有效改动，不使用 reset。

## 当前基线（已验收）

- `firmware/product/`：独立 ESP-IDF v6.0.2 产品固件（唯一正式固件工程）。Phase 1B.1 已在真机验收 Boot、16 MB Flash、8 MB octal PSRAM、RLCD/LVGL、BOOT 按键与 Wi-Fi station。详见 [Phase 1B.1 报告](phase-reports/phase-01b1-clean-firmware-bootstrap.md)与[详细记录](PHASE1B1_CLEAN_FIRMWARE_BOOTSTRAP.md)。
- `firmware/xiaozhi/`：Xiaozhi v2.4.2 冻结硬件参考（annotated tag `phase-1b-xiaozhi-reference`），不是产品固件基底，默认不读取。
- Stock Gateway Phase 1D 已完成并在 NAS/非交易时段验收；下一交易时段实时推进
  作为明确补测项保留。Phase 1E 正在把已验收的 stock model/view 切换到
  Gateway 真实数据；Voice Gateway 尚未开始。

## Phase 1C 已验收结果

- `firmware/product/components/stock/` 已加入纯 C99 的
  model/mock、LVGL 2×2 view、约 10 秒刷新 service、字体子集和 host test；
  `scripts/verify-phase-1c.sh` 提供静态检查与 host test。
- 实际链路为 `deterministic mock → stock model → stock view → LVGL → RLCD`，
  不接入真实行情、Stock Gateway、Web 管理或任何凭据。
- 启动路径已按既定修复边界改为 task-owned：`app_main()` 只调用
  `stock_service_start()`；stock view 创建、mock reset 与首屏刷新都在具有
  明确栈预算（8192 字节）的 stock service task 内、于首次约 10 秒延迟之前
  完成，main task 不再创建/刷新股票 UI，main task 栈未增大。真机重新烧录
  后 `app_main()` 正常返回，完整 24-tick 循环无 stack overflow、panic 或
  reboot；Wi-Fi 回归通过，用户确认 4 股显示、约 10 秒刷新、闪烁/残影与
  2–3 米可读性可接受。证据见
  [Phase 1C 报告](phase-reports/phase-01c-stock-display-skeleton.md)。

## 最近完成

- [Phase 2A — Voice Hardware Bring-up](PHASE2A_REPORT.md)（2026-08-17 交付 `556acc3`；2026-08-18 用户确认验收，作为 realtime 方向开发基线）
- [Phase 1E — Live Stock Dashboard](phase-reports/phase-01e-live-stock-dashboard.md)（2026-08-16）
- [Phase 1D — Stock Gateway](phase-reports/phase-01d-stock-gateway.md)（2026-08-16）
- [Phase 1D.0 — A-share Provider Bake-off](phase-reports/phase-01d0-provider-bakeoff.md)（2026-08-15）
- [Phase 1C — Stock Display Skeleton](phase-reports/phase-01c-stock-display-skeleton.md)（2026-08-15）
- [Phase 1B.1 — Clean Firmware Bootstrap](phase-reports/phase-01b1-clean-firmware-bootstrap.md)（2026-08-15）
- [Phase 1B — First Xiaozhi Flash & Boot Verification](phase-reports/phase-01b-first-flash-boot.md)（2026-08-15）
- [Phase 1A — USB、设备身份与原厂备份](phase-reports/phase-01a-usb-identity-backup.md)（2026-08-15）
- [Phase 0A — 产品与 Upstream 基线](phase-reports/phase-00a-product-upstream-baseline.md)（2026-08-13）
- [Phase 0 — Agent 协作与交付基础设施](phase-reports/phase-00-agent-delivery-foundation.md)（2026-08-13）

## 下一步

1. 新 ADR：正式替代 ADR-0006 的「Mac 本地 ASR/LLM/TTS」路线；模型写
   `gpt-realtime-2.1`，传输写 `gateway-relay`，OpenClaw Gateway 在 Mac mini。
2. 下一阶段开题：ESP32 → Mac EVA Voice Bridge 接口设计（禁止清单仍有效：
   不自建 STT/TTS、不直连 OpenAI、不把 OpenClaw 协议下沉到 ESP32）。
3. 运维项（不进固件）：EVA 主模型 zai token 过期；headless OAuth 续期方案。
4. 旧遗留补测项保留：下一交易时段 Gateway quote/分钟实时推进；2A 遗留
   WAV 协议限速、AEC 模式对比等（见 PHASE2A_REPORT 已知问题节）。

## 重要风险与未验证

- Realtime 产品主链已验证（OAuth-only + gateway-relay + gpt-realtime-2.1 +
  agent-consult）。未验证：headless OAuth 续期、下行音频重采样到 16 kHz、
  浏览器外放自打断在 ESP32 AEC 下的消除（2A 硬件 AEC 是设计依据）。
  `gpt-live-1-codex` 已证实不可用于 platform realtime。
- 2A 遗留：串口 WAV 协议在 >16 kHz/更多通道时需重新限速评估；AEC 仅验
  证 VOIP_HIGH_PERF 模式；音量 0 对照实验 inconclusive（底噪主导，不用
  作证据）。详见 [PHASE2A_REPORT.md](PHASE2A_REPORT.md) 已知问题节。
- RLCD 中文字体、2–3 米可读性、信息密度与持续刷新/残影（1C 真机验证）。
- 电池、RTC、SHTC3、TF 卡未接入验证（不在 1/2A 范围）。
- 当前有界组合建议为 quote primary easyquotation/Tencent、intraday supplementary
  Baidu direct、quote fallback adata/Sina；这不是完整 Gateway routing。
- 2026-08-15 周六只验证了上一交易日（2026-08-14）分钟数据；尚未验证交易时段
  实时更新。easyquotation/Tencent timekline 实测返回 2021-10-08 陈旧数据，
  不能直接用于看板 sparkline。
- 本次四股没有实际命中 LIMIT_UP/LIMIT_DOWN 或 SUSPENDED；状态覆盖仍受真实样本
  限制，不得把 `stockStatus`/`upDownStatus` 数字猜成 canonical 状态。
- 完整 Gateway 已在 NAS Docker 验证 build、health、LAN Web/API、named volume、
  container restart 和进程崩溃恢复；NAS 全机重启、跨日长稳和交易时段实时推进
  尚未验证。
- 已验收历史能力默认不重新验证，除非当前改动可能引起回归。

## 必读 canonical 文档

- 产品需求：[PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)
- 当前架构：[ARCHITECTURE.md](ARCHITECTURE.md)
- 阶段顺序：[ROADMAP.md](ROADMAP.md)
- 当前有效决策：[DECISIONS.md](DECISIONS.md)
