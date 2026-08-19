#pragma once

#include "esp_err.h"

/*
 * Phase 2A audio self-test kept as an on-demand diagnostic. It does not own
 * I2S in the product runtime; Voice Runtime is the default RX/TX owner.
 * Sequence per run is unchanged: codec bring-up, stimulus playback captured
 * raw (aec_off.wav + playback_reference.wav + mic0_mic1.wav), the same
 * playback captured through esp-sr AEC (aec_on.wav), device-side statistics,
 * then a serial WAV dump protocol.
 */
esp_err_t audio_selftest_start(void);

void audio_selftest_request_rerun(void);

/* Cycle output volume 70 <-> 0 (audible BOOT double-press evidence). */
void audio_selftest_toggle_volume(void);
