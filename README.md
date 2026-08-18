# OpenDeskNode

Waveshare ESP32-S3-RLCD-4.2 上的 A 股桌面看板；语音是附加能力，经 Mac 上
EVA Voice Bridge → OpenClaw Talk → EVA 接入。正式产品使用独立 ESP-IDF 固件；
Xiaozhi v2.4.2 仅作已验收硬件参考，产品不依赖 Xiaozhi 官方服务器、账号或激活。

## 从这里开始

1. [当前状态](docs/PROJECT_STATE.md)
2. [文档清单](docs/DOCUMENT_INDEX.md)
3. [产品需求](docs/PRODUCT_REQUIREMENTS.md)
4. [当前架构](docs/ARCHITECTURE.md)
5. [当前有效决策](docs/DECISIONS.md)
6. [路线图](docs/ROADMAP.md)

## 固件构建

```bash
bash scripts/setup-idf.sh
bash scripts/build-clean-firmware.sh
```

工具链只保存在项目的 `.tools/`；构建输出默认位于
`/private/tmp/esp32-s3-rlcd-4.2-clean-build/`。两者均不提交 Git。Xiaozhi
reference 仍可通过 `scripts/build-firmware.sh` 独立构建。构建通过不代表
显示、音频、Wi-Fi 或按键真机验收。

## Phase 1D Stock Gateway

Gateway 的 Docker/SQLite/FastAPI 实现位于 `gateway/`；离线验证入口是
`bash scripts/verify-phase-1d.sh`；TerrenceNAS 部署见
[NAS 部署记录](docs/NAS_STOCK_GATEWAY.md)。真实 Provider smoke 是独立命令。
下一交易时段实时推进仍需按报告补测。
