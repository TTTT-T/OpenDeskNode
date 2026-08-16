#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

/*
 * Phase 2A audio hardware bring-up for the Waveshare ESP32-S3-RLCD-4.2.
 *
 * Data path (16 kHz, PCM16, full duplex on I2S0):
 *   ES7210 ADC (MIC1, MIC3, MIC2 over TDM) -> I2S RX -> audio_hw_read()
 *   audio_hw_write() -> I2S TX (std slot) -> ES8311 DAC -> PA(GPIO46) -> speaker
 *
 * Captured channel order returned by audio_hw_read():
 *   mic0 = ES7210 MIC1 (TDM slot 0), ref = ES7210 MIC3 (TDM slot 1,
 *   wired on this board as the playback loopback reference), mic1 = ES7210
 *   MIC2 (TDM slot 2).
 */
#define AUDIO_HW_SAMPLE_RATE 16000

esp_err_t audio_hw_init(void);
esp_err_t audio_hw_input_enable(bool enable);
esp_err_t audio_hw_output_enable(bool enable);

/* Reads `samples` per channel and deinterleaves into mic0/ref/mic1. */
esp_err_t audio_hw_read(int16_t *mic0, int16_t *ref, int16_t *mic1, int samples);

/* Writes `samples` of mono PCM16 to the speaker path. */
esp_err_t audio_hw_write(const int16_t *pcm, int samples);

esp_err_t audio_hw_set_output_volume(int volume);

/* Register access used for bus probe evidence in the self-test logs. */
esp_err_t audio_hw_probe_registers(int *es7210_reset_reg, int *es8311_dac_reg);
