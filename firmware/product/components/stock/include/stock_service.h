#pragma once

#include "esp_err.h"

/*
 * Phase 1C orchestration service: advance the deterministic mock about every
 * 10 seconds, refresh the view, and log one compact metrics line per update
 * (view wall cost, full-frame flush count/time, internal heap and PSRAM).
 */

/** Start the stock refresh task. Returns ESP_ERR_NO_MEM if it cannot spawn. */
esp_err_t stock_service_start(void);
