#include "voice_protocol.h"

#include <stdio.h>
#include <string.h>

static uint32_t read_le32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static void write_le32(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)(value & 0xff);
    p[1] = (uint8_t)((value >> 8) & 0xff);
    p[2] = (uint8_t)((value >> 16) & 0xff);
    p[3] = (uint8_t)((value >> 24) & 0xff);
}

int voice_pack_frame(uint8_t *out, size_t out_len, uint32_t conversation_id,
                     uint32_t seq, uint32_t ts_ms, uint8_t flags,
                     const int16_t *pcm, int samples)
{
    if (out == NULL || pcm == NULL || samples != VOICE_SAMPLES_PER_FRAME ||
        out_len < VOICE_WIRE_BYTES) {
        return -1;
    }
    out[0] = VOICE_FRAME_MAGIC;
    out[1] = VOICE_PROTOCOL_VERSION;
    out[2] = flags;
    out[3] = 0;
    write_le32(out + 4, conversation_id);
    write_le32(out + 8, seq);
    write_le32(out + 12, ts_ms);
    memcpy(out + VOICE_HEADER_SIZE, pcm, VOICE_FRAME_BYTES);
    return VOICE_WIRE_BYTES;
}

int voice_unpack_frame(const uint8_t *in, size_t in_len, voice_frame_view_t *view)
{
    if (in == NULL || view == NULL || in_len != VOICE_WIRE_BYTES) {
        return -1;
    }
    if (in[0] != VOICE_FRAME_MAGIC || in[1] != VOICE_PROTOCOL_VERSION) {
        return -1;
    }
    view->flags = in[2];
    view->conversation_id = read_le32(in + 4);
    view->seq = read_le32(in + 8);
    view->ts_ms = read_le32(in + 12);
    view->pcm = in + VOICE_HEADER_SIZE;
    return 0;
}

void voice_txq_init(voice_txq_t *q)
{
    memset(q, 0, sizeof(*q));
}

int voice_txq_push(voice_txq_t *q, const uint8_t *frame)
{
    if (q == NULL || frame == NULL) {
        return -1;
    }
    if (q->count == VOICE_TXQ_FRAMES) {
        q->head = (uint16_t)((q->head + 1) % VOICE_TXQ_FRAMES);
        q->count--;
        q->dropped++;
        q->dropped_total++;
    }
    const uint16_t tail = (uint16_t)((q->head + q->count) % VOICE_TXQ_FRAMES);
    memcpy(q->frames[tail], frame, VOICE_WIRE_BYTES);
    q->count++;
    if (q->count > q->peak_count) {
        q->peak_count = q->count;
    }
    q->pushed++;
    return q->dropped >= VOICE_TXQ_DROP_LIMIT ? -2 : 0;
}

int voice_txq_pop(voice_txq_t *q, uint8_t *frame)
{
    if (q == NULL || frame == NULL || q->count == 0) {
        return 0;
    }
    memcpy(frame, q->frames[q->head], VOICE_WIRE_BYTES);
    q->head = (uint16_t)((q->head + 1) % VOICE_TXQ_FRAMES);
    q->count--;
    q->popped++;
    return VOICE_WIRE_BYTES;
}

void voice_txq_clear(voice_txq_t *q)
{
    if (q == NULL) {
        return;
    }
    q->head = 0;
    q->count = 0;
    q->dropped = 0;
}

int voice_txq_count(const voice_txq_t *q)
{
    return q != NULL ? (int)q->count : 0;
}

void voice_rxq_init(voice_rxq_t *q)
{
    if (q == NULL) {
        return;
    }
    memset(q, 0, sizeof(*q));
}

int voice_rxq_push_pcm(voice_rxq_t *q, const int16_t *pcm, int samples)
{
    if (q == NULL || pcm == NULL || samples <= 0) {
        return -1;
    }
    /* Drop-newest: keep already-queued playback contiguous. Realtime can burst
     * several seconds faster than the speaker; skipping the tail is better than
     * deleting the next samples to play. */
    if ((int)q->count + samples > VOICE_RXQ_SAMPLES) {
        q->dropped_frames += (uint32_t)((samples + VOICE_SAMPLES_PER_FRAME - 1) /
                                        VOICE_SAMPLES_PER_FRAME);
        return -2;
    }
    int tail = ((int)q->head + (int)q->count) % VOICE_RXQ_SAMPLES;
    int first = VOICE_RXQ_SAMPLES - tail;
    if (samples <= first) {
        memcpy(q->samples + tail, pcm, (size_t)samples * sizeof(int16_t));
    } else {
        memcpy(q->samples + tail, pcm, (size_t)first * sizeof(int16_t));
        memcpy(q->samples, pcm + first, (size_t)(samples - first) * sizeof(int16_t));
    }
    q->count += (uint32_t)samples;
    if (q->count > q->peak_count) {
        q->peak_count = q->count;
    }
    q->pushed_frames++;
    return 0;
}

int voice_rxq_pop_pcm(voice_rxq_t *q, int16_t *pcm, int samples)
{
    if (q == NULL || pcm == NULL || samples <= 0 || q->count == 0) {
        return 0;
    }
    const int n = samples < (int)q->count ? samples : (int)q->count;
    int first = VOICE_RXQ_SAMPLES - (int)q->head;
    if (n <= first) {
        memcpy(pcm, q->samples + q->head, (size_t)n * sizeof(int16_t));
    } else {
        memcpy(pcm, q->samples + q->head, (size_t)first * sizeof(int16_t));
        memcpy(pcm + first, q->samples, (size_t)(n - first) * sizeof(int16_t));
    }
    q->head = (q->head + (uint32_t)n) % VOICE_RXQ_SAMPLES;
    q->count -= (uint32_t)n;
    q->popped_samples += (uint32_t)n;
    return n;
}

void voice_rxq_clear(voice_rxq_t *q)
{
    if (q == NULL) {
        return;
    }
    q->head = 0;
    q->count = 0;
}

int voice_rxq_count(const voice_rxq_t *q)
{
    return q != NULL ? (int)q->count : 0;
}

int voice_rxq_ready(const voice_rxq_t *q)
{
    return q != NULL && q->count >= VOICE_RXQ_PREBUFFER_SAMPLES;
}

int voice_hello_json(char *out, size_t out_len, const char *device_id,
                     const char *fw_version)
{
    if (out == NULL || device_id == NULL || fw_version == NULL) {
        return -1;
    }
    return snprintf(
        out, out_len,
        "{\"type\":\"hello\",\"protocol\":%d,\"device_id\":\"%s\","
        "\"fw_version\":\"%s\",\"audio\":{\"sample_rate\":%d,\"channels\":1,"
        "\"bits\":16,\"frame_ms\":%d,\"codec\":\"%s\"}}",
        VOICE_PROTOCOL_VERSION, device_id, fw_version, VOICE_SAMPLE_RATE,
        VOICE_FRAME_MS, VOICE_CODEC_ID);
}

int voice_control_json(char *out, size_t out_len, const char *type,
                       uint32_t conversation_id, const char *reason)
{
    if (out == NULL || type == NULL) {
        return -1;
    }
    if (reason != NULL && reason[0] != '\0') {
        if (conversation_id != 0) {
            return snprintf(out, out_len,
                            "{\"type\":\"%s\",\"conversation_id\":%lu,\"reason\":\"%s\"}",
                            type, (unsigned long)conversation_id, reason);
        }
        return snprintf(out, out_len, "{\"type\":\"%s\",\"reason\":\"%s\"}", type,
                        reason);
    }
    if (conversation_id != 0) {
        return snprintf(out, out_len, "{\"type\":\"%s\",\"conversation_id\":%lu}",
                        type, (unsigned long)conversation_id);
    }
    return snprintf(out, out_len, "{\"type\":\"%s\"}", type);
}
