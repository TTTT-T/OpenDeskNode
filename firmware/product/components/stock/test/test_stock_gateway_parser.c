#include <stdio.h>
#include <string.h>

#include "stock_gateway_parser.h"

static int failures;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            ++failures;                                                         \
            printf("FAIL %s:%d\n", __func__, __LINE__);                       \
        }                                                                       \
    } while (0)

#define QUOTE(name, current, previous, state, price)                            \
    "{\"name\":\"" name "\",\"current_price\":" current               \
    ",\"previous_close\":" previous ",\"status\":\"" state               \
    "\",\"intraday\":[{\"price\":" price "}]}"

static const char VALID_JSON[] =
    "{\"schema_version\":1,\"quotes\":["
    QUOTE("贵州茅台", "1341.99", "1355.29", "NORMAL", "1341.99") ","
    QUOTE("平安银行", "11.11", "11.25", "UNKNOWN", "11.11") ","
    QUOTE("宁德时代", "393.93", "396.30", "LIMIT_UP", "393.93") ","
    QUOTE("中芯国际", "132.87", "129.44", "SUSPENDED", "132.87")
    "],\"market_session\":{\"state\":\"STANDBY\"},"
    "\"next_open_at\":\"2026-08-17T09:30:00+08:00\","
    "\"next_open_in_seconds\":77400,"
    "\"freshness\":{\"last_success_at\":\"2026-08-16T12:34:56+08:00\"},"
    "\"stale\":false}";

static void test_valid_dashboard(void)
{
    stock_dashboard_t dashboard;
    CHECK(stock_gateway_parse_dashboard(VALID_JSON, strlen(VALID_JSON), &dashboard) ==
          STOCK_GATEWAY_PARSE_OK);
    CHECK(dashboard.has_data);
    CHECK(dashboard.data_state == STOCK_DATA_FRESH);
    CHECK(dashboard.session == STOCK_SESSION_STANDBY);
    CHECK(strcmp(dashboard.next_open_time, "09:30") == 0);
    CHECK(dashboard.next_open_minutes == 1290);
    CHECK(strcmp(dashboard.last_success_time, "12:34") == 0);
    CHECK(strcmp(dashboard.quotes[0].name, "贵州茅台") == 0);
    CHECK(dashboard.quotes[0].current == 134199);
    CHECK(dashboard.quotes[0].prev_close == 135529);
    CHECK(dashboard.quotes[1].state == STOCK_MARKET_UNKNOWN);
    CHECK(dashboard.quotes[2].state == STOCK_MARKET_LIMIT_UP);
    CHECK(dashboard.quotes[3].state == STOCK_MARKET_SUSPENDED);
    CHECK(dashboard.quotes[0].intraday_count == 1);
}

static void test_rejects_schema_and_incomplete_quotes(void)
{
    stock_dashboard_t dashboard;
    const char wrong_schema[] = "{\"schema_version\":2}";
    const char incomplete[] =
        "{\"schema_version\":1,\"quotes\":[],"
        "\"market_session\":{\"state\":\"TRADING\"},"
        "\"next_open_at\":\"2026-08-17T13:00:00+08:00\",\"stale\":false}";
    CHECK(stock_gateway_parse_dashboard(wrong_schema, strlen(wrong_schema), &dashboard) ==
          STOCK_GATEWAY_PARSE_INVALID_SCHEMA);
    CHECK(stock_gateway_parse_dashboard(incomplete, strlen(incomplete), &dashboard) ==
          STOCK_GATEWAY_PARSE_INVALID_DATA);
    CHECK(stock_gateway_parse_dashboard("not-json", 8, &dashboard) ==
          STOCK_GATEWAY_PARSE_INVALID_JSON);
}

static void test_stale_gateway_is_preserved_in_model(void)
{
    char stale[sizeof(VALID_JSON)];
    memcpy(stale, VALID_JSON, sizeof(VALID_JSON));
    char *value = strstr(stale, "\"stale\":false");
    CHECK(value != NULL);
    if (value != NULL) {
        memcpy(value, "\"stale\":true ", strlen("\"stale\":true "));
        stock_dashboard_t dashboard;
        CHECK(stock_gateway_parse_dashboard(stale, strlen(stale), &dashboard) ==
              STOCK_GATEWAY_PARSE_OK);
        CHECK(dashboard.data_state == STOCK_DATA_STALE);
    }
}

int main(void)
{
    test_valid_dashboard();
    test_rejects_schema_and_incomplete_quotes();
    test_stale_gateway_is_preserved_in_model();
    if (failures != 0) {
        printf("PHASE1E_GATEWAY_PARSER_TESTS_FAILED (%d failures)\n", failures);
        return 1;
    }
    printf("PHASE1E_GATEWAY_PARSER_TESTS_OK\n");
    return 0;
}
