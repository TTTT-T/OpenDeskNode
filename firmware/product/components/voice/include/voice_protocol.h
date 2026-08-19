#pragma once

#include <stddef.h>
#include <stdint.h>

#define VOICE_PROTOCOL_VERSION 0
#define VOICE_FRAME_MAGIC 0xA5
#define VOICE_HEADER_SIZE 16
#define VOICE_SAMPLE_RATE 16000
#define VOICE_FRAME_MS 20
#define VOICE_SAMPLES_PER_FRAME (VOICE_SAMPLE_RATE * VOICE_FRAME_MS / 1000)
#define VOICE_FRAME_BYTES (VOICE_SAMPLES_PER_FRAME * 2)
#define VOICE_WIRE_BYTES (VOICE_HEADER_SIZE + VOICE_FRAME_BYTES)
#define VOICE_FLAG_UTTERANCE_START 0x01
#define VOICE_FLAG_UTTERANCE_END 0x02
#define VOICE_CODEC_ID "pcm_s16le_16k_mono"
#define VOICE_TXQ_FRAMES 100
/* Congestion-window drop limit: VOICE_TXQ_DROP_LIMIT frames x VOICE_FRAME_MS
 * = 1.5 s of dropped audio inside the CURRENT utterance window. voice_txq_clear()
 * opens a fresh window (new utterance); dropped_total is a lifetime metric and
 * must never gate transport. */
#define VOICE_TXQ_DROP_LIMIT (1500 / VOICE_FRAME_MS)
#define VOICE_RXQ_FRAMES 400
#define VOICE_RXQ_SAMPLES (VOICE_RXQ_FRAMES * VOICE_SAMPLES_PER_FRAME)
/* C2 starting prebuffer only; 6 frames x 20 ms = 120 ms. C3 kept this value
 * and added a one-chunk fade-in; retune only with barge-in measurements. */
#define VOICE_RXQ_PREBUFFER_FRAMES 6
#define VOICE_RXQ_PREBUFFER_SAMPLES (VOICE_RXQ_PREBUFFER_FRAMES * VOICE_SAMPLES_PER_FRAME)

typedef struct {
    uint32_t conversation_id;
    uint32_t seq;
    uint32_t ts_ms;
    uint8_t flags;
    const uint8_t *pcm;
} voice_frame_view_t;

typedef struct {
    uint8_t frames[VOICE_TXQ_FRAMES][VOICE_WIRE_BYTES];
    uint16_t head;
    uint16_t count;
    /* Current congestion window: drops since the last voice_txq_clear(). */
    uint32_t dropped;
    /* Lifetime metric since boot; diagnostic only, never gates transport. */
    uint32_t dropped_total;
    uint32_t pushed;
    uint32_t popped;
    /* High-water mark of count since boot; diagnostic only. */
    uint16_t peak_count;
} voice_txq_t;

typedef struct {
    int16_t samples[VOICE_RXQ_SAMPLES];
    uint32_t head;
    uint32_t count;
    uint32_t dropped_frames;
    uint32_t pushed_frames;
    uint32_t popped_samples;
    uint32_t underrun;
    uint32_t peak_count;
} voice_rxq_t;

int voice_pack_frame(uint8_t *out, size_t out_len, uint32_t conversation_id,
                     uint32_t seq, uint32_t ts_ms, uint8_t flags,
                     const int16_t *pcm, int samples);
int voice_unpack_frame(const uint8_t *in, size_t in_len, voice_frame_view_t *view);
void voice_txq_init(voice_txq_t *q);
int voice_txq_push(voice_txq_t *q, const uint8_t *frame);
int voice_txq_pop(voice_txq_t *q, uint8_t *frame);
void voice_txq_clear(voice_txq_t *q);
int voice_txq_count(const voice_txq_t *q);
void voice_rxq_init(voice_rxq_t *q);
int voice_rxq_push_pcm(voice_rxq_t *q, const int16_t *pcm, int samples);
int voice_rxq_pop_pcm(voice_rxq_t *q, int16_t *pcm, int samples);
void voice_rxq_clear(voice_rxq_t *q);
int voice_rxq_count(const voice_rxq_t *q);
int voice_rxq_ready(const voice_rxq_t *q);
int voice_hello_json(char *out, size_t out_len, const char *device_id,
                     const char *fw_version);
int voice_control_json(char *out, size_t out_len, const char *type,
                       uint32_t conversation_id, const char *reason);
