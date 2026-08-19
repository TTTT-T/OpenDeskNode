#include <stdio.h>
#include <string.h>

#include "voice_protocol.h"

static int failures;

#define CHECK_TRUE(cond)                                                       \
    do {                                                                       \
        if (!(cond)) {                                                         \
            ++failures;                                                        \
            printf("FAIL %s:%d\n", __func__, __LINE__);                        \
        }                                                                      \
    } while (0)

static void test_frame_roundtrip(void)
{
    int16_t pcm[VOICE_SAMPLES_PER_FRAME];
    for (int i = 0; i < VOICE_SAMPLES_PER_FRAME; i++) {
        pcm[i] = (int16_t)(i - 160);
    }
    uint8_t wire[VOICE_WIRE_BYTES];
    CHECK_TRUE(voice_pack_frame(wire, sizeof(wire), 9, 4, 80, VOICE_FLAG_UTTERANCE_START,
                                pcm, VOICE_SAMPLES_PER_FRAME) == VOICE_WIRE_BYTES);
    voice_frame_view_t view;
    CHECK_TRUE(voice_unpack_frame(wire, sizeof(wire), &view) == 0);
    CHECK_TRUE(view.conversation_id == 9);
    CHECK_TRUE(view.seq == 4);
    CHECK_TRUE(view.ts_ms == 80);
    CHECK_TRUE(view.flags == VOICE_FLAG_UTTERANCE_START);
    CHECK_TRUE(memcmp(view.pcm, pcm, VOICE_FRAME_BYTES) == 0);
}

static void test_rejects_short_frame(void)
{
    uint8_t wire[VOICE_WIRE_BYTES];
    int16_t pcm[VOICE_SAMPLES_PER_FRAME] = { 0 };
    CHECK_TRUE(voice_pack_frame(wire, sizeof(wire), 1, 0, 0, 0, pcm, 10) < 0);
    CHECK_TRUE(voice_unpack_frame(wire, VOICE_HEADER_SIZE, NULL) < 0);
}

static void test_queue_drop_oldest(void)
{
    voice_txq_t q;
    voice_txq_init(&q);
    uint8_t frame[VOICE_WIRE_BYTES];
    int16_t pcm[VOICE_SAMPLES_PER_FRAME] = { 0 };
    for (uint32_t seq = 0; seq < VOICE_TXQ_FRAMES + 3; seq++) {
        pcm[0] = (int16_t)seq;
        voice_pack_frame(frame, sizeof(frame), 1, seq, seq, 0, pcm, VOICE_SAMPLES_PER_FRAME);
        voice_txq_push(&q, frame);
    }
    CHECK_TRUE(voice_txq_count(&q) == VOICE_TXQ_FRAMES);
    CHECK_TRUE(q.dropped == 3);
    uint8_t out[VOICE_WIRE_BYTES];
    CHECK_TRUE(voice_txq_pop(&q, out) == VOICE_WIRE_BYTES);
    voice_frame_view_t view;
    CHECK_TRUE(voice_unpack_frame(out, sizeof(out), &view) == 0);
    CHECK_TRUE(view.seq == 3);
}

static void test_queue_drop_limit(void)
{
    voice_txq_t q;
    voice_txq_init(&q);
    uint8_t frame[VOICE_WIRE_BYTES] = { 0 };
    int rc = 0;
    for (int i = 0; i < VOICE_TXQ_FRAMES + VOICE_TXQ_DROP_LIMIT - 1; i++) {
        rc = voice_txq_push(&q, frame);
    }
    CHECK_TRUE(rc == 0);
    rc = voice_txq_push(&q, frame);
    CHECK_TRUE(rc == -2);
    CHECK_TRUE(q.dropped == VOICE_TXQ_DROP_LIMIT);
    CHECK_TRUE(q.dropped_total >= VOICE_TXQ_DROP_LIMIT);
    CHECK_TRUE(VOICE_TXQ_DROP_LIMIT * VOICE_FRAME_MS == 1500);
}

/* A drop-heavy utterance must not poison any later utterance: the transport
 * error threshold is per congestion window, not per lifetime. */
static void test_drop_window_resets_between_utterances(void)
{
    voice_txq_t q;
    voice_txq_init(&q);
    uint8_t frame[VOICE_WIRE_BYTES] = { 0 };
    int rc = 0;
    for (int i = 0; i < VOICE_TXQ_FRAMES + VOICE_TXQ_DROP_LIMIT; i++) {
        rc = voice_txq_push(&q, frame);
    }
    CHECK_TRUE(rc == -2);
    CHECK_TRUE(q.dropped >= VOICE_TXQ_DROP_LIMIT);
    const uint32_t total_first = q.dropped_total;

    voice_txq_clear(&q);
    CHECK_TRUE(q.dropped == 0);
    CHECK_TRUE(q.dropped_total == total_first);
    CHECK_TRUE(voice_txq_count(&q) == 0);

    for (int i = 0; i < VOICE_TXQ_FRAMES + 3; i++) {
        rc = voice_txq_push(&q, frame);
    }
    CHECK_TRUE(rc == 0);
    CHECK_TRUE(q.dropped == 3);
    CHECK_TRUE(q.dropped_total >= total_first + 3);

    voice_txq_clear(&q);
    for (int i = 0; i < VOICE_TXQ_FRAMES + VOICE_TXQ_DROP_LIMIT; i++) {
        rc = voice_txq_push(&q, frame);
    }
    CHECK_TRUE(rc == -2);
}

static void test_rxq_push_pop_and_wrap(void)
{
    static voice_rxq_t q;
    voice_rxq_init(&q);
    int16_t frame[VOICE_SAMPLES_PER_FRAME];
    for (int i = 0; i < VOICE_SAMPLES_PER_FRAME; i++) {
        frame[i] = (int16_t)(i + 1);
    }
    CHECK_TRUE(voice_rxq_push_pcm(&q, frame, VOICE_SAMPLES_PER_FRAME) == 0);
    CHECK_TRUE(voice_rxq_count(&q) == VOICE_SAMPLES_PER_FRAME);
    CHECK_TRUE(!voice_rxq_ready(&q));

    int16_t out[256];
    CHECK_TRUE(voice_rxq_pop_pcm(&q, out, 256) == 256);
    CHECK_TRUE(out[0] == 1);
    CHECK_TRUE(out[255] == 256);
    CHECK_TRUE(voice_rxq_count(&q) == VOICE_SAMPLES_PER_FRAME - 256);

    int16_t rest[VOICE_SAMPLES_PER_FRAME];
    const int n = voice_rxq_pop_pcm(&q, rest, VOICE_SAMPLES_PER_FRAME);
    CHECK_TRUE(n == VOICE_SAMPLES_PER_FRAME - 256);
    CHECK_TRUE(rest[0] == 257);
    CHECK_TRUE(voice_rxq_count(&q) == 0);
    CHECK_TRUE(voice_rxq_pop_pcm(&q, rest, 16) == 0);
}

static void test_rxq_prebuffer_and_drop_newest(void)
{
    static voice_rxq_t q;
    voice_rxq_init(&q);
    int16_t frame[VOICE_SAMPLES_PER_FRAME];
    for (uint32_t seq = 0; seq < VOICE_RXQ_PREBUFFER_FRAMES; seq++) {
        frame[0] = (int16_t)seq;
        voice_rxq_push_pcm(&q, frame, VOICE_SAMPLES_PER_FRAME);
    }
    CHECK_TRUE(voice_rxq_ready(&q));
    CHECK_TRUE(voice_rxq_count(&q) == VOICE_RXQ_PREBUFFER_SAMPLES);

    for (uint32_t seq = VOICE_RXQ_PREBUFFER_FRAMES; seq < VOICE_RXQ_FRAMES; seq++) {
        frame[0] = (int16_t)seq;
        CHECK_TRUE(voice_rxq_push_pcm(&q, frame, VOICE_SAMPLES_PER_FRAME) == 0);
    }
    CHECK_TRUE(voice_rxq_count(&q) == VOICE_RXQ_SAMPLES);

    frame[0] = 2000;
    CHECK_TRUE(voice_rxq_push_pcm(&q, frame, VOICE_SAMPLES_PER_FRAME) == -2);
    CHECK_TRUE(q.dropped_frames >= 1);
    CHECK_TRUE(voice_rxq_count(&q) == VOICE_RXQ_SAMPLES);

    int16_t out[VOICE_SAMPLES_PER_FRAME];
    CHECK_TRUE(voice_rxq_pop_pcm(&q, out, VOICE_SAMPLES_PER_FRAME) == VOICE_SAMPLES_PER_FRAME);
    CHECK_TRUE(out[0] == 0);

    voice_rxq_clear(&q);
    CHECK_TRUE(voice_rxq_count(&q) == 0);
    CHECK_TRUE(!voice_rxq_ready(&q));
    CHECK_TRUE(q.dropped_frames >= 1);
}

static void test_hello_json(void)
{
    char buf[256];
    CHECK_TRUE(voice_hello_json(buf, sizeof(buf), "opendesk-a", "phase-2c-c1") > 0);
    CHECK_TRUE(strstr(buf, "\"type\":\"hello\"") != NULL);
    CHECK_TRUE(strstr(buf, "pcm_s16le_16k_mono") != NULL);
    CHECK_TRUE(strstr(buf, "appendAudio") == NULL);
}

int main(void)
{
    test_frame_roundtrip();
    test_rejects_short_frame();
    test_queue_drop_oldest();
    test_queue_drop_limit();
    test_drop_window_resets_between_utterances();
    test_rxq_push_pop_and_wrap();
    test_rxq_prebuffer_and_drop_newest();
    test_hello_json();
    if (failures) {
        printf("VOICE_PROTOCOL_HOST_TESTS_FAILED %d\n", failures);
        return 1;
    }
    printf("VOICE_PROTOCOL_HOST_TESTS_OK\n");
    return 0;
}
