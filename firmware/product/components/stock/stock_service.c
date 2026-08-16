/* Phase 1E live stock service: LAN Gateway -> canonical model -> LVGL. */
#include "stock_service.h"

#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "display.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "network.h"
#include "stock_gateway_client.h"
#include "stock_view.h"

static const char *TAG = "stock-1e";
static const uint32_t STOCK_SERVICE_PERIOD_MS = 10000;
static const uint32_t STOCK_INITIAL_RETRY_MS = 5000;
static const int64_t STOCK_STALE_AFTER_MS = 5 * 60 * 1000;
static const size_t STOCK_SERVICE_STACK_BYTES = 16384;
static TaskHandle_t s_service_task;
static stock_dashboard_t s_dashboard;
static int64_t s_service_started_ms;
static uint32_t s_cycle;

static int64_t uptime_ms(void)
{
    return esp_timer_get_time() / 1000;
}

static void log_cycle(esp_err_t fetch_err, size_t response_bytes,
                      int64_t view_us, const display_flush_metrics_t *flush)
{
    const size_t internal_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    const size_t internal_largest =
        heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
    const size_t psram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    const uint32_t flush_avg_us = flush->flush_count == 0
                                      ? 0
                                      : (uint32_t)(flush->flush_total_us /
                                                   flush->flush_count);

    ESP_LOGI(TAG,
             "cycle=%lu fetch=%s bytes=%u data=%s view_us=%lld "
             "flush_count=%lu flush_avg_us=%lu flush_max_us=%lu "
             "heap_internal=%u heap_internal_largest=%u psram_free=%u",
             (unsigned long)s_cycle, esp_err_to_name(fetch_err),
             (unsigned)response_bytes,
             s_dashboard.data_state == STOCK_DATA_FRESH
                 ? "fresh"
                 : (s_dashboard.data_state == STOCK_DATA_STALE ? "stale" : "starting"),
             (long long)view_us, (unsigned long)flush->flush_count,
             (unsigned long)flush_avg_us, (unsigned long)flush->flush_max_us,
             (unsigned)internal_free, (unsigned)internal_largest,
             (unsigned)psram_free);
}

static int64_t render_dashboard(void)
{
    const int64_t started_us = esp_timer_get_time();
    stock_view_update(&s_dashboard);
    return esp_timer_get_time() - started_us;
}

static void stock_service_task(void *arg)
{
    (void)arg;
    const esp_err_t create_err = stock_view_create();
    if (create_err != ESP_OK) {
        ESP_LOGE(TAG, "stock view create failed: %s", esp_err_to_name(create_err));
        s_service_task = NULL;
        vTaskDelete(NULL);
        return;
    }

    memset(&s_dashboard, 0, sizeof(s_dashboard));
    s_dashboard.data_state = STOCK_DATA_STARTING;
    s_service_started_ms = uptime_ms();
    render_dashboard();
    display_flush_metrics_take();

    for (;;) {
        const int64_t now_ms = uptime_ms();
        size_t response_bytes = 0;
        esp_err_t fetch_err = ESP_ERR_INVALID_STATE;
        int64_t view_us = 0;
        bool should_render = false;

        if (network_is_connected()) {
            stock_dashboard_t candidate = {0};
            fetch_err = stock_gateway_fetch(&candidate, &response_bytes);
            if (fetch_err == ESP_OK) {
                candidate.last_success_update_ms = now_ms;
                s_dashboard = candidate;
                should_render = true;
            } else {
                should_render = stock_dashboard_apply_failure(
                    &s_dashboard, now_ms, s_service_started_ms,
                    STOCK_STALE_AFTER_MS);
            }
        } else {
            should_render = stock_dashboard_apply_failure(
                &s_dashboard, now_ms, s_service_started_ms,
                STOCK_STALE_AFTER_MS);
        }

        if (should_render) {
            view_us = render_dashboard();
        }
        const display_flush_metrics_t flush = display_flush_metrics_take();
        ++s_cycle;
        log_cycle(fetch_err, response_bytes, view_us, &flush);

        vTaskDelay(pdMS_TO_TICKS(s_dashboard.has_data
                                     ? STOCK_SERVICE_PERIOD_MS
                                     : STOCK_INITIAL_RETRY_MS));
    }
}

esp_err_t stock_service_start(void)
{
    if (s_service_task != NULL) {
        return ESP_OK;
    }
    const BaseType_t ok = xTaskCreate(stock_service_task, "stock_svc",
                                      STOCK_SERVICE_STACK_BYTES, NULL, 2,
                                      &s_service_task);
    return ok == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
