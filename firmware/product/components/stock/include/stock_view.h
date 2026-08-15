#pragma once

#include "esp_err.h"
#include "stock_model.h"

/*
 * Build and refresh the 2x2 stock dashboard on the RLCD. The view renders
 * exactly the confirmed v1 per-stock information (Chinese name, price,
 * change amount, change percent, status, sparkline with a dashed
 * previous-close baseline) and nothing else.
 */

/** Create the dashboard screen and make it the active screen. */
esp_err_t stock_view_create(void);

/**
 * Refresh all four panels from the model. Acquires the display lock;
 * callers must not hold it.
 */
void stock_view_update(const stock_dashboard_t *dashboard);
