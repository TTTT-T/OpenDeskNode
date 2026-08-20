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

voice_wake_action_t voice_wake_handle_runtime(voice_wake_t *w, voice_wake_evt_t evt,
                                              uint32_t conversation_id)
{
    voice_wake_action_t act = { false, false, false };
    if (w == NULL) {
        return act;
    }
    if (evt == VOICE_WAKE_EVT_MANUAL) {
        voice_wake_feed_manual(w);
        act.counted_manual = true;
        act.start_talk = true;
        return act;
    }
    if (conversation_id != 0) {
        return act;
    }
    if (w->source != VOICE_WAKE_SRC_MOCK) {
        return act;
    }
    if (!voice_wake_feed_mock(w, true)) {
        return act;
    }
    voice_wake_take(w);
    act.counted_wake = true;
    act.start_talk = true;
    return act;
}

voice_wake_source_t voice_wake_source_from_config(void)
{
#if defined(CONFIG_VOICE_WAKE_SOURCE_MOCK) && CONFIG_VOICE_WAKE_SOURCE_MOCK
    return VOICE_WAKE_SRC_MOCK;
#else
    return VOICE_WAKE_SRC_NONE;
#endif
}

const char *voice_wake_model_status(void)
{
    return "WAKE MODEL PENDING";
}
