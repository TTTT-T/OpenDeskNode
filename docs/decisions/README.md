# 架构决策记录

本目录只保存对未来有长期影响的技术决策。

## 决策索引

| ID | 标题 | 状态 | 日期 | 影响范围 | 替代关系 |
| --- | --- | --- | --- | --- | --- |
| [0001](0001-xiaozhi-upstream-integration.md) | Xiaozhi 固件采用固定 release 的 Git subtree | Superseded | 2026-08-13 | 固件来源与升级 | 0004 |
| [0002](0002-product-and-stock-boundaries.md) | 产品层与统一 Stock Service 边界 | Accepted | 2026-08-13 | 固件、后端、数据一致性 | 固件基底前提由 0004 替代，Stock 边界保留 |
| [0003](0003-v1-voice-pipeline.md) | v1 采用 Xiaozhi ASR → GPT → TTS | Superseded | 2026-08-13 | 语音与 OpenAI 集成 | 0004 |
| [0004](0004-clean-product-firmware.md) | Xiaozhi 冻结为 reference，产品采用独立 ESP-IDF 固件 | Accepted | 2026-08-15 | 固件、语音、云边界 | 替代 0001 产品基底与 0003 |

有效状态包括：`Proposed`、`Accepted`、`Superseded`、`Deprecated`、`Rejected`。实现时只把 `Accepted` 且未被替代的记录视为约束。

## 何时创建 ADR

需要记录的典型决策包括核心框架、通信协议、数据模型、模块边界、状态管理、持久化、核心依赖和硬件接口策略。满足以下条件时创建：存在真实候选方案，选择会跨多个 Phase 影响实现或未来撤销成本较高，并且理由仅靠当前代码无法恢复。

普通文件布局、函数拆分、命名、局部错误处理、测试组织、小范围重构和可轻易撤销的实现细节不创建 ADR。

## 记录格式

需要时新建 `NNNN-short-title.md`，并在上方索引增加一行。每份记录保持最小但完整，包含：

1. 标题、日期、状态和决策者；
2. 背景与需要解决的问题；
3. 已确认事实和约束；
4. 候选方案；
5. 当前决定及选择理由；
6. 放弃其他方案的原因；
7. 代价、风险和后果；
8. 重新评估的触发条件；
9. 对架构、代码、测试和迁移的影响。

## 变更规则

- ADR 记录决策历史，不通过重写旧结论伪造历史。
- 决策尚未执行时可保持 `Proposed`；只有决定已被接受后才标为 `Accepted`。
- 新决定推翻旧决定时，创建新 ADR，并把旧记录标为 `Superseded`、建立双向链接。
- ADR 生效或失效时，同一提交更新 `docs/ARCHITECTURE.md` 和必要的 Phase 验收项。
- 如果实现会违反有效 ADR，必须先停止并使用架构咨询流程，不能静默绕过。
