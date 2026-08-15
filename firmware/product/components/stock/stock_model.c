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
    case STOCK_MARKET_NORMAL:
    default:
        return "";
    }
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
