# Clean product firmware

This is the formal ESP-IDF product firmware for the ESP32-S3-RLCD-4.2. It is
separate from `../xiaozhi/`, which remains an immutable Phase 1B hardware
reference. The product has no runtime or build-time dependency on that tree.

Phase 1B.1 contains only:

- ESP32-S3 N16R8 configuration and a no-OTA 16 MB partition table;
- Waveshare RLCD board pins and BOOT input;
- ST7305 RLCD transport, LVGL 9.5.x, and a minimal black-and-white page;
- NVS/event-loop initialization and an ESP-IDF Wi-Fi station client.

It intentionally excludes audio, voice, stock data, OTA, cloud activation,
and all application protocols.

Build with `bash scripts/build-clean-firmware.sh` from the repository root.
Wi-Fi credentials are never compiled into the image. On the Phase 1B migration
boot, the network component can import the first credential already stored in
the frozen reference's `wifi` NVS namespace. On a fresh device it enters the
official ESP-IDF SmartConfig (ESPTouch/AirKiss) runtime provisioning path and
stores the resulting station configuration in device NVS.

## Hardware-source provenance

The pin assignments, ST7305 command sequence, and landscape 1-bit pixel
mapping were adapted from the board-specific files at the fixed
`phase-1b-xiaozhi-reference` tag:

- `firmware/xiaozhi/main/boards/waveshare/esp32-s3-rlcd-4.2/config.h`
- `firmware/xiaozhi/main/boards/waveshare/esp32-s3-rlcd-4.2/custom_lcd_display.cc`

Only those hardware-level facts were reused. The code in this directory is a
new ESP-IDF implementation and does not include the reference application's
classes, assets, cloud endpoints, activation flow, OTA flow, or protocols.
