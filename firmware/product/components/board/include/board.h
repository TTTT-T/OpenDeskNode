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

/*
 * Audio bus parameters for ES7210 (ADC) and ES8311 (DAC) on I2C0 and the
 * shared full-duplex I2S0 bus. Same provenance as the display block above.
 * ES7210 outputs TDM with slot order MIC1, MIC3, MIC2, MIC4.
 */
#define BOARD_I2C_PORT            0
#define BOARD_I2C_SDA_GPIO        13
#define BOARD_I2C_SCL_GPIO        14
#define BOARD_I2C_FREQ_HZ         100000

#define BOARD_I2S_MCLK_GPIO       16
#define BOARD_I2S_WS_GPIO         45
#define BOARD_I2S_BCLK_GPIO       9
#define BOARD_I2S_DOUT_GPIO       8
#define BOARD_I2S_DIN_GPIO        10

#define BOARD_AUDIO_PA_GPIO       46

typedef enum {
    BOARD_BUTTON_PRESS = 0,
    BOARD_BUTTON_DOUBLE_PRESS,
} board_button_event_t;

typedef void (*board_button_callback_t)(board_button_event_t event);

/** Configure and asynchronously debounce the active-low BOOT button. */
esp_err_t board_button_init(board_button_callback_t callback);
