#include "voice_wake.h"

#include <stddef.h>

void voice_wake_init(voice_wake_t *w, voice_wake_source_t src)
{
    if (w == NULL) {
        return;
    }
    w->source = src;
    w->armed = true;
    w->pending = false;
    w->mock_hits = 0;
    w->manual_hits = 0;
}

void voice_wake_reset(voice_wake_t *w)
{
    if (w == NULL) {
        return;
    }
    w->armed = true;
    w->pending = false;
}

void voice_wake_arm(voice_wake_t *w)
{
    if (w == NULL) {
        return;
    }
    w->armed = true;
    w->pending = false;
}

void voice_wake_disarm(voice_wake_t *w)
{
    if (w == NULL) {
        return;
    }
    w->armed = false;
    w->pending = false;
}

bool voice_wake_feed_mock(voice_wake_t *w, bool detected)
{
    if (w == NULL || w->source != VOICE_WAKE_SRC_MOCK || !w->armed || !detected) {
        return false;
    }
    w->pending = true;
    w->mock_hits++;
    return true;
}

bool voice_wake_feed_manual(voice_wake_t *w)
{
    if (w == NULL) {
        return false;
    }
    w->manual_hits++;
    return true;
}

bool voice_wake_take(voice_wake_t *w)
{
    if (w == NULL || !w->pending) {
        return false;
    }
    w->pending = false;
    w->armed = false;
    return true;
}

const char *voice_wake_model_status(void)
{
    return "WAKE MODEL PENDING";
}
