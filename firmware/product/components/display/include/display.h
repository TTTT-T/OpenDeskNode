#pragma once

#include "esp_err.h"

/** Initialize the ST7305 RLCD transport, LVGL port, and bootstrap page. */
esp_err_t display_init(void);

/** These functions take the LVGL port lock before changing visible state. */
void display_set_wifi_status(const char *status);
void display_set_button_status(const char *status);
void display_set_psram_status(const char *status);
