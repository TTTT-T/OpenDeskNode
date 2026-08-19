#pragma once

#include <stdbool.h>

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

typedef enum {
    AUDIO_OWNER_NONE = 0,
    AUDIO_OWNER_VOICE,
    AUDIO_OWNER_SELFTEST,
} audio_owner_id_t;

esp_err_t audio_owner_init(void);
void audio_owner_request(audio_owner_id_t id);
esp_err_t audio_owner_acquire(audio_owner_id_t id, TickType_t timeout);
esp_err_t audio_owner_release(audio_owner_id_t id);
audio_owner_id_t audio_owner_current(void);
bool audio_owner_is(audio_owner_id_t id);
bool audio_owner_should_yield(audio_owner_id_t id);
