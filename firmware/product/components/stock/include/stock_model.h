#pragma once

/*
 * Canonical stock dashboard model (Phase 1C).
 *
 * Pure C99, no ESP-IDF or LVGL dependencies, so the fixed-point math and the
 * exact up/down formatting semantics are host-testable. The same model will
 * be filled by the Stock Gateway client in Phase 1E; the mock in stock_mock.c
 * is the only Phase 1C producer.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define STOCK_COUNT 4
#define STOCK_NAME_MAX_BYTES 16
#define STOCK_INTRADAY_SAMPLES 32

typedef enum {
    STOCK_MARKET_NORMAL = 0,
    STOCK_MARKET_LIMIT_UP,
    STOCK_MARKET_LIMIT_DOWN,
    STOCK_MARKET_SUSPENDED,
} stock_market_state_t;

/* Reserved for Phase 1E session handling (pre-market, lunch break, standby). */
typedef enum {
    STOCK_SESSION_OPEN = 0,
    STOCK_SESSION_PRE_MARKET,
    STOCK_SESSION_LUNCH_BREAK,
    STOCK_SESSION_CLOSED,
    STOCK_SESSION_STANDBY,
} stock_session_t;

/* Price in fixed-point cents (2 decimals); 1735.50 CNY == 173550. */
typedef int32_t stock_price_t;

typedef struct {
    char name[STOCK_NAME_MAX_BYTES];
    stock_price_t prev_close;
    stock_price_t current;
    stock_price_t intraday[STOCK_INTRADAY_SAMPLES];
    uint16_t intraday_count;
    stock_market_state_t state;
} stock_quote_t;

typedef struct {
    stock_quote_t quotes[STOCK_COUNT];
    stock_session_t session;
    /* Uptime milliseconds of the last successful data refresh (0 = never). */
    int64_t last_success_update_ms;
} stock_dashboard_t;

/** Signed change amount in cents: current - prev_close. */
stock_price_t stock_quote_change(const stock_quote_t *quote);

/** Change percent times 100 (87 == 0.87%), rounded half away from zero. */
int32_t stock_quote_change_pct_x100(const stock_quote_t *quote);

bool stock_quote_is_up(const stock_quote_t *quote);
bool stock_quote_is_down(const stock_quote_t *quote);

/** Short status text: "涨停", "跌停", "停牌", or "" for NORMAL. */
const char *stock_market_state_text(stock_market_state_t state);

/** Render "1735.50" from fixed-point cents. */
void stock_format_price(char *buffer, size_t size, stock_price_t price);

/** Render the signed change amount: "+15.50", "-12.86", "0.00". */
void stock_format_change_amount(char *buffer, size_t size, const stock_quote_t *quote);

/** Render the exact up/down line: "▲ +0.90%", "▼ -0.86%", "0.00%". */
void stock_format_change_percent(char *buffer, size_t size, const stock_quote_t *quote);

/**
 * Percent line with the special state as an additional prefix instead of
 * replacing data: "涨停 ▲ +10.00%", "跌停 ▼ -10.00%", "停牌 ▲ +10.00%".
 * NORMAL keeps the exact plain semantics "▲ +0.90%" / "▼ -0.86%" / "0.00%".
 */
void stock_format_change_percent_with_state(char *buffer, size_t size,
                                            const stock_quote_t *quote);
