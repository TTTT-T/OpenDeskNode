# ESP32-S3 RLCD 股票看板 + GPT 终端

目标是在 Waveshare ESP32-S3-RLCD-4.2 上构建可长期维护的 A 股桌面看板和 OpenAI 语音终端。正式产品使用独立 ESP-IDF 固件；Xiaozhi v2.4.2 仅作为已验收硬件参考，产品不依赖 Xiaozhi 官方服务器、账号或激活。

## 从这里开始

1. [当前状态](docs/PROJECT_STATE.md)
2. [产品需求](docs/PRODUCT_REQUIREMENTS.md)
3. [当前架构](docs/ARCHITECTURE.md)
4. [当前有效决策](docs/DECISIONS.md)
5. [路线图](docs/ROADMAP.md)

## 固件构建

```bash
bash scripts/setup-idf.sh
bash scripts/build-clean-firmware.sh
```

工具链只保存在项目的 `.tools/`；构建输出默认位于 `/private/tmp/esp32-s3-rlcd-4.2-clean-build/`。两者均不提交 Git。Xiaozhi reference 仍可通过 `scripts/build-firmware.sh` 独立构建。构建通过不代表显示、音频、Wi-Fi 或按键真机验收。
