/*
 * Stock model helpers (Phase 1C). Pure C99, host-testable.
 */
#include "stock_model.h"

#include <stdio.h>
#include <string.h>

stock_price_t stock_quote_change(const stock_quote_t *quote)
{
    return quote->current - quote->prev_close;
}

int32_t stock_quote_change_pct_x100(const stock_quote_t *quote)
{
    if (quote->prev_close == 0) {
        return 0;
    }
    /* Symmetric rounding half away from zero, all in 64-bit integer math. */
    const int64_t numerator = (int64_t)stock_quote_change(quote) * 10000;
    const int64_t denominator = quote->prev_close;
    const int64_t half = denominator / 2;
    if (numerator >= 0) {
        return (int32_t)((numerator + half) / denominator);
    }
    return (int32_t)((numerator - half) / denominator);
}

bool stock_quote_is_up(const stock_quote_t *quote)
{
    return stock_quote_change(quote) > 0;
}

bool stock_quote_is_down(const stock_quote_t *quote)
{
    return stock_quote_change(quote) < 0;
}

const char *stock_market_state_text(stock_market_state_t state)
{
    switch (state) {
    case STOCK_MARKET_LIMIT_UP:
        return "涨停";
    case STOCK_MARKET_LIMIT_DOWN:
        return "跌停";
    case STOCK_MARKET_SUSPENDED:
        return "停牌";
    case STOCK_MARKET_UNKNOWN:
    case STOCK_MARKET_NORMAL:
    default:
        return "";
    }
}

void stock_format_dashboard_banner(char *buffer, size_t size,
                                   const stock_dashboard_t *dashboard)
{
    if (dashboard->data_state == STOCK_DATA_STALE) {
        snprintf(buffer, size, "行情异常 %s",
                 dashboard->last_success_time[0]
                     ? dashboard->last_success_time
                     : "--:--");
        return;
    }
    if (dashboard->data_state == STOCK_DATA_STARTING || !dashboard->has_data) {
        snprintf(buffer, size, "连接中");
        return;
    }

    switch (dashboard->session) {
    case STOCK_SESSION_OPEN:
        snprintf(buffer, size, "交易中");
        break;
    case STOCK_SESSION_PRE_MARKET:
        snprintf(buffer, size, "盘前 %lum",
                 (unsigned long)dashboard->next_open_minutes);
        break;
    case STOCK_SESSION_LUNCH_BREAK:
        snprintf(buffer, size, "午间休市 %lum",
                 (unsigned long)dashboard->next_open_minutes);
        break;
    case STOCK_SESSION_CLOSED:
        snprintf(buffer, size, "已收盘");
        break;
    case STOCK_SESSION_STANDBY:
    default:
        snprintf(buffer, size, "休市待机 %s",
                 dashboard->next_open_time[0] ? dashboard->next_open_time : "");
        break;
    }
}

bool stock_dashboard_apply_failure(stock_dashboard_t *dashboard,
                                   int64_t now_ms,
                                   int64_t service_started_ms,
                                   int64_t stale_after_ms)
{
    if (dashboard == NULL || stale_after_ms < 0) {
        return false;
    }
    const int64_t reference = dashboard->last_success_update_ms > 0
                                  ? dashboard->last_success_update_ms
                                  : service_started_ms;
    if (now_ms - reference <= stale_after_ms ||
        dashboard->data_state == STOCK_DATA_STALE) {
        return false;
    }
    dashboard->data_state = STOCK_DATA_STALE;
    return true;
}

void stock_format_price(char *buffer, size_t size, stock_price_t price)
{
    const bool negative = price < 0;
    const int32_t magnitude = negative ? -price : price;
    snprintf(buffer, size, "%s%ld.%02ld", negative ? "-" : "",
             (long)(magnitude / 100), (long)(magnitude % 100));
}

void stock_format_change_amount(char *buffer, size_t size, const stock_quote_t *quote)
{
    const stock_price_t change = stock_quote_change(quote);
    const char sign = change > 0 ? '+' : (change < 0 ? '-' : ' ');
    char amount[16];
    stock_format_price(amount, sizeof(amount), change < 0 ? -change : change);
    if (change == 0) {
        snprintf(buffer, size, "%s", amount);
    } else {
        snprintf(buffer, size, "%c%s", sign, amount);
    }
}

void stock_format_change_percent(char *buffer, size_t size, const stock_quote_t *quote)
{
    const int32_t pct_x100 = stock_quote_change_pct_x100(quote);
    const int32_t magnitude = pct_x100 < 0 ? -pct_x100 : pct_x100;
    const long whole = magnitude / 100;
    const long frac = magnitude % 100;

    if (pct_x100 > 0) {
        snprintf(buffer, size, "\xe2\x96\xb2 +%ld.%02ld%%", whole, frac);
    } else if (pct_x100 < 0) {
        snprintf(buffer, size, "\xe2\x96\xbc -%ld.%02ld%%", whole, frac);
    } else {
        snprintf(buffer, size, "0.00%%");
    }
}

void stock_format_change_percent_with_state(char *buffer, size_t size,
                                            const stock_quote_t *quote)
{
    char percent[24];
    stock_format_change_percent(percent, sizeof(percent), quote);
    const char *state_text = stock_market_state_text(quote->state);
    if (state_text[0] == '\0') {
        snprintf(buffer, size, "%s", percent);
        return;
    }
    snprintf(buffer, size, "%s %s", state_text, percent);
}
