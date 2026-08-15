#pragma once

#include "esp_err.h"

/*
 * Waveshare ESP32-S3-RLCD-4.2 hardware parameters.
 *
 * Provenance: firmware/xiaozhi/main/boards/waveshare/
 * esp32-s3-rlcd-4.2/config.h at the fixed v2.4.2 reference tag. Only
 * board-level pin assignments and display geometry are retained here.
 */
#define BOARD_BOOT_BUTTON_GPIO 0

#define BOARD_RLCD_DC_GPIO 5
#define BOARD_RLCD_CS_GPIO 40
#define BOARD_RLCD_SCK_GPIO 11
#define BOARD_RLCD_MOSI_GPIO 12
#define BOARD_RLCD_RST_GPIO 41
#define BOARD_RLCD_TE_GPIO 6

#define BOARD_RLCD_WIDTH 400
#define BOARD_RLCD_HEIGHT 300

typedef void (*board_button_callback_t)(void);

/** Configure and asynchronously debounce the active-low BOOT button. */
esp_err_t board_button_init(board_button_callback_t callback);
