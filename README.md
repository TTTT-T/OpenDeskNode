# OpenDeskNode

**简体中文** | [English](README.en.md)

**OpenDeskNode 是一个面向桌面智能终端的开源平台，用于构建具备实时数据展示、语音交互和 AI 能力的常驻式智能显示设备。**

当前公开版本 **v0.1.0 — Stock Dashboard**，已经可以把 Waveshare ESP32-S3-RLCD-4.2 变成一台自托管的 A 股实时行情桌面终端：设备端负责低功耗黑白显示，局域网内的 Stock Gateway 负责行情获取、缓存、管理和接口服务。

Waveshare ESP32-S3-RLCD-4.2 只是 OpenDeskNode 当前第一个经过验证的参考硬件，并不是永久的平台限制。项目的目标是逐步支持更多显示开发板、MCU、边缘计算设备、本地外设与服务，而不是把 OpenDeskNode 限定成某一块 ESP32 开发板的专用固件。

## v0.1.0 已实现

- 4 只 A 股同时展示，包含中文名称、现价、涨跌额、涨跌幅、市场状态和分时走势。
- 设备端约每 10 秒轮询一次行情，并保留最后一次有效数据；网络或上游短暂异常时可继续展示，默认容忍约 5 分钟。
- 自托管 FastAPI + SQLite Stock Gateway，提供适合手机访问的自选股管理页面和版本化 JSON API。
- 行情数据源与设备端解耦：Provider 的凭据、格式和兼容逻辑都留在服务端，显示节点只访问配置好的 Gateway。
- 针对黑白/低功耗屏设计的 2×2 股票布局，已在参考 RLCD 硬件上验证。

## 架构

```text
显示节点 -- 局域网 HTTP / schema v1 --> Stock Gateway --> 行情数据源
   |                                      |
   +-- 本地 UI / 最后有效状态             +-- 自选股 / 缓存 / SQLite / Web UI
```

产品固件位于 `firmware/product/`，Stock Gateway 位于 `gateway/`。

`firmware/xiaozhi/` 是带有来源说明的冻结硬件参考代码，仅用于板级实现参考，并不是 OpenDeskNode 的运行依赖或构建依赖。

## 快速启动 Stock Gateway

要求：已安装 Docker，并支持 Docker Compose。

```bash
cp .env.example .env
# 将 STOCK_GATEWAY_PUBLIC_HOSTNAME 设置为设备能够访问的主机名或局域网 IP。
docker compose up -d --build
curl --fail http://127.0.0.1:8000/healthz
```

随后打开：

```text
http://<gateway-host>:8000/
```

即可管理 4 只自选股。

v0.1.0 的 Gateway 默认不提供身份认证，因此建议只部署在可信局域网内，不要直接暴露到公网。

## 构建参考固件

要求：macOS 或 Linux、Git，以及足够的磁盘空间用于 ESP-IDF v6.0.2。

```bash
bash scripts/setup-idf.sh
bash scripts/build-clean-firmware.sh
```

如果默认地址无法被设备访问，请在构建前通过 `idf.py menuconfig` 配置：

```text
OpenDeskNode > Stock Gateway URL
```

Wi-Fi 凭据在运行时配置，不应提交到仓库，也不应直接编译进固件。

构建脚本默认把生成文件写到仓库之外。编译成功并不等同于完成真机验收，显示、Wi-Fi、Flash 分区和稳定性仍应在真实设备上验证。

## 验证

```bash
bash scripts/verify-public-release.sh
bash scripts/verify-phase-1d.sh
bash scripts/verify-phase-1e.sh
```

部分验证脚本仍保留内部开发阶段名称，用于追溯开发历史；对外发布版本统一为：

**OpenDeskNode v0.1.0 — Stock Dashboard**

## 文档

- [架构说明](docs/ARCHITECTURE.md)
- [产品需求](docs/PRODUCT_REQUIREMENTS.md)
- [参考硬件基线](docs/HARDWARE_BASELINE.md)
- [Stock Gateway 部署说明](docs/NAS_STOCK_GATEWAY.md)

## 安全与敏感信息

- 不要提交 `.env`、数据库文件、日志、Wi-Fi 凭据、API Key 或行情 Provider Token。
- 当前 Gateway 没有身份认证，只应运行在可信局域网内。
- 默认行情 Provider 组合使用公开接口，不需要填写 `.env.example` 中预留的 API 凭据字段。

## 后续方向

OpenDeskNode 不会停留在股票看板。后续版本将逐步加入语音交互、AI 服务、本地模型/云端模型接入，以及更多硬件平台支持。

股票看板是第一个可用场景，也是 OpenDeskNode 的第一套参考实现。

## License

OpenDeskNode 自有代码和文档采用 [Apache License 2.0](LICENSE) 发布。

仓库中包含的参考代码、生成字体和外部依赖仍分别遵循其原有许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
