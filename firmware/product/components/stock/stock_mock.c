/*
 * Deterministic stock mock (Phase 1C). Pure C99, host-testable.
 *
 * Scenario roles across the 24-tick cycle:
 *   quotes[0] 贵州茅台: normal rise, crosses prev_close upward mid-cycle.
 *   quotes[1] 宁德时代: normal fall, crosses prev_close downward, ends pinned
 *                       at the -10% limit price (LIMIT_DOWN).
 *   quotes[2] 比亚迪:   flat around prev_close (change 0.00% at cycle end).
 *   quotes[3] 中国平安: normal rise, pinned at +10% limit (LIMIT_UP), then
 *                       suspended with the last price frozen.
 */
#include "stock_mock.h"

#include <string.h>

typedef struct {
    const char *name;
    stock_price_t prev_close;
    stock_price_t path[STOCK_MOCK_CYCLE_TICKS];
    stock_market_state_t states[STOCK_MOCK_CYCLE_TICKS];
} stock_scenario_t;

static const stock_scenario_t SCENARIOS[STOCK_COUNT] = {
    {
        .name = "贵州茅台",
        .prev_close = 172000,
        .path = {
            171200, 171050, 171300, 171500, 171450, 171650, 171800, 171900,
            172050, 172100, 172250, 172400, 172500, 172650, 172750, 172850,
            172900, 173000, 173100, 173200, 173250, 173350, 173450, 173550,
        },
        .states = {
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
        },
    },
    {
        .name = "宁德时代",
        .prev_close = 25800,
        .path = {
            26200, 26050, 25900, 25850, 25700, 25500, 25300, 25150,
            25000, 24850, 24700, 24550, 24400, 24250, 24100, 23950,
            23800, 23600, 23400, 23220, 23220, 23220, 23220, 23220,
        },
        .states = {
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_LIMIT_DOWN, STOCK_MARKET_LIMIT_DOWN,
            STOCK_MARKET_LIMIT_DOWN, STOCK_MARKET_LIMIT_DOWN, STOCK_MARKET_LIMIT_DOWN,
        },
    },
    {
        .name = "比亚迪",
        .prev_close = 8740,
        .path = {
            8740, 8740, 8730, 8740, 8740, 8750, 8740, 8730,
            8740, 8740, 8740, 8730, 8740, 8740, 8740, 8740,
            8750, 8740, 8740, 8730, 8740, 8740, 8740, 8740,
        },
        .states = {
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
        },
    },
    {
        .name = "中国平安",
        .prev_close = 11050,
        .path = {
            11080, 11150, 11230, 11310, 11400, 11500, 11620, 11760,
            11910, 12040, 12155, 12155, 12155, 12155, 12155, 12155,
            12155, 12155, 12155, 12155, 12155, 12155, 12155, 12155,
        },
        .states = {
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL, STOCK_MARKET_NORMAL,
            STOCK_MARKET_NORMAL, STOCK_MARKET_LIMIT_UP, STOCK_MARKET_LIMIT_UP,
            STOCK_MARKET_LIMIT_UP, STOCK_MARKET_LIMIT_UP, STOCK_MARKET_LIMIT_UP,
            STOCK_MARKET_LIMIT_UP, STOCK_MARKET_SUSPENDED, STOCK_MARKET_SUSPENDED,
            STOCK_MARKET_SUSPENDED, STOCK_MARKET_SUSPENDED, STOCK_MARKET_SUSPENDED,
            STOCK_MARKET_SUSPENDED, STOCK_MARKET_SUSPENDED, STOCK_MARKET_SUSPENDED,
        },
    },
};

static stock_dashboard_t s_dashboard;
static uint16_t s_tick;

static void apply_tick(uint16_t tick)
{
    for (size_t i = 0; i < STOCK_COUNT; ++i) {
        stock_quote_t *quote = &s_dashboard.quotes[i];
        if (tick == 0) {
            quote->intraday_count = 0;
        }
        quote->current = SCENARIOS[i].path[tick];
        quote->state = SCENARIOS[i].states[tick];
        if (quote->intraday_count < STOCK_INTRADAY_SAMPLES) {
            quote->intraday[quote->intraday_count++] = quote->current;
        }
    }
    s_dashboard.session = STOCK_SESSION_OPEN;
    s_dashboard.has_data = true;
    s_dashboard.data_state = STOCK_DATA_FRESH;
    s_dashboard.last_success_update_ms += STOCK_MOCK_TICK_INTERVAL_MS;
}

void stock_mock_reset(void)
{
    memset(&s_dashboard, 0, sizeof(s_dashboard));
    for (size_t i = 0; i < STOCK_COUNT; ++i) {
        strncpy(s_dashboard.quotes[i].name, SCENARIOS[i].name,
                STOCK_NAME_MAX_BYTES - 1);
        s_dashboard.quotes[i].name[STOCK_NAME_MAX_BYTES - 1] = '\0';
        s_dashboard.quotes[i].prev_close = SCENARIOS[i].prev_close;
    }
    s_tick = 0;
    apply_tick(0);
    /* Boot baseline: the reset state itself is not a timed refresh. */
    s_dashboard.last_success_update_ms = 0;
}

void stock_mock_tick(void)
{
    s_tick = (uint16_t)((s_tick + 1U) % STOCK_MOCK_CYCLE_TICKS);
    apply_tick(s_tick);
}

const stock_dashboard_t *stock_mock_snapshot(void)
{
    return &s_dashboard;
}

uint16_t stock_mock_tick_index(void)
{
    return s_tick;
}
