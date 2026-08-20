#pragma once

#include <stdbool.h>

#include "esp_err.h"

esp_err_t voice_runtime_start(void);
void voice_runtime_request_talk(void);
void voice_runtime_on_wake(void);
void voice_runtime_on_network(bool connected);
