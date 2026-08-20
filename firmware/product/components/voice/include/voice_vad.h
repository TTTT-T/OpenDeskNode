#pragma once

#include <stdbool.h>
#include <stdint.h>

#define VOICE_VAD_ABS_THRESH 800
#define VOICE_VAD_ONSET_FRAMES 4
#define VOICE_BARGE_HOLDOFF_MS 400
#define VOICE_BARGE_POST_SPEECH_MS 400
#define VOICE_VAD_FLOOR_RATIO 3
#define VOICE_FOLLOWUP_MS 12000
#define VOICE_FOLLOWUP_HOLDOFF_MS 400
#define VOICE_FOLLOWUP_WAIT_REPLY_MS 2500

typedef struct {
    uint32_t onset;
    uint32_t last_abs;
    uint32_t floor_abs;
} voice_vad_t;

void voice_vad_init(voice_vad_t *v);
void voice_vad_reset(voice_vad_t *v);
uint32_t voice_pcm_mean_abs(const int16_t *pcm, int samples);
bool voice_vad_feed(voice_vad_t *v, uint32_t residual_abs, uint32_t play_abs,
                    bool learn_only);
bool voice_barge_should_stop(bool playing, bool holdoff_ok, bool speech);
