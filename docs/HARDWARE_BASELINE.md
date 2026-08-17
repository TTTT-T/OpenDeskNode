# Phase 1 Hardware Baseline

状态：Phase 1A 和 Phase 1B 已完成；Phase 1C 已完成并验收。本文是验收记录模板；未填写证据的条目一律视为未通过。

## 当前接入观察

- 用户报告：2026-08-15 已通过 Type-C 接入 Mac。
- 主机检查：2026-08-15 11:14 CST，`ioreg -p IOUSB` 未发现 Espressif/Waveshare 设备，`/dev` 未出现 `cu.usb*` 或 `tty.usb*`。
- 后续复查：Mac 已稳定枚举 Espressif `303a:1001` 和 `/dev/cu.usbmodemXXXX`；确认 ESP32-S3 revision v0.2、16 MB Flash、8 MB PSRAM、Secure Boot/Flash Encryption 未启用。
- Phase 1B：Xiaozhi v2.4.2 merged image 首次烧录和写后 hash 验证成功；启动、RLCD 可读内容、BOOT 单击和 Wi-Fi 首配/联网通过最小验收。详见 [Phase 1B 报告](phase-reports/phase-01b-first-flash-boot.md)。

## Phase 1A 写入前安全门槛

在任何 `write-flash`、`flash`、erase、分区或 OTA 写入之前，必须完成：

1. 记录串口、USB vendor/product、芯片型号、MAC（公开记录脱敏）、Flash ID/容量和安全启动/加密只读状态；
2. 读取完整 `0x1000000` bytes 原厂 Flash 两次，保存为两个不同文件；
3. 确认两份文件均为 16,777,216 bytes 且 SHA-256 完全一致；
4. 记录恢复命令和备份保存位置，备份不得提交 Git；
5. 复核待写入 merged binary 的来源、版本、大小、SHA-256 和 Flash 布局。

任一项缺失时保持只读，不烧录。Phase 1A 通过后再进入下方外围功能与稳定性验收。

## 测试身份

记录实物 SKU、PCB/revision、购买页面、供电方式、USB 线、18650 型号、固件 tag/SHA、ESP-IDF 版本、构建产物 SHA-256、串口名和测试日期。日志公开前删除 Wi-Fi 名称、MAC、UUID、设备 ID 和 Token。

## 验收矩阵

| 子系统 | 操作与证据 | 通过条件 |
| --- | --- | --- |
| Boot/System | 上电和软件重启各 3 次；保存 boot log、chip/flash/PSRAM、reset reason | 版本与硬件匹配；无异常 reset/boot loop |
| RLCD init | 冷启动显示测试页；照片 + 串口日志 | 无花屏/错位；初始化稳定 |
| Resolution/orientation | 显示四角标记、坐标轴和 `400×300` 文本 | 四角和方向与产品布局一致 |
| Chinese/LVGL | 显示中英数字、涨跌符号、不同字号和分隔线 | 必需字形完整，无裁切/乱码 |
| RLCD refresh | 价格区域 1/5/15 秒刷新；记录 SPI/flush 耗时和视频 | 无不可接受闪烁/阻塞；目标周期可持续 |
| Display soak | 静态 + 周期刷新至少 2 小时 | 无崩溃、明显残影累积或资源持续下降 |
| Wi-Fi provision | 清空配置后首配 | 可完成并有明确 UI/日志反馈 |
| Wi-Fi reconnect | 重启路由/断网/恢复各 3 次 | 状态可解释，自动恢复，不阻塞 UI |
| Microphones | 分别采集双麦/参考通道，保存短样本与通道统计 | 非静音、非复制假象、无持续削波 |
| Speaker/Codec | 播放固定测试音并记录 ES7210/ES8311/I2S 日志 | 音量可用，无明显爆音/卡顿 |
| AEC basic | 同一语句在 AEC off/on 下播放并录音 | 开启后回声有可观察改善且语音仍可懂；不要求极致指标 |
| Buttons | BOOT 单击/双击、KEY、PWR 按官方行为逐项测试 | 每个实际按键行为有记录；不凭代码推断 |
| Battery | USB、18650、充电、放电；记录 ADC mV/百分比/状态 | 电压合理、百分比不越界；充放电行为可解释 |
| RTC/SHTC3/TF | 读时钟、温湿度、FAT32 卡信息 | 数据合理，错误场景有日志；若不纳入 Phase 1 须明确延期 |
| Memory | boot、idle、display active、voice idle/active 采样 internal free/largest、PSRAM free/largest | 无分配失败；峰值后可恢复；保留安全余量 |
| Stability | Dashboard mock + Wi-Fi + 一轮语音持续至少 4 小时 | 无 crash/watchdog/持续泄漏；所有 reset 有解释 |

## 一次性需要用户配合的实体操作

硬件到货后一次准备：确认外观/SKU/PCB 标识，提供可靠数据线、合适扬声器、FAT32 TF 卡和正确极性的 18650；按测试脚本完成按键、断网、充放电和 AEC 对照。Agent 负责给出单次完整步骤、收集日志和判断，不要求用户重复无信息量操作。

## 证据保存

Phase 1 开始时在 `artifacts/phase-01/<date>/` 保存脱敏日志、测试配置、指标 CSV 和必要照片索引；大体积音视频默认不提交 Git，只在阶段报告记录位置、摘要和哈希。
