# ADR-0001：Xiaozhi 固件采用固定 release 的 Git subtree

- 状态：Superseded by [ADR-0004](0004-clean-product-firmware.md)
- 日期：2026-08-13
- 决策者：项目用户与 Codex

> 历史保留：Git subtree 与 v2.4.2 已验收代码继续作为硬件参考，但不再作为正式产品固件基底。

## 背景

产品需要复用 Xiaozhi 的板级、网络、音频、协议、OTA、MCP 和 Application，同时保持可审查的 upstream 关系。根仓库已经存在治理历史，不能简单替换为 upstream 仓库；目标产品又会需要与固件同仓构建的小范围集成。

## 候选方案

- 直接复制/vendor：简单，但来源和升级关系弱。
- Git submodule：版本清晰，但产品与固件跨仓修改、构建和审查成本较高。
- Git subtree：保留固定来源与可重复 pull，产品仓可原子提交集成变更，代价是仓库包含 upstream 文件。
- 立即建立 GitHub fork：适合长期修改 upstream 核心，但当前尚无托管目标和实际 patch，不应先扩张外部流程。
- 只保存 patch layer：侵入最小，但在尚未知道实际 hook 数量前会增加应用/冲突机制。

## 决定

把 `78/xiaozhi-esp32` 的稳定 release 以 squash subtree 固定在 `firmware/xiaozhi`，远端名为 `xiaozhi-upstream`。不追踪 `main`。产品代码优先放在独立产品组件/UI/协调层；对 upstream 文件的必要 hook 必须保持最小并有测试。

## 后果

- 固件基线和产品集成可在一个提交中构建与回滚。
- upstream 更新必须通过显式 `git subtree pull --squash`，会产生可审查 merge，不会自动漂移。
- 仓库体积比 submodule 大；upstream 冲突需要人工审查。
- 不因为 subtree 就允许把业务写进 Board/驱动。

## 重评条件

连续两个 Phase 都需要修改 upstream 核心、难以向上游贡献补丁、subtree 冲突显著增加，或需要对外发布独立固件分支时，评估建立正式 fork；如变更策略，创建替代 ADR。
