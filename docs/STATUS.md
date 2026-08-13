# 当前阶段状态

最后更新：2026-08-13

本文件是阶段状态的唯一入口。新会话只需从这里定位当前 Phase 和最近相关报告，不应默认加载全部历史。

## 进行中 Phase

### Phase 0A — 产品与 Upstream 基线

- 单一目标：把已确认的 ESP32-S3-RLCD 股票看板与 GPT 终端产品移交转化为可复现的仓库、架构和上游构建基线。
- 非目标：不开发股票业务、产品 UI、股票后端或语音股票工具；不宣称任何真机能力通过。
- 预计范围：项目上下文、当前架构、ADR、路线图、上游基线记录、固件 upstream 引入、主机构建脚本和阶段报告。
- 验收标准：
  - 微雪官方资料、Waveshare 示例、`78/xiaozhi-esp32` 稳定 release、`xinnan-tech/xiaozhi-esp32-server` 稳定 tag 和 OpenAI 官方接口资料均有日期、URL、tag/SHA 或明确版本证据；
  - 固件 upstream 以固定 SHA 引入，能追溯版本且有明确更新/回滚流程；
  - 目标板在固定 upstream 中可被构建系统唯一识别，upstream 构建脚本测试通过；
  - 使用固定 ESP-IDF 版本执行目标板完整本机构建，产出 merged binary；若不可执行，必须记录准确阻塞证据且 Phase 0A 不标完成；
  - v1 架构、禁止边界、有效 ADR、完整 Phase 路线图及 Phase 1 真机验收清单彼此一致；
  - `git diff --check`、本地 Markdown 链接检查和敏感值扫描通过。
- 风险与依赖：首次 ESP-IDF 工具链和组件下载体积较大；upstream 最新稳定版本尚未经过本项目真机验证；硬件未到位。
- 回滚点：Phase 0 提交 `375b189`；upstream 引入保持独立提交，可单独回退。

## 最近完成

- [Phase 0 — Agent 协作与交付基础设施](phase-reports/phase-00-agent-delivery-foundation.md)（2026-08-13）

## 下一阶段候选

Phase 0A 验收后进入 Phase 1 — Hardware Baseline。硬件未到位前只保留验收计划，不提前实现 Phase 2 业务 UI。
