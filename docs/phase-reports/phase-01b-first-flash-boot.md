# Phase 1B — First Xiaozhi Flash & Boot Verification

## 目标与结果

将固定的 Xiaozhi v2.4.2 `waveshare/esp32-s3-rlcd-4.2` 首次烧录到已验证的 ESP32-S3-RLCD-4.2，并完成 Boot、Memory、RLCD、BOOT 按键和 Wi-Fi 最小验收。本阶段通过，未验收音频质量、AEC、唤醒词、GPT、Stock 或自定义 UI。

## 镜像与烧录

- 固件：Xiaozhi v2.4.2，ESP-IDF v6.0.2，目标 `esp32s3`，板型配置 `CONFIG_BOARD_TYPE_WAVESHARE_ESP32_S3_RLCD_4_2=y`。
- 产物：`merged-binary.bin`，11,289,121 bytes，SHA-256 `9bf98a7762916ad0eb5d5463a0fe3f472bea74c19ff77952ff06e3184933cd19`。
- 格式证据：Xiaozhi 官方 `scripts/build.py` 调用 `idf.py merge-bin`，官方 builder 将该文件定义为 full flash image。镜像头为 ESP32-S3 / 16 MB / DIO / 80 MHz，checksum 和 validation hash 有效。
- 合并组成：`0x0` bootloader、`0x8000` partition table、`0xd000` OTA data、`0x20000` application、`0x800000` assets；各 offset 片段与原始构建文件 SHA-256 逐项一致。
- 实际命令：

  ```bash
  python -m esptool --chip esp32s3 --port /dev/cu.usbmodemXXXX --baud 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-freq 80m --flash-size 16MB 0x0 /private/tmp/esp32-s3-rlcd-4.2-build/merged-binary.bin
  ```

- 只从 `0x0` 写入单个 merged image；未使用 `--erase-all`、`--force` 或额外 Flash 操作。esptool 报告写入区间 `0x00000000–0x00ac4fff`，写后 hash 验证通过。

## 启动验收

- Boot：一次受控 reset，`SPI_FAST_FLASH_BOOT`；日志识别 Xiaozhi 2.4.2、ESP-IDF 6.0.2、chip revision v0.2 和 SKU `esp32-s3-rlcd-4.2`。观察窗内无 boot loop、panic、watchdog reset 或 allocation failure。
- Memory：检测 8 MB octal PSRAM @ 80 MHz 并加入 allocator；Flash 写前身份检查为 16 MB，镜像头和运行分区与 16 MB 布局一致。该短窗口不代替 Phase 1C 的资源峰值和长稳。
- RLCD：日志完成 SPI、LVGL 和 `RLCD init`；用户实际看到可读的“激活设备”、网址、验证码与“待命”画面，证明非全黑/全白且有效内容可显示。更细的方向标记、坐标、字体和残影仍属后续验收。
- Button：用户单击 BOOT 后，画面从激活提示切换为“待命”；日志对应 `activating -> idle`，与 v2.4.2 的 `HandleToggleChatEvent()` 逻辑一致。
- Wi-Fi：首启进入配网 AP，DNS/DHCP/Web 服务启动；完成用户配网后进入 station 模式、获得 IP 并报告 `Application: Network connected`。公开证据不记录 SSID、MAC、UUID、IP 或激活码。

## 云端激活限制

官方 v2.4.2 固件默认通过 HTTPS 访问 `api.tenclass.net/xiaozhi/ota/`，并引导用户在 `xiaozhi.me` 登录后使用六位码绑定设备。未绑定时固件会反复执行激活检查；BOOT 单击可暂时转入 idle，但不会永久取消后台激活轮询。

激活/版本检查会发送设备 MAC/UUID、板型/版本、芯片、Flash、分区和资源等系统元数据；代码中该请求不包含 Wi-Fi 密码。本阶段没有替用户登录或绑定，也不把“官方默认服务”视为已完成隐私/安全审计。后续语音集成前必须明确选择官方云或自托管 Xiaozhi Server；在该决策前不需要完成官方云绑定。

## 证据与剩余风险

- 原始 monitor 日志位于被 Git 忽略的 `.tools/phase-01/logs/phase-1b-first-boot-monitor.log`，包含网络/设备标识，权限必须保持 `0600`，不得提交或公开。
- 启动中有单次 `i2s_channel_disable`: channel not enabled yet，未导致 panic/reset；音频本就不属于 Phase 1B，留待 Phase 1C 用可重复音频路径判定。
- 未完成官方云账号绑定；这不阻塞 Phase 1B 硬件验收，但会阻塞依赖官方云的 AI 对话。

