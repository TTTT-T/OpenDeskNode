#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    VOICE_WAKE_SRC_NONE = 0,
    VOICE_WAKE_SRC_MANUAL,
    VOICE_WAKE_SRC_MOCK,
    VOICE_WAKE_SRC_WAKENET,
} voice_wake_source_t;

typedef struct {
    voice_wake_source_t source;
    bool armed;
    bool pending;
    uint32_t mock_hits;
    uint32_t manual_hits;
} voice_wake_t;

void voice_wake_init(voice_wake_t *w, voice_wake_source_t src);
void voice_wake_reset(voice_wake_t *w);
void voice_wake_arm(voice_wake_t *w);
void voice_wake_disarm(voice_wake_t *w);
bool voice_wake_feed_mock(voice_wake_t *w, bool detected);
bool voice_wake_feed_manual(voice_wake_t *w);
bool voice_wake_take(voice_wake_t *w);
const char *voice_wake_model_status(void);
