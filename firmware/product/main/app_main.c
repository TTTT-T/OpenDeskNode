/*
 * Phase 1E product bootstrap coordinator.
 *
 * Orchestrates the accepted Phase 1B.1 hardware bootstrap (flash/PSRAM
 * report, RLCD/LVGL, BOOT button, Wi-Fi station) and the Phase 1C stock
 * live dashboard: the stock task reads the self-hosted LAN Gateway about every
 * 10 seconds and preserves its last valid snapshot across bounded failures.
 * No provider credential, cloud voice, OTA, or public endpoint is present.
 */
#include <stdbool.h>
#include <stddef.h>

#include "audio_selftest.h"
#include "board.h"
#include "display.h"
#include "esp_check.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "network.h"
#include "stock_service.h"

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

static void on_boot_button_pressed(board_button_event_t event)
{
    /* Phase 2A: single press re-runs the audio self-test, double press
     * toggles the speaker volume as audible button evidence. */
    if (event == BOARD_BUTTON_DOUBLE_PRESS) {
        audio_selftest_toggle_volume();
    } else {
        audio_selftest_request_rerun();
    }
    display_set_button_status(event == BOARD_BUTTON_DOUBLE_PRESS ? "2xPress" : "Pressed");
}

static void on_wifi_status_changed(network_status_t status)
{
    ESP_LOGI(TAG, "Wi-Fi status: %s", network_status_text(status));
    display_set_wifi_status(network_status_text(status));
}

void app_main(void)
{
    ESP_LOGI(TAG, "ESP32-S3 Dashboard clean firmware boot");
    const bool psram_ok = report_memory_baseline();

    ESP_ERROR_CHECK(display_init());
    display_set_psram_status(psram_ok ? "OK" : "Mismatch");

    /* The task owns its placeholder, HTTP/JSON conversion, last-good model,
     * and all LVGL stock updates; app_main never touches stock widgets. */
    ESP_ERROR_CHECK(stock_service_start());

    /* Phase 2A: audio hardware bring-up runs after the dashboard task is up;
     * BOOT re-triggers the audio self-test at any time. */
    ESP_ERROR_CHECK(audio_selftest_start());

    ESP_ERROR_CHECK(board_button_init(on_boot_button_pressed));
    ESP_ERROR_CHECK(network_init(on_wifi_status_changed));
}
