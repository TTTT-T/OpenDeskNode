/*
 * Phase 1B.1 product bootstrap coordinator.
 *
 * This file intentionally initializes only board input, RLCD/LVGL, memory
 * reporting, and Wi-Fi station support. It has no cloud, voice, stock, OTA,
 * or application-protocol responsibilities.
 */
#include <stdbool.h>
#include <stddef.h>

#include "board.h"
#include "display.h"
#include "esp_check.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "network.h"

static const char *TAG = "bootstrap";
static const size_t EXPECTED_FLASH_BYTES = 16U * 1024U * 1024U;
static const size_t EXPECTED_PSRAM_BYTES = 8U * 1024U * 1024U;

static bool report_memory_baseline(void)
{
    uint32_t flash_bytes = 0;
    ESP_ERROR_CHECK(esp_flash_get_size(NULL, &flash_bytes));
    const size_t psram_bytes = esp_psram_get_size();

    if (flash_bytes == EXPECTED_FLASH_BYTES) {
        ESP_LOGI(TAG, "Flash: %lu bytes (16 MB expected)", (unsigned long)flash_bytes);
    } else {
        ESP_LOGW(TAG, "Flash mismatch: detected %lu bytes, expected 16 MB",
                 (unsigned long)flash_bytes);
    }

    if (psram_bytes == EXPECTED_PSRAM_BYTES) {
        ESP_LOGI(TAG, "PSRAM: %lu bytes (8 MB expected)", (unsigned long)psram_bytes);
    } else {
        ESP_LOGW(TAG, "PSRAM mismatch: detected %lu bytes, expected 8 MB",
                 (unsigned long)psram_bytes);
    }

    return psram_bytes == EXPECTED_PSRAM_BYTES;
}

static void on_boot_button_pressed(void)
{
    ESP_LOGI(TAG, "BOOT button press captured");
    display_set_button_status("Pressed");
}

static void on_wifi_status_changed(network_status_t status)
{
    display_set_wifi_status(network_status_text(status));
}

void app_main(void)
{
    ESP_LOGI(TAG, "ESP32-S3 Dashboard clean firmware boot");
    const bool psram_ok = report_memory_baseline();

    ESP_ERROR_CHECK(display_init());
    display_set_psram_status(psram_ok ? "OK" : "Mismatch");
    ESP_ERROR_CHECK(board_button_init(on_boot_button_pressed));
    ESP_ERROR_CHECK(network_init(on_wifi_status_changed));
}
