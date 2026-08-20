#include "voice_vad.h"

#include <stddef.h>

void voice_vad_init(voice_vad_t *v)
{
    voice_vad_reset(v);
}

void voice_vad_reset(voice_vad_t *v)
{
    if (v == NULL) {
        return;
    }
    v->onset = 0;
    v->last_abs = 0;
    v->floor_abs = 0;
}

uint32_t voice_pcm_mean_abs(const int16_t *pcm, int samples)
{
    if (pcm == NULL || samples <= 0) {
        return 0;
    }
    uint32_t acc = 0;
    for (int i = 0; i < samples; i++) {
        const int32_t s = pcm[i];
        acc += (uint32_t)(s < 0 ? -s : s);
    }
    return acc / (uint32_t)samples;
}

static void vad_learn(voice_vad_t *v, uint32_t mag)
{
    if (v->floor_abs == 0) {
        v->floor_abs = mag == 0 ? 1 : mag;
    } else {
        v->floor_abs = v->floor_abs - (v->floor_abs >> 3) + (mag >> 3);
    }
    v->onset = 0;
}

bool voice_vad_feed(voice_vad_t *v, uint32_t residual_abs, uint32_t play_abs,
                    bool learn_only)
{
    (void)play_abs;
    if (v == NULL) {
        return false;
    }
    v->last_abs = residual_abs;
    if (learn_only) {
        vad_learn(v, residual_abs);
        return false;
    }
    uint32_t thresh = VOICE_VAD_ABS_THRESH;
    const uint32_t adapted = v->floor_abs * VOICE_VAD_FLOOR_RATIO;
    if (adapted > thresh) {
        thresh = adapted;
    }
    if (residual_abs >= thresh) {
        if (v->onset < VOICE_VAD_ONSET_FRAMES) {
            v->onset++;
        }
        return v->onset >= VOICE_VAD_ONSET_FRAMES;
    }
    vad_learn(v, residual_abs);
    return false;
}

bool voice_barge_should_stop(bool playing, bool holdoff_ok, bool speech)
{
    return playing && holdoff_ok && speech;
}

bool voice_followup_holdoff_ok(int64_t now_us, int64_t listen_start_us)
{
    if (listen_start_us <= 0 || now_us < listen_start_us) {
        return false;
    }
    return (now_us - listen_start_us) >= (int64_t)VOICE_FOLLOWUP_HOLDOFF_MS * 1000;
}

bool voice_followup_expired(int64_t now_us, int64_t listen_start_us)
{
    if (listen_start_us <= 0 || now_us < listen_start_us) {
        return false;
    }
    return (now_us - listen_start_us) >= (int64_t)VOICE_FOLLOWUP_MS * 1000;
}

bool voice_followup_should_listen(bool listening, bool playing, bool speaking,
                                  uint32_t conversation_id)
{
    return listening && !playing && !speaking && conversation_id != 0;
}

bool voice_followup_should_trigger(bool listening, bool playing, bool speaking,
                                   uint32_t conversation_id, bool holdoff_ok,
                                   bool speech)
{
    return voice_followup_should_listen(listening, playing, speaking, conversation_id) &&
           holdoff_ok && speech;
}

bool voice_idle_should_trigger(bool helloed, bool playing, bool speaking,
                               uint32_t conversation_id, bool holdoff_ok, bool speech)
{
    return helloed && conversation_id == 0 && !playing && !speaking && holdoff_ok && speech;
}
