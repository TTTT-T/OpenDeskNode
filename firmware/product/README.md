# OpenDeskNode reference firmware

This directory contains the ESP-IDF firmware used by OpenDeskNode v0.1.0 on
the Waveshare ESP32-S3-RLCD-4.2 reference hardware.

It provides:

- ESP32-S3 N16R8 configuration and a no-OTA 16 MB partition table;
- Waveshare board pins, BOOT input, ST7305 RLCD transport, and LVGL UI;
- Wi-Fi station networking with runtime provisioning;
- the four-stock dashboard, Gateway HTTP/schema client, last-good state, and
  host-side model/parser tests.

Build from the repository root:

```bash
bash scripts/setup-idf.sh
bash scripts/build-clean-firmware.sh
```

Use `idf.py menuconfig` and set `OpenDeskNode > Stock Gateway URL` to a host
name or LAN IP reachable by the device. Do not embed credentials in that URL.
Wi-Fi credentials are provisioned at runtime and stored in device NVS.

The adjacent `../xiaozhi/` tree is a frozen, attributed hardware reference. It
is not required to build or run this firmware.

## Hardware-source provenance

The pin assignments, ST7305 command sequence, and landscape 1-bit pixel
mapping were adapted from board-specific files in the frozen Xiaozhi reference:

- `firmware/xiaozhi/main/boards/waveshare/esp32-s3-rlcd-4.2/config.h`
- `firmware/xiaozhi/main/boards/waveshare/esp32-s3-rlcd-4.2/custom_lcd_display.cc`

Only hardware-level facts were reused. OpenDeskNode does not include the
reference application's runtime classes, activation flow, OTA flow, cloud
endpoints, or application protocols.
