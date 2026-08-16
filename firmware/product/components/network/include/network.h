#pragma once

#include <stdbool.h>

#include "esp_err.h"

typedef enum {
    NETWORK_STATUS_STARTING,
    NETWORK_STATUS_CONNECTING,
    NETWORK_STATUS_CONNECTED,
    NETWORK_STATUS_DISCONNECTED,
    NETWORK_STATUS_PROVISIONING,
    NETWORK_STATUS_UNCONFIGURED,
} network_status_t;

typedef void (*network_status_callback_t)(network_status_t status);

/** Initialize NVS, the event loop, and a station-mode Wi-Fi client. */
esp_err_t network_init(network_status_callback_t callback);

/** True only after station mode has obtained an IP address. */
bool network_is_connected(void);

/** Return a user-visible status string with no SSID, password, or IP address. */
const char *network_status_text(network_status_t status);
