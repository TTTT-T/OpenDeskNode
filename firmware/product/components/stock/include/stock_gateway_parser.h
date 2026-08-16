#pragma once

#include <stddef.h>

#include "stock_model.h"

typedef enum {
    STOCK_GATEWAY_PARSE_OK = 0,
    STOCK_GATEWAY_PARSE_INVALID_JSON,
    STOCK_GATEWAY_PARSE_INVALID_SCHEMA,
    STOCK_GATEWAY_PARSE_INVALID_DATA,
} stock_gateway_parse_result_t;

/** Convert one compact schema-v1 Gateway response into the pure stock model. */
stock_gateway_parse_result_t stock_gateway_parse_dashboard(
    const char *json, size_t length, stock_dashboard_t *dashboard);

const char *stock_gateway_parse_result_text(stock_gateway_parse_result_t result);
