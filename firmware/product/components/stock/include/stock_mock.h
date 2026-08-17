#pragma once

/*
 * Deterministic stock data source for Phase 1C.
 *
 * A fixed scenario table advances one tick per call; no randomness, no
 * network, no real market API. One full cycle is 24 ticks and collectively
 * covers: normal rise, normal fall, flat, limit-up, limit-down, suspended,
 * and crossing the previous close in both directions. The Stock Gateway
 * client replaces this producer in Phase 1E.
 */

#include "stock_model.h"

/** Number of ticks in one deterministic scenario cycle. */
#define STOCK_MOCK_CYCLE_TICKS 24

/** Wall-clock period of one mock tick in milliseconds (about 10 seconds). */
#define STOCK_MOCK_TICK_INTERVAL_MS 10000

/** Reset to the first tick of the scenario cycle. */
void stock_mock_reset(void);

/** Advance exactly one tick and refresh the dashboard model. */
void stock_mock_tick(void);

/** Current tick index within the scenario cycle (0 .. STOCK_MOCK_CYCLE_TICKS-1). */
uint16_t stock_mock_tick_index(void);

/** Read-only view of the current dashboard model. */
const stock_dashboard_t *stock_mock_snapshot(void);
