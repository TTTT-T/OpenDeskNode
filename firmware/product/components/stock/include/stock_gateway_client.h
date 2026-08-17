#pragma once

#include <stddef.h>

#include "esp_err.h"
#include "stock_model.h"

/** Fetch and strictly parse one compact dashboard response. */
esp_err_t stock_gateway_fetch(stock_dashboard_t *dashboard, size_t *response_bytes);
