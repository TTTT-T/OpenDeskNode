# Upstream Baseline

核验日期：2026-08-13

## 固定版本

| 组件 | 用途 | 固定版本 / SHA | 状态 |
| --- | --- | --- | --- |
| `78/xiaozhi-esp32` | 固件基础设施 | `v2.4.2` / `e8d8a4010788afd60f0c8aa3b2e3d0a7bb8f02e5` | 已以 subtree 导入 `firmware/xiaozhi` |
| ESP-IDF | 固件工具链 | `v6.0.2` / `7101770dc6db2667b3c477cc31365dd1acd6db4e` | 项目本地安装，不提交 |
| `waveshareteam/ESP32-S3-RLCD-4.2` | 官方硬件示例参考 | `main` / `eb1f63427d735a22b9c30e22fa63ebddae1834d3` | 只读参考，不作为产品代码依赖 |
| `xinnan-tech/xiaozhi-esp32-server` | v1 后端候选 | `v0.9.6` / `f5ed1aaec88471ba00ac778045331514066d63dc` | 已核验，Phase 6 前不导入 |

核验时固件 `main` 为 `631add2a327ea2d49fec16e4d4534b8345bb40c1`，服务端 `main` 为 `545979873b6fe6ab52c86122fe6a0aef621b39ee`。这些只用于说明漂移，不是构建输入。

## 为什么选择固件 v2.4.2

- 是核验日最新稳定 release，而非易变 `main`。
- 目标板已从 v2.2.4 进入正式 release；v2.4.2 仍含唯一板型、`SetupUI()`、LVGL/ST7305、ES7210/ES8311、设备 AEC 和电池实现。
- v2.4.2 的 upstream CI 使用 `espressif/idf:v6.0.2`；其 manifest 最低要求 IDF 5.5.2，但 README 推荐 6.0.2。项目固定 CI 同版本 6.0.2，避免使用“任意 ≥5.5.2”。

## 已验证与纠正

- 微雪硬件描述基本准确，但实物 revision/GPIO 仍须 Phase 1 复核。
- 当前软件横向逻辑尺寸是 `400×300`，不是未经方向说明的 `300×400`；真机方向仍未验收。
- RLCD flush 确实在更新 dirty area 后发送整个 framebuffer；不把 partial render 误称为 panel partial transfer。
- 两个 LUT 与 LVGL buffer 的 PSRAM 占用明显大于仅 15 KB framebuffer；Phase 1 必须量测总内存，而不能只引用 framebuffer 大小。
- Xiaozhi Server v0.9.6 的 OpenAI-compatible LLM 适配器仍走 Chat Completions；OpenAI 官方当前推荐 Responses API 用于新建的 reasoning/tool workflows。v1 复用并不等于永久锁定该接口。
- Tushare 当前确有 `rt_min` / `rt_min_daily`，但实时分钟需要单独权限；历史分钟还有非商业用途限制。AKShare 当前接口大量封装第三方网页。两者都不是未经验证的正式数据源承诺。

## 本机构建证据

2026-08-13 使用项目脚本和固定 ESP-IDF v6.0.2 完成目标板全量构建：

- 命令：`bash scripts/build-firmware.sh`
- 板型：`waveshare/esp32-s3-rlcd-4.2`
- 配置：`CONFIG_BOARD_TYPE_WAVESHARE_ESP32_S3_RLCD_4_2=y`、`CONFIG_USE_DEVICE_AEC=y`
- 编译任务：2207/2207；应用 `xiaozhi.bin` 为 `0x2c9740`，最小 app 分区剩余 29%
- 合并固件：`/private/tmp/esp32-s3-rlcd-4.2-build/merged-binary.bin`
- 大小：11,289,121 bytes
- SHA-256：`9bf98a7762916ad0eb5d5463a0fe3f472bea74c19ff77952ff06e3184933cd19`
- 上游脚本测试：62/62 通过

已确认 workaround：ESP-IDF v6.0.2 的 GCC response file 在当前含中文的仓库路径下把 `picolibc.specs` 路径错误换行。`scripts/build-firmware.sh` 通过 `idf.py -B` 把构建输出定向到纯 ASCII 的 `/private/tmp` 子目录；源码仍从仓库读取，未修改 upstream。移除条件是后续工具链能在相同非 ASCII 路径下完整构建。Codex 沙箱内的组件管理器还会因 `sysctl()` 权限受限而失败，因此完整构建须在正常主机 shell 或获准的主机级执行中运行。

## Subtree 操作

远端名称固定为 `xiaozhi-upstream`：

```bash
git remote get-url xiaozhi-upstream
git fetch xiaozhi-upstream tag v2.4.2 --no-tags
git subtree pull --prefix firmware/xiaozhi xiaozhi-upstream <new-tag> --squash
```

升级必须在独立 Phase 中执行：先记录旧/新 SHA 和 changelog，检查目标板及我们触及的上游文件，构建，再真机回归。不得在有未提交产品修改时 pull，不得自动跟踪 `main`。

回滚优先 revert 对应 subtree merge/升级提交；不使用 `reset --hard` 覆盖用户工作。若产品对 upstream 核心 patch 持续增多或需要向上游提交，按 ADR-0001 的重评条件迁移到正式 fork。
