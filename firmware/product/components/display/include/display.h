#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

/**
 * Full-frame ST7305 flush instrumentation. One LVGL flush callback equals one
 * full-frame SPI transfer under the current strategy.
 */
typedef struct {
    uint32_t flush_count;
    uint64_t flush_total_us;
    uint32_t flush_max_us;
} display_flush_metrics_t;

/** Initialize the ST7305 RLCD transport, LVGL port, and bootstrap page. */
esp_err_t display_init(void);

/** These functions take the LVGL port lock before changing visible state. */
void display_set_wifi_status(const char *status);
void display_set_button_status(const char *status);
void display_set_psram_status(const char *status);

/** Acquire/release the LVGL lock for callers building their own screens. */
bool display_lock(uint32_t timeout_ms);
void display_unlock(void);

/**
 * Atomically snapshot and zero the full-frame flush counters, so every count
 * is attributed to exactly one reporting interval (safe from any task).
 */
display_flush_metrics_t display_flush_metrics_take(void);
