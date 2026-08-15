/*
 * Stock refresh service (Phase 1C): the service task owns startup — it
 * creates the LVGL stock view, resets the deterministic mock, and
 * synchronously renders the first view inside its explicit stack budget —
 * then one mock tick -> view update -> compact metrics log line per ~10
 * second cycle. Metrics intentionally exclude per-frame logging.
 */
#include "stock_service.h"

#include <inttypes.h>
#include <stdint.h>

#include "display.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "stock_mock.h"
#include "stock_view.h"

static const char *TAG = "stock-1c";
static const uint32_t STOCK_SERVICE_PERIOD_MS = STOCK_MOCK_TICK_INTERVAL_MS;
static const size_t STOCK_SERVICE_STACK_BYTES = 8192;
static TaskHandle_t s_service_task;

static void log_update_metrics(uint16_t tick, int64_t view_us,
                               const display_flush_metrics_t *flush)
{
    const size_t internal_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    const size_t internal_largest = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
    const size_t psram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    const uint32_t flush_avg_us = flush->flush_count == 0
                                      ? 0
                                      : (uint32_t)(flush->flush_total_us / flush->flush_count);

    ESP_LOGI(TAG,
             "tick=%u view_us=%lld flush_count=%lu flush_avg_us=%lu flush_max_us=%lu "
             "heap_internal=%u heap_internal_largest=%u psram_free=%u",
             (unsigned)tick, (long long)view_us, (unsigned long)flush->flush_count,
             (unsigned long)flush_avg_us, (unsigned long)flush->flush_max_us,
             (unsigned)internal_free, (unsigned)internal_largest, (unsigned)psram_free);
}

static void run_update_cycle(void)
{
    const uint16_t tick = stock_mock_tick_index();
    const int64_t started_us = esp_timer_get_time();
    stock_view_update(stock_mock_snapshot());
    const int64_t view_us = esp_timer_get_time() - started_us;

    const display_flush_metrics_t flush = display_flush_metrics_take();
    log_update_metrics(tick, view_us, &flush);
}

static void stock_service_task(void *arg)
{
    /* Startup runs inside this task with its explicit stack budget instead
     * of the caller's context: build the 2x2 view, reset the deterministic
     * mock, and render the first four-stock view before the task's first
     * ~10 second delay, so names and prices are visible immediately. */
    const esp_err_t create_err = stock_view_create();
    if (create_err != ESP_OK) {
        ESP_LOGE(TAG, "stock view create failed: %s",
                 esp_err_to_name(create_err));
        s_service_task = NULL;
        vTaskDelete(NULL);
    }

    stock_mock_reset();
    run_update_cycle();

    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(STOCK_SERVICE_PERIOD_MS));

        stock_mock_tick();
        run_update_cycle();
    }
}

esp_err_t stock_service_start(void)
{
    if (s_service_task != NULL) {
        return ESP_OK;
    }

    /* The spawned task performs view creation, mock reset, and the first
     * render under its own stack budget; the caller never touches LVGL. */
    const BaseType_t ok = xTaskCreate(stock_service_task, "stock_svc",
                                      STOCK_SERVICE_STACK_BYTES, NULL, 2,
                                      &s_service_task);
    return ok == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
