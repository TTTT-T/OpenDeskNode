#pragma once

#include "esp_err.h"

/*
 * Phase 2A audio self-test. Runs once at boot after the stock service is
 * up, and re-runs when the BOOT button is pressed.
 *
 * Sequence per run: codec bring-up, stimulus playback captured raw
 * (aec_off.wav + playback_reference.wav + mic0_mic1.wav), the same playback
 * captured through esp-sr AEC (aec_on.wav), device-side statistics, then a
 * serial WAV dump protocol for the host to reassemble. Afterwards the task
 * stays in a stability loop that keeps codecs + I2S + AEC active and logs
 * resource lines once per minute.
 */
esp_err_t audio_selftest_start(void);

/* Request a self-test re-run from the BOOT button handler. */
void audio_selftest_request_rerun(void);

/* Cycle output volume 70 <-> 0 (audible BOOT double-press evidence). */
void audio_selftest_toggle_volume(void);
