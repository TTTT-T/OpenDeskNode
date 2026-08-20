# 文档清单与唯一真相层级

最后核验：2026-08-20

本文件是仓库文档的 **inventory + canonical owner** 入口。它不替代任何
canonical 文档的内容；只回答「这个概念该读哪一份」。

`firmware/xiaozhi/**` 的 Markdown 属于冻结参考工程，不纳入本清单。

## 唯一真相层级

```text
PROJECT_STATE.md          当前 Phase / 基线 / 未验证项
    ↓
ROADMAP.md                Phase 顺序与状态
    ↓
PRODUCT_REQUIREMENTS.md   已确认产品行为
    ↓
ARCHITECTURE.md           当前唯一有效系统架构
    ↓
DECISIONS.md / ADR        为什么采用这个架构
    ↓
PHASE*.md                 当时计划做什么（完成后不再是架构事实源）
    ↓
phase-reports/*           实际发生了什么（永久保留）
    ↓
archive/*                 被替代的历史背景（默认不加载）
```

规则：**一个概念只有一个 canonical owner。** 其他文档只链接，不复制一份会漂移的定义。

## A. Canonical（当前有效定义）

| 文件 | Owner | 不负责 |
| --- | --- | --- |
| [PROJECT_STATE.md](PROJECT_STATE.md) | 当前 Phase、已验收基线、最近完成、未验证项 | 历史阶段细节、架构讨论 |
| [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) | 已确认产品行为 | 实现拓扑、阶段计划 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 当前系统是什么 | 决策理由、实验过程 |
| [ROADMAP.md](ROADMAP.md) | Phase 顺序与状态 | 当前细节（以 PROJECT_STATE 为准） |
| [DECISIONS.md](DECISIONS.md) | 当前有效长期决策汇总 | ADR 全文 |
| [decisions/](decisions/README.md) | ADR 历史与变更规则 | 当前状态入口 |
| [HARDWARE_BASELINE.md](HARDWARE_BASELINE.md) | 硬件验收矩阵与未验项 | 产品路线 |
| [UPSTREAM_BASELINE.md](UPSTREAM_BASELINE.md) | 工具链 / upstream 版本 | 产品行为 |
| [DELIVERY_WORKFLOW.md](DELIVERY_WORKFLOW.md) | Phase / 验收 / 咨询流程；`IMPLEMENTED` / `AUTO-VERIFIED` / `HW-ACCEPTANCE-PENDING` / `ACCEPTED` | 具体阶段内容；Pending 队列以 PROJECT_STATE 为准 |
| [NAS_STOCK_GATEWAY.md](NAS_STOCK_GATEWAY.md) | Stock Gateway NAS 部署与运维记录 | 语音架构 |
| [AGENTS.md](../AGENTS.md) | Agent 工作约定 | 项目事实 |
| [README.md](../README.md) | 仓库入口 | 架构全文 |

## B. Current Phase Definition

| 文件 | 说明 |
| --- | --- |
| [PHASE2C_EVA_VOICE_BRIDGE.md](PHASE2C_EVA_VOICE_BRIDGE.md) | Phase 2C 开题：目标、非目标、验收、未知项 |
| [VOICE_BRIDGE_PROTOCOL.md](VOICE_BRIDGE_PROTOCOL.md) | ESP32 ↔ Bridge 工作协议草案（2C 冻结对象；C0–C3 ACCEPTED，C4/C5 AUTO-VERIFIED / HW-ACCEPTANCE-PENDING） |

## C. Phase Report（永久保留）

短报告在 `phase-reports/`。2A/2B 的详细证据仍留在 `docs/` 根目录，短报告只做入口。

| 短报告 | 详细证据 |
| --- | --- |
| [phase-00-agent-delivery-foundation.md](phase-reports/phase-00-agent-delivery-foundation.md) | — |
| [phase-00a-product-upstream-baseline.md](phase-reports/phase-00a-product-upstream-baseline.md) | — |
| [phase-01a-usb-identity-backup.md](phase-reports/phase-01a-usb-identity-backup.md) | — |
| [phase-01b-first-flash-boot.md](phase-reports/phase-01b-first-flash-boot.md) | — |
| [phase-01b1-clean-firmware-bootstrap.md](phase-reports/phase-01b1-clean-firmware-bootstrap.md) | [PHASE1B1_CLEAN_FIRMWARE_BOOTSTRAP.md](PHASE1B1_CLEAN_FIRMWARE_BOOTSTRAP.md) |
| [phase-01c-stock-display-skeleton.md](phase-reports/phase-01c-stock-display-skeleton.md) | [PHASE1C_STOCK_DISPLAY_SKELETON.md](PHASE1C_STOCK_DISPLAY_SKELETON.md) |
| [phase-01d0-provider-bakeoff.md](phase-reports/phase-01d0-provider-bakeoff.md) | 同目录 JSON |
| [phase-01d-stock-gateway.md](phase-reports/phase-01d-stock-gateway.md) | [PHASE1D_STOCK_GATEWAY.md](PHASE1D_STOCK_GATEWAY.md) |
| [phase-01e-live-stock-dashboard.md](phase-reports/phase-01e-live-stock-dashboard.md) | [PHASE1E_LIVE_STOCK_DASHBOARD.md](PHASE1E_LIVE_STOCK_DASHBOARD.md) |
| [phase-02a-voice-hardware-bringup.md](phase-reports/phase-02a-voice-hardware-bringup.md) | [PHASE2A_REPORT.md](PHASE2A_REPORT.md) |
| [phase-02b-realtime-validation.md](phase-reports/phase-02b-realtime-validation.md) | [PHASE2B_REALTIME_VALIDATION_REPORT.md](PHASE2B_REALTIME_VALIDATION_REPORT.md) |
| [phase-02c-c1-live-acceptance.md](phase-reports/phase-02c-c1-live-acceptance.md) | — |
| [phase-02c-c2-live-acceptance.md](phase-reports/phase-02c-c2-live-acceptance.md) | — |
| [phase-02c-c3-live-acceptance.md](phase-reports/phase-02c-c3-live-acceptance.md) | — |

## D. Historical Phase Definition（当时计划，不是当前架构源）

完成后不得继续当作当前架构事实。正文中的旧图（如 NAS OpenClaw、`gpt-live-1-codex`）是开题快照。

| 文件 | 阶段 |
| --- | --- |
| [PHASE1B1_CLEAN_FIRMWARE_BOOTSTRAP.md](PHASE1B1_CLEAN_FIRMWARE_BOOTSTRAP.md) | 1B.1 规划 + 详细记录 |
| [PHASE1C_STOCK_DISPLAY_SKELETON.md](PHASE1C_STOCK_DISPLAY_SKELETON.md) | 1C 规划 |
| [PHASE1D_STOCK_GATEWAY.md](PHASE1D_STOCK_GATEWAY.md) | 1D 规划 |
| [PHASE1E_LIVE_STOCK_DASHBOARD.md](PHASE1E_LIVE_STOCK_DASHBOARD.md) | 1E 规划 |
| [PHASE2A_VOICE_HARDWARE_BRINGUP.md](PHASE2A_VOICE_HARDWARE_BRINGUP.md) | 2A 规划 |
| [PHASE2B_GPT_LIVE_REALTIME_VALIDATION.md](PHASE2B_GPT_LIVE_REALTIME_VALIDATION.md) | 2B 开题计划（含已被实测修正的假设） |

## E. Historical / Superseded on this branch

| 文件 | 状态 |
| --- | --- |
| [archive/PROJECT_CONTEXT.md](archive/PROJECT_CONTEXT.md) | 已拆入 PRODUCT_REQUIREMENTS / PROJECT_STATE |
| [decisions/0001-xiaozhi-upstream-integration.md](decisions/0001-xiaozhi-upstream-integration.md) | Superseded by ADR-0004 |
| [decisions/0003-v1-voice-pipeline.md](decisions/0003-v1-voice-pipeline.md) | Superseded by ADR-0004 |

## F. Other-branch historical（保留，不合并，不删除）

这些文件只存在于实验分支，**不是本主线的 canonical 文档**。

| 分支 | 文件 | 原职责 | 本主线处理 |
| --- | --- | --- | --- |
| `dev` `phase-2b-r` `phase-2b-voice-subsystem` | `docs/decisions/0005-opendesknode-product-positioning.md` | 股票是核心、语音可选 | 约束仍有效，已写入 PRODUCT_REQUIREMENTS / ARCHITECTURE；本分支 ADR-0005 编号已被 realtime 决策占用 |
| `dev` `phase-2b-r` `phase-2b-voice-subsystem` | `docs/decisions/0006-unified-gateway-and-mac-ai-node.md` | NAS 统一 Gateway + Mac 本地 ASR/LLM/TTS Compute Node | **Superseded** by 本分支 [ADR-0006](decisions/0006-eva-voice-bridge-thin-adapter.md) |
| `phase-2b-r` | `docs/decisions/0007-eva-openclaw-agent-runtime-voice-edge.md` | Voice Edge + NAS Adapter；路径 A/B 未测 | 产品路径 **Superseded**；设备侧 conversation/turn 语义可参考 |
| `dev` `phase-2b-r` `phase-2b-voice-subsystem` | `docs/VOICE_PROTOCOL.md` | v1/v2 设备协议 | 参考，不照搬、不 merge |
| `phase-2b-voice-subsystem` | `docs/PHASE2B_REPORT.md` `docs/PHASE2B_VOICE_SUBSYSTEM.md` | 旧 2B（Mock Gateway） | 旧实验报告 |
| `dev` | `docs/phase-reports/phase-02b-voice-subsystem.md` | 旧 2B 短报告 | 旧实验 |
| `phase-2b-r` | `docs/phase-reports/phase-02b-r-voice-edge-refactor.md` | 2B-R 短报告 | 旧实验 |

## G. Duplicate / Redundant（本次不删除）

| 模式 | 处理 |
| --- | --- |
| `PHASE*.md` 与 `phase-reports/phase-0x-*.md` | 规划 vs 结果，职责不同；保留并加状态横幅 |
| `PHASE2A_REPORT.md` / `PHASE2B_REALTIME_VALIDATION_REPORT.md` 在 `docs/` 根目录 | 详细证据保留原位；`phase-reports/` 只放短入口 |
| `NAS_STOCK_GATEWAY.md` 与 ARCHITECTURE 中的 Stock 段 | 前者是部署记录，后者是架构；不合并 |
| 本分支 ADR-0005 与他分支 ADR-0005 同号不同文 | **不改号**；本索引记录碰撞，禁止把实验分支 ADR 直接 checkout 进来 |

本次 **没有删除任何文件**。过期内容优先 canonicalize → 更新引用 → 标记 superseded。

## 已关闭的文档冲突

| 冲突 | 决议 |
| --- | --- |
| OpenClaw Gateway 在 NAS vs Mac mini | **当前事实：Mac mini**（loopback `:18789`）。迁回 NAS 只是 Future / unvalidated |
| 正式 realtime 模型 `gpt-live-1-codex` vs `gpt-realtime-2.1` | **`gpt-realtime-2.1`**。前者不可用于 platform realtime |
| 产品主链 STT→OpenClaw→TTS vs Realtime | **Realtime + agent-consult**。旧 STT/TTS 主链退出 current architecture |
| 统一 NAS Gateway vs Stock/Voice 分离 | **继续分离**。Stock Gateway ≠ OpenClaw Gateway ≠ EVA Voice Bridge |
| Phase 2B 进行中 vs 已验证 | **Completed / Accepted for architecture progression**。R0 FAIL 不阻塞 |
| PHASE2A 定义仍写「等待用户验收」 | 用户已于 2026-08-18 验收；定义文件改为历史规划 |
