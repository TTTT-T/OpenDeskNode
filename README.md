# ESP32-S3 RLCD 股票看板 + GPT 终端

目标是在 Waveshare ESP32-S3-RLCD-4.2 上构建可长期维护的 A 股桌面看板和 OpenAI GPT 语音终端。项目当前尚未开发业务功能；固件 upstream 与可复现主机构建基线已经建立，真机基线等待硬件到货。

## 从这里开始

1. [项目上下文](docs/PROJECT_CONTEXT.md)
2. [当前架构](docs/ARCHITECTURE.md)
3. [架构决策](docs/decisions/README.md)
4. [当前阶段](docs/STATUS.md)
5. [路线图](docs/ROADMAP.md)

## 固件构建

```bash
bash scripts/setup-idf.sh
bash scripts/build-firmware.sh
```

工具链只保存在项目的 `.tools/`；为规避 ESP-IDF/GCC 对当前中文仓库路径的兼容问题，构建输出默认位于 `/private/tmp/esp32-s3-rlcd-4.2-build/`。两者均不提交 Git。固定版本、已知 workaround 与升级方法见 [Upstream Baseline](docs/UPSTREAM_BASELINE.md)。硬件到位前，构建通过不代表显示、音频、AEC、Wi-Fi、按键或电池通过。
