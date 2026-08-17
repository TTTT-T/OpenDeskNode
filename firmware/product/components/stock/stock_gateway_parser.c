#include "stock_gateway_parser.h"

#include <limits.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "cJSON.h"

static const cJSON *object_item(const cJSON *object, const char *name)
{
    return cJSON_GetObjectItemCaseSensitive(object, name);
}

static bool positive_price(const cJSON *item, stock_price_t *price)
{
    if (!cJSON_IsNumber(item) || !isfinite(item->valuedouble) ||
        item->valuedouble <= 0.0 ||
        item->valuedouble > ((double)INT32_MAX / 100.0)) {
        return false;
    }
    *price = (stock_price_t)(item->valuedouble * 100.0 + 0.5);
    return true;
}

static bool copy_name(const cJSON *item, char *name, size_t size)
{
    if (!cJSON_IsString(item) || item->valuestring == NULL ||
        item->valuestring[0] == '\0') {
        return false;
    }
    const size_t length = strlen(item->valuestring);
    if (length >= size) {
        return false;
    }
    memcpy(name, item->valuestring, length + 1);
    return true;
}

static bool parse_market_state(const cJSON *item, stock_market_state_t *state)
{
    if (!cJSON_IsString(item) || item->valuestring == NULL) {
        return false;
    }
    if (strcmp(item->valuestring, "NORMAL") == 0) {
        *state = STOCK_MARKET_NORMAL;
    } else if (strcmp(item->valuestring, "LIMIT_UP") == 0) {
        *state = STOCK_MARKET_LIMIT_UP;
    } else if (strcmp(item->valuestring, "LIMIT_DOWN") == 0) {
        *state = STOCK_MARKET_LIMIT_DOWN;
    } else if (strcmp(item->valuestring, "SUSPENDED") == 0) {
        *state = STOCK_MARKET_SUSPENDED;
    } else if (strcmp(item->valuestring, "UNKNOWN") == 0) {
        *state = STOCK_MARKET_UNKNOWN;
    } else {
        return false;
    }
    return true;
}

static bool parse_session(const cJSON *root, stock_dashboard_t *dashboard)
{
    const cJSON *market_session = object_item(root, "market_session");
    if (!cJSON_IsObject(market_session)) {
        return false;
    }
    const cJSON *state = object_item(market_session, "state");
    if (!cJSON_IsString(state) ||
        state->valuestring == NULL) {
        return false;
    }
    if (strcmp(state->valuestring, "TRADING") == 0) {
        dashboard->session = STOCK_SESSION_OPEN;
    } else if (strcmp(state->valuestring, "PRE_MARKET") == 0) {
        dashboard->session = STOCK_SESSION_PRE_MARKET;
    } else if (strcmp(state->valuestring, "MIDDAY_BREAK") == 0) {
        dashboard->session = STOCK_SESSION_LUNCH_BREAK;
    } else if (strcmp(state->valuestring, "CLOSED") == 0) {
        dashboard->session = STOCK_SESSION_CLOSED;
    } else if (strcmp(state->valuestring, "STANDBY") == 0) {
        dashboard->session = STOCK_SESSION_STANDBY;
    } else {
        return false;
    }

    const cJSON *next_open = object_item(root, "next_open_at");
    if (!cJSON_IsString(next_open) || next_open->valuestring == NULL) {
        return false;
    }
    const char *time = strchr(next_open->valuestring, 'T');
    if (time == NULL || strlen(time + 1) < 5 || time[3] != ':') {
        return false;
    }
    memcpy(dashboard->next_open_time, time + 1, 5);
    dashboard->next_open_time[5] = '\0';

    const cJSON *seconds = object_item(root, "next_open_in_seconds");
    if (!cJSON_IsNumber(seconds) || !isfinite(seconds->valuedouble) ||
        seconds->valuedouble < 0.0 || seconds->valuedouble > UINT32_MAX) {
        return false;
    }
    dashboard->next_open_minutes =
        (uint32_t)((seconds->valuedouble + 59.0) / 60.0);

    const cJSON *freshness = object_item(root, "freshness");
    if (!cJSON_IsObject(freshness)) {
        return false;
    }
    const cJSON *last_success = object_item(freshness, "last_success_at");
    if (!cJSON_IsString(last_success) || last_success->valuestring == NULL) {
        return false;
    }
    time = strchr(last_success->valuestring, 'T');
    if (time == NULL || strlen(time + 1) < 5 || time[3] != ':') {
        return false;
    }
    memcpy(dashboard->last_success_time, time + 1, 5);
    dashboard->last_success_time[5] = '\0';
    return true;
}

static bool parse_quote(const cJSON *item, stock_quote_t *quote)
{
    if (!cJSON_IsObject(item) ||
        !copy_name(object_item(item, "name"), quote->name, sizeof(quote->name)) ||
        !positive_price(object_item(item, "current_price"), &quote->current) ||
        !positive_price(object_item(item, "previous_close"), &quote->prev_close) ||
        !parse_market_state(object_item(item, "status"), &quote->state)) {
        return false;
    }

    const cJSON *intraday = object_item(item, "intraday");
    if (!cJSON_IsArray(intraday)) {
        return false;
    }
    const int count = cJSON_GetArraySize(intraday);
    if (count < 0 || count > STOCK_INTRADAY_SAMPLES) {
        return false;
    }
    for (int index = 0; index < count; ++index) {
        const cJSON *bar = cJSON_GetArrayItem(intraday, index);
        if (!cJSON_IsObject(bar) ||
            !positive_price(object_item(bar, "price"), &quote->intraday[index])) {
            return false;
        }
    }
    quote->intraday_count = (uint16_t)count;
    return true;
}

stock_gateway_parse_result_t stock_gateway_parse_dashboard(
    const char *json, size_t length, stock_dashboard_t *dashboard)
{
    if (json == NULL || length == 0 || dashboard == NULL) {
        return STOCK_GATEWAY_PARSE_INVALID_DATA;
    }
    cJSON *root = cJSON_ParseWithLength(json, length);
    if (root == NULL) {
        return STOCK_GATEWAY_PARSE_INVALID_JSON;
    }

    stock_dashboard_t parsed = {0};
    const cJSON *schema = object_item(root, "schema_version");
    const cJSON *quotes = object_item(root, "quotes");
    const cJSON *stale = object_item(root, "stale");
    if (!cJSON_IsObject(root) || !cJSON_IsNumber(schema) ||
        schema->valuedouble != 1.0) {
        cJSON_Delete(root);
        return STOCK_GATEWAY_PARSE_INVALID_SCHEMA;
    }
    if (!cJSON_IsArray(quotes) || cJSON_GetArraySize(quotes) != STOCK_COUNT ||
        !cJSON_IsBool(stale) || !parse_session(root, &parsed)) {
        cJSON_Delete(root);
        return STOCK_GATEWAY_PARSE_INVALID_DATA;
    }
    for (int index = 0; index < STOCK_COUNT; ++index) {
        if (!parse_quote(cJSON_GetArrayItem(quotes, index), &parsed.quotes[index])) {
            cJSON_Delete(root);
            return STOCK_GATEWAY_PARSE_INVALID_DATA;
        }
    }

    parsed.has_data = true;
    parsed.data_state = cJSON_IsTrue(stale) ? STOCK_DATA_STALE : STOCK_DATA_FRESH;
    *dashboard = parsed;
    cJSON_Delete(root);
    return STOCK_GATEWAY_PARSE_OK;
}

const char *stock_gateway_parse_result_text(stock_gateway_parse_result_t result)
{
    switch (result) {
    case STOCK_GATEWAY_PARSE_OK:
        return "ok";
    case STOCK_GATEWAY_PARSE_INVALID_JSON:
        return "invalid-json";
    case STOCK_GATEWAY_PARSE_INVALID_SCHEMA:
        return "invalid-schema";
    case STOCK_GATEWAY_PARSE_INVALID_DATA:
    default:
        return "invalid-data";
    }
}
