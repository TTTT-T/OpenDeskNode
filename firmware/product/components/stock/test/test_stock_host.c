/*
 * Phase 1C host tests for the pure-C stock model and deterministic mock.
 * Compiled and run on the host by scripts/verify-phase-1c.sh:
 *   cc -std=c99 -Wall -Werror -I<stock include> this file stock_model.c stock_mock.c
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "stock_mock.h"
#include "stock_model.h"

static int failures;

#define CHECK_STR(actual, expected)                                            \
    do {                                                                       \
        if (strcmp((actual), (expected)) != 0) {                               \
            ++failures;                                                        \
            printf("FAIL %s:%d got \"%s\" want \"%s\"\n", __func__, __LINE__,  \
                   (actual), (expected));                                      \
        }                                                                      \
    } while (0)

#define CHECK_TRUE(cond)                                                       \
    do {                                                                       \
        if (!(cond)) {                                                         \
            ++failures;                                                        \
            printf("FAIL %s:%d condition false\n", __func__, __LINE__);        \
        }                                                                      \
    } while (0)

static const stock_quote_t *q(stock_price_t prev, stock_price_t current)
{
    static stock_quote_t quote;
    quote.prev_close = prev;
    quote.current = current;
    return &quote;
}

static void test_fixed_point_change(void)
{
    CHECK_TRUE(stock_quote_change(q(172000, 173550)) == 1550);
    CHECK_TRUE(stock_quote_change(q(25800, 23512)) == -2288);
    CHECK_TRUE(stock_quote_change(q(8740, 8740)) == 0);
}

static void test_change_pct_rounding(void)
{
    /* +15.50 / 1720.00 = +0.9011% -> 0.90% */
    CHECK_TRUE(stock_quote_change_pct_x100(q(172000, 173550)) == 90);
    /* -2.22 / 258.00 = -0.86% */
    CHECK_TRUE(stock_quote_change_pct_x100(q(25800, 25578)) == -86);
    /* 1726 / 25800 = 6.6899% -> 6.69% */
    CHECK_TRUE(stock_quote_change_pct_x100(q(25800, 27526)) == 669);
    /* Exactly +10% limit: 1105.0 -> 1215.5 */
    CHECK_TRUE(stock_quote_change_pct_x100(q(11050, 12155)) == 1000);
    /* Rounding half away from zero: 0.125% -> 0.13% */
    CHECK_TRUE(stock_quote_change_pct_x100(q(80000, 80100)) == 13);
    CHECK_TRUE(stock_quote_change_pct_x100(q(80000, 79900)) == -13);
    CHECK_TRUE(stock_quote_change_pct_x100(q(8740, 8740)) == 0);
}

static void test_format_price(void)
{
    char buffer[16];

    stock_format_price(buffer, sizeof(buffer), 173550);
    CHECK_STR(buffer, "1735.50");
    stock_format_price(buffer, sizeof(buffer), 8740);
    CHECK_STR(buffer, "87.40");
    stock_format_price(buffer, sizeof(buffer), 23220);
    CHECK_STR(buffer, "232.20");
}

static void test_format_change_amount_values(void)
{
    char buffer[16];

    stock_format_change_amount(buffer, sizeof(buffer), q(172000, 173550));
    CHECK_STR(buffer, "+15.50");
    stock_format_change_amount(buffer, sizeof(buffer), q(25800, 23512));
    CHECK_STR(buffer, "-22.88");
    stock_format_change_amount(buffer, sizeof(buffer), q(8740, 8740));
    CHECK_STR(buffer, "0.00");
}

static void test_format_change_percent_exact_semantics(void)
{
    char buffer[20];

    stock_format_change_percent(buffer, sizeof(buffer), q(172000, 173550));
    CHECK_STR(buffer, "\xe2\x96\xb2 +0.90%");
    stock_format_change_percent(buffer, sizeof(buffer), q(25800, 25578));
    CHECK_STR(buffer, "\xe2\x96\xbc -0.86%");
    stock_format_change_percent(buffer, sizeof(buffer), q(8740, 8740));
    CHECK_STR(buffer, "0.00%");
    stock_format_change_percent(buffer, sizeof(buffer), q(11050, 12155));
    CHECK_STR(buffer, "\xe2\x96\xb2 +10.00%");
    CHECK_TRUE(!stock_quote_is_down(q(172000, 173550)));
    CHECK_TRUE(stock_quote_is_up(q(172000, 173550)));
}

static void test_format_change_percent_with_state(void)
{
    char buffer[32];
    stock_quote_t quote;

    /* NORMAL keeps the exact plain semantics, byte for byte. */
    quote.prev_close = 172000;
    quote.current = 173550;
    quote.state = STOCK_MARKET_NORMAL;
    stock_format_change_percent_with_state(buffer, sizeof(buffer), &quote);
    CHECK_STR(buffer, "\xe2\x96\xb2 +0.90%");
    quote.prev_close = 25800;
    quote.current = 25578;
    stock_format_change_percent_with_state(buffer, sizeof(buffer), &quote);
    CHECK_STR(buffer, "\xe2\x96\xbc -0.86%");

    /* Special states prefix the percent line; the amount stays a separate
     * line, so nothing replaces the data. */
    quote.prev_close = 11050;
    quote.current = 12155;
    quote.state = STOCK_MARKET_LIMIT_UP;
    stock_format_change_percent_with_state(buffer, sizeof(buffer), &quote);
    CHECK_STR(buffer, "\xe6\xb6\xa8\xe5\x81\x9c \xe2\x96\xb2 +10.00%");

    quote.prev_close = 25800;
    quote.current = 23220;
    quote.state = STOCK_MARKET_LIMIT_DOWN;
    stock_format_change_percent_with_state(buffer, sizeof(buffer), &quote);
    CHECK_STR(buffer, "\xe8\xb7\x8c\xe5\x81\x9c \xe2\x96\xbc -10.00%");

    quote.prev_close = 8740;
    quote.current = 8740;
    quote.state = STOCK_MARKET_SUSPENDED;
    stock_format_change_percent_with_state(buffer, sizeof(buffer), &quote);
    CHECK_STR(buffer, "\xe5\x81\x9c\xe7\x89\x8c 0.00%");
}

static void test_state_text(void)
{
    CHECK_STR(stock_market_state_text(STOCK_MARKET_NORMAL), "");
    CHECK_STR(stock_market_state_text(STOCK_MARKET_LIMIT_UP), "\xe6\xb6\xa8\xe5\x81\x9c");
    CHECK_STR(stock_market_state_text(STOCK_MARKET_LIMIT_DOWN), "\xe8\xb7\x8c\xe5\x81\x9c");
    CHECK_STR(stock_market_state_text(STOCK_MARKET_SUSPENDED), "\xe5\x81\x9c\xe7\x89\x8c");
}

static bool quote_changes_sign_during_cycle(size_t index, int *direction)
{
    const stock_dashboard_t *snap = stock_mock_snapshot();
    bool below = false;
    bool above = false;
    for (uint16_t t = 0; t < STOCK_MOCK_CYCLE_TICKS; ++t) {
        stock_mock_reset();
        for (uint16_t k = 0; k < t; ++k) {
            stock_mock_tick();
        }
        snap = stock_mock_snapshot();
        const stock_price_t change = stock_quote_change(&snap->quotes[index]);
        below = below || change < 0;
        above = above || change > 0;
    }
    *direction = below && above ? 1 : 0;
    return below && above;
}

static void test_scenario_coverage(void)
{
    bool seen_limit_up = false;
    bool seen_limit_down = false;
    bool seen_suspended = false;
    bool seen_up = false;
    bool seen_down = false;
    bool seen_flat_end = false;
    bool intraday_ok = true;
    bool price_frozen_when_special = true;
    int cross_dirs[STOCK_COUNT] = {0};

    for (uint16_t t = 0; t < STOCK_MOCK_CYCLE_TICKS; ++t) {
        stock_mock_reset();
        for (uint16_t k = 0; k < t; ++k) {
            stock_mock_tick();
        }
        const stock_dashboard_t *snap = stock_mock_snapshot();
        if (snap->quotes[0].intraday_count != t + 1 ||
            snap->quotes[3].intraday_count != t + 1) {
            intraday_ok = false;
        }
        for (size_t i = 0; i < STOCK_COUNT; ++i) {
            const stock_quote_t *q = &snap->quotes[i];
            if (q->state == STOCK_MARKET_LIMIT_UP) {
                seen_limit_up = true;
            }
            if (q->state == STOCK_MARKET_LIMIT_DOWN) {
                seen_limit_down = true;
            }
            if (q->state == STOCK_MARKET_SUSPENDED) {
                seen_suspended = true;
            }
            if (stock_quote_is_up(q)) {
                seen_up = true;
            }
            if (stock_quote_is_down(q)) {
                seen_down = true;
            }
        }
    }

    /* Determinism: two identical passes produce identical snapshots. */
    stock_mock_reset();
    stock_dashboard_t first = *stock_mock_snapshot();
    for (uint16_t k = 0; k < STOCK_MOCK_CYCLE_TICKS + 7; ++k) {
        stock_mock_tick();
    }
    stock_dashboard_t second = *stock_mock_snapshot();
    stock_mock_reset();
    for (uint16_t k = 0; k < STOCK_MOCK_CYCLE_TICKS + 7; ++k) {
        stock_mock_tick();
    }
    stock_dashboard_t third = *stock_mock_snapshot();
    CHECK_TRUE(memcmp(&second, &third, sizeof(second)) == 0);
    CHECK_TRUE(first.quotes[2].current == 8740);

    /* Flat scenario: 比亚迪 ends the cycle exactly flat. */
    stock_mock_reset();
    for (uint16_t k = 0; k < STOCK_MOCK_CYCLE_TICKS - 1; ++k) {
        stock_mock_tick();
    }
    const stock_dashboard_t *snap = stock_mock_snapshot();
    if (stock_quote_change(&snap->quotes[2]) == 0) {
        seen_flat_end = true;
    }

    /* Special states freeze the price at the pinned value. */
    if (snap->quotes[1].state != STOCK_MARKET_LIMIT_DOWN ||
        snap->quotes[1].current != 23220 ||
        snap->quotes[1].current != (snap->quotes[1].prev_close * 9) / 10) {
        price_frozen_when_special = false;
    }
    if (snap->quotes[3].state != STOCK_MARKET_SUSPENDED ||
        snap->quotes[3].current != 12155 ||
        snap->quotes[3].current != (snap->quotes[3].prev_close * 11) / 10) {
        price_frozen_when_special = false;
    }

    /* Crossing previous close: 贵州茅台 crosses up, 宁德时代 crosses down. */
    CHECK_TRUE(quote_changes_sign_during_cycle(0, &cross_dirs[0]));
    CHECK_TRUE(quote_changes_sign_during_cycle(1, &cross_dirs[1]));

    CHECK_TRUE(seen_limit_up);
    CHECK_TRUE(seen_limit_down);
    CHECK_TRUE(seen_suspended);
    CHECK_TRUE(seen_up);
    CHECK_TRUE(seen_down);
    CHECK_TRUE(seen_flat_end);
    CHECK_TRUE(intraday_ok);
    CHECK_TRUE(price_frozen_when_special);
}

static void test_session_and_last_success_update(void)
{
    stock_mock_reset();
    const stock_dashboard_t *snap = stock_mock_snapshot();
    CHECK_TRUE(snap->session == STOCK_SESSION_OPEN);
    CHECK_TRUE(snap->last_success_update_ms == 0);
    stock_mock_tick();
    stock_mock_tick();
    snap = stock_mock_snapshot();
    CHECK_TRUE(snap->last_success_update_ms == 2 * STOCK_MOCK_TICK_INTERVAL_MS);
}

int main(void)
{
    test_fixed_point_change();
    test_change_pct_rounding();
    test_format_price();
    test_format_change_amount_values();
    test_format_change_percent_exact_semantics();
    test_format_change_percent_with_state();
    test_state_text();
    test_scenario_coverage();
    test_session_and_last_success_update();

    if (failures != 0) {
        printf("PHASE1C_STOCK_HOST_TESTS_FAILED (%d failures)\n", failures);
        return 1;
    }
    printf("PHASE1C_STOCK_HOST_TESTS_OK\n");
    return 0;
}
