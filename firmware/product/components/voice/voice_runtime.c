#include "voice_runtime.h"

#include <stdio.h>
#include <string.h>

#include "audio_hw.h"
#include "audio_owner.h"
#include "cJSON.h"
#include "esp_aec.h"
#include "esp_check.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "network.h"
#include "voice_protocol.h"
#include "voice_recovery.h"
#include "voice_vad.h"
#include "voice_wake.h"

static const char *TAG = "voice";

typedef enum {
    PLAY_IDLE = 0,
    PLAY_BUFFERING,
    PLAY_ACTIVE,
    PLAY_DRAINING,
} play_state_t;

#define AUDIO_TASK_STACK 20480
#define NET_TASK_STACK 8192
#define AUDIO_TASK_PRIO 5
#define NET_TASK_PRIO 4
#define TALK_BIT BIT0
#define WS_CONNECTED_BIT BIT1
#define HELLO_OK_BIT BIT2
#define OPENED_BIT BIT3
#define REJECT_BIT BIT4
#define WS_CLOSED_BIT BIT5
#define END_BIT BIT6

typedef struct {
    EventGroupHandle_t events;
    SemaphoreHandle_t mu;
    voice_txq_t *txq;
    voice_rxq_t *rxq;
    esp_websocket_client_handle_t ws;
    volatile uint32_t conversation_id;
    uint32_t seq;
    volatile bool speaking;
    volatile bool helloed;
    volatile play_state_t play;
    volatile bool accept_downlink;
    volatile bool barge_pending;
    volatile bool stop_play;
    volatile bool fade_in;
    volatile bool listen_followup;
    volatile bool await_reply;
    volatile int vol_req;
    uint32_t turn_index;
    voice_vad_t vad;
    int32_t rx_seq_seen;
    uint32_t frames_sent;
    uint32_t bytes_sent;
    uint32_t frames_rx;
    uint32_t frames_play;
    uint32_t samples_play;
    uint32_t play_underrun;
    uint32_t play_peak;
    uint32_t rx_drop_busy;
    uint32_t rx_drop_barge;
    uint32_t residual_peak;
    uint32_t overlap_residual;
    uint32_t overlap_play;
    uint32_t rx_drop_cid;
    uint32_t rx_dup;
    uint32_t rx_gap;
    uint32_t rx_reorder;
    uint32_t ws_reconnects;
    uint32_t conversation_creates;
    uint32_t session_invalidations;
    uint32_t followup_starts;
    uint32_t followup_vad_hits;
    uint32_t followup_timeouts;
    uint32_t interrupts_sent;
    uint32_t playback_starts;
    uint32_t playback_ends;
    uint32_t audio_yields;
    uint32_t audio_reacquires;
    uint32_t wifi_losses;
    uint32_t hello_ok_count;
    int64_t talk_req_us;
    int64_t speech_start_us;
    int64_t speech_end_us;
    int64_t first_frame_us;
    int64_t first_rx_us;
    int64_t play_start_us;
    int64_t listen_start_us;
    voice_recovery_t recovery;
    voice_wake_t wake;
} voice_rt_t;

static voice_rt_t s_rt;
static StaticEventGroup_t s_event_buf;
static StaticSemaphore_t s_mu_buf;

static void log_metrics(const char *label)
{
    multi_heap_info_t internal = { 0 };
    heap_caps_get_info(&internal, MALLOC_CAP_INTERNAL);
    const size_t ps_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    int qdepth = 0;
    int rxdepth = 0;
    uint32_t dropped = 0;
    uint32_t dropped_total = 0;
    uint32_t qpeak = 0;
    uint32_t rx_drop = 0;
    uint32_t rx_peak = 0;
    if (xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(20)) == pdTRUE) {
        qdepth = voice_txq_count(s_rt.txq);
        rxdepth = voice_rxq_count(s_rt.rxq);
        if (s_rt.txq != NULL) {
            dropped = s_rt.txq->dropped;
            dropped_total = s_rt.txq->dropped_total;
            qpeak = s_rt.txq->peak_count;
        }
        if (s_rt.rxq != NULL) {
            rx_drop = s_rt.rxq->dropped_frames;
            rx_peak = s_rt.rxq->peak_count;
        }
        xSemaphoreGive(s_rt.mu);
    }
    printf("PHASE2C_C1 %s conn=%d hello=%d cid=%lu frames=%lu bytes=%lu drop=%lu "
           "drop_total=%lu q=%d qpeak=%lu heap=%u psram=%u\n",
           label,
           s_rt.ws != NULL && esp_websocket_client_is_connected(s_rt.ws),
           s_rt.helloed, (unsigned long)s_rt.conversation_id,
           (unsigned long)s_rt.frames_sent, (unsigned long)s_rt.bytes_sent,
           (unsigned long)dropped, (unsigned long)dropped_total, qdepth,
           (unsigned long)qpeak, (unsigned)internal.total_free_bytes,
           (unsigned)ps_free);
    printf("PHASE2C_C2 %s play=%d rxq=%d rx_drop=%lu rx_peak=%lu frames_rx=%lu "
           "frames_play=%lu underrun=%lu peak=%lu busy_drop=%lu\n",
           label, (int)s_rt.play, rxdepth, (unsigned long)rx_drop,
           (unsigned long)rx_peak, (unsigned long)s_rt.frames_rx,
           (unsigned long)(s_rt.samples_play / VOICE_SAMPLES_PER_FRAME),
           (unsigned long)s_rt.play_underrun,
           (unsigned long)s_rt.play_peak, (unsigned long)s_rt.rx_drop_busy);
    printf("PHASE2C_C3 %s barge_pending=%d accept_rx=%d barge_drop=%lu residual=%lu "
           "play_rms=%lu\n",
           label, s_rt.barge_pending, s_rt.accept_downlink,
           (unsigned long)s_rt.rx_drop_barge, (unsigned long)s_rt.overlap_residual,
           (unsigned long)s_rt.overlap_play);
    printf("PHASE2C_C4 %s listen=%d await=%d turn=%lu cid=%lu follow_start=%lu "
           "follow_vad=%lu follow_to=%lu\n",
           label, s_rt.listen_followup, s_rt.await_reply,
           (unsigned long)s_rt.turn_index, (unsigned long)s_rt.conversation_id,
           (unsigned long)s_rt.followup_starts, (unsigned long)s_rt.followup_vad_hits,
           (unsigned long)s_rt.followup_timeouts);
    printf("PHASE2C_METRICS ws_reconnects=%lu conv_create=%lu invalid=%lu "
           "up_frames=%lu up_bytes=%lu up_drop=%lu down_frames=%lu down_drop=%lu "
           "play_start=%lu play_end=%lu underrun=%lu gap=%lu dup=%lu reorder=%lu "
           "interrupts=%lu follow_start=%lu follow_vad=%lu follow_to=%lu turns=%lu "
           "yield=%lu reacquire=%lu wifi_loss=%lu hello_ok=%lu heap=%u psram=%u "
           "audio=%d net=%d\n",
           (unsigned long)s_rt.ws_reconnects, (unsigned long)s_rt.conversation_creates,
           (unsigned long)s_rt.session_invalidations, (unsigned long)s_rt.frames_sent,
           (unsigned long)s_rt.bytes_sent, (unsigned long)dropped,
           (unsigned long)s_rt.frames_rx, (unsigned long)rx_drop,
           (unsigned long)s_rt.playback_starts, (unsigned long)s_rt.playback_ends,
           (unsigned long)s_rt.play_underrun, (unsigned long)s_rt.rx_gap,
           (unsigned long)s_rt.rx_dup, (unsigned long)s_rt.rx_reorder,
           (unsigned long)s_rt.interrupts_sent, (unsigned long)s_rt.followup_starts,
           (unsigned long)s_rt.followup_vad_hits, (unsigned long)s_rt.followup_timeouts,
           (unsigned long)s_rt.turn_index, (unsigned long)s_rt.audio_yields,
           (unsigned long)s_rt.audio_reacquires, (unsigned long)s_rt.wifi_losses,
           (unsigned long)s_rt.hello_ok_count, (unsigned)internal.total_free_bytes,
           (unsigned)ps_free, 1, 1);
    fflush(stdout);
}

static void fade_from_zero(int16_t *pcm, int n)
{
    for (int i = 0; i < n; i++) {
        pcm[i] = (int16_t)((int32_t)pcm[i] * i / n);
    }
}

static uint32_t pcm_peak(const int16_t *pcm, int samples)
{
    uint32_t peak = 0;
    for (int i = 0; i < samples; i++) {
        const int32_t v = pcm[i] < 0 ? -(int32_t)pcm[i] : (int32_t)pcm[i];
        if ((uint32_t)v > peak) {
            peak = (uint32_t)v;
        }
    }
    return peak;
}

static void reset_playback_locked(void)
{
    if (s_rt.rxq != NULL) {
        voice_rxq_clear(s_rt.rxq);
    }
    s_rt.play = PLAY_IDLE;
    s_rt.rx_seq_seen = -1;
    s_rt.fade_in = false;
    voice_vad_reset(&s_rt.vad);
}

static void reset_playback(void)
{
    if (s_rt.mu != NULL && xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(20)) == pdTRUE) {
        reset_playback_locked();
        xSemaphoreGive(s_rt.mu);
        return;
    }
    reset_playback_locked();
}

static void begin_playback(void)
{
    if (s_rt.mu != NULL && xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(20)) == pdTRUE) {
        voice_rxq_clear(s_rt.rxq);
        xSemaphoreGive(s_rt.mu);
    }
    s_rt.play = PLAY_BUFFERING;
    s_rt.accept_downlink = true;
    s_rt.fade_in = true;
    s_rt.rx_seq_seen = -1;
    s_rt.residual_peak = 0;
    s_rt.overlap_residual = 0;
    s_rt.overlap_play = 0;
    voice_vad_reset(&s_rt.vad);
    s_rt.frames_rx = 0;
    s_rt.frames_play = 0;
    s_rt.samples_play = 0;
    s_rt.play_underrun = 0;
    s_rt.play_peak = 0;
    s_rt.first_rx_us = 0;
    s_rt.play_start_us = esp_timer_get_time();
    s_rt.vol_req = 70;
    s_rt.listen_followup = false;
    s_rt.await_reply = false;
    s_rt.playback_starts++;
    printf("PHASE2C_C2 playback_start cid=%lu\n", (unsigned long)s_rt.conversation_id);
    fflush(stdout);
}

static void start_followup_listen(const char *why)
{
    if (s_rt.conversation_id == 0 || s_rt.speaking || s_rt.barge_pending) {
        return;
    }
    s_rt.listen_followup = true;
    s_rt.await_reply = false;
    s_rt.listen_start_us = esp_timer_get_time();
    s_rt.followup_starts++;
    voice_vad_reset(&s_rt.vad);
    printf("PHASE2C_C4 listen_start why=%s cid=%lu turn=%lu\n", why,
           (unsigned long)s_rt.conversation_id, (unsigned long)s_rt.turn_index);
    fflush(stdout);
}

static void finish_playback(const char *why)
{
    const int64_t now = esp_timer_get_time();
    s_rt.frames_play = s_rt.samples_play / VOICE_SAMPLES_PER_FRAME;
    printf("PHASE2C_C2 play_done why=%s cid=%lu frames_rx=%lu frames_play=%lu "
           "underrun=%lu drop=%lu qpeak=%lu peak=%lu first_audio_ms=%ld play_ms=%ld "
           "gap=%lu dup=%lu reorder=%lu\n",
           why, (unsigned long)s_rt.conversation_id,
           (unsigned long)s_rt.frames_rx, (unsigned long)s_rt.frames_play,
           (unsigned long)s_rt.play_underrun,
           (unsigned long)(s_rt.rxq != NULL ? s_rt.rxq->dropped_frames : 0),
           (unsigned long)(s_rt.rxq != NULL ? s_rt.rxq->peak_count : 0),
           (unsigned long)s_rt.play_peak,
           s_rt.first_rx_us > 0 && s_rt.speech_end_us > 0
               ? (long)((s_rt.first_rx_us - s_rt.speech_end_us) / 1000)
               : -1,
           s_rt.play_start_us > 0 ? (long)((now - s_rt.play_start_us) / 1000) : -1,
            (unsigned long)s_rt.rx_gap, (unsigned long)s_rt.rx_dup,
            (unsigned long)s_rt.rx_reorder);
    printf("PHASE2C_C3 play_done why=%s residual_peak=%lu residual=%lu play_rms=%lu "
           "barge_drop=%lu\n",
           why, (unsigned long)s_rt.residual_peak,
           (unsigned long)s_rt.overlap_residual, (unsigned long)s_rt.overlap_play,
           (unsigned long)s_rt.rx_drop_barge);
    fflush(stdout);
    s_rt.playback_ends++;
    reset_playback();
    if (strcmp(why, "drained") == 0) {
        start_followup_listen("drained");
    } else {
        s_rt.listen_followup = false;
    }
}

static void invalidate_session(const char *why, voice_fault_t fault)
{
    s_rt.speaking = false;
    s_rt.listen_followup = false;
    s_rt.await_reply = false;
    s_rt.turn_index = 0;
    if (s_rt.conversation_id != 0 || s_rt.play != PLAY_IDLE || s_rt.helloed) {
        s_rt.session_invalidations++;
    }
    s_rt.conversation_id = 0;
    if (!voice_recovery_keeps_hello(fault)) {
        s_rt.helloed = false;
    }
    if (s_rt.play != PLAY_IDLE) {
        finish_playback(why);
    } else {
        reset_playback();
    }
    if (s_rt.mu != NULL && xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(20)) == pdTRUE) {
        if (s_rt.txq != NULL) {
            voice_txq_clear(s_rt.txq);
        }
        if (s_rt.rxq != NULL) {
            voice_rxq_clear(s_rt.rxq);
        }
        xSemaphoreGive(s_rt.mu);
    }
    voice_vad_reset(&s_rt.vad);
    voice_recovery_on_fault(&s_rt.recovery, fault);
    voice_wake_arm(&s_rt.wake);
    printf("PHASE2C_C5 invalidate why=%s fault=%s hello=%d\n", why, voice_fault_name(fault),
           s_rt.helloed);
    fflush(stdout);
}

static void local_stop_playback(const char *why)
{
    s_rt.vol_req = 0;
    if (s_rt.play == PLAY_IDLE) {
        s_rt.accept_downlink = false;
        voice_vad_reset(&s_rt.vad);
        return;
    }
    s_rt.accept_downlink = false;
    finish_playback(why);
}

static bool send_text(const char *json)
{
    if (s_rt.ws == NULL || !esp_websocket_client_is_connected(s_rt.ws)) {
        return false;
    }
    const int len = (int)strlen(json);
    return esp_websocket_client_send_text(s_rt.ws, json, len, pdMS_TO_TICKS(500)) == len;
}

static bool send_bin(const uint8_t *frame)
{
    if (s_rt.ws == NULL || !esp_websocket_client_is_connected(s_rt.ws)) {
        return false;
    }
    return esp_websocket_client_send_bin(s_rt.ws, (const char *)frame, VOICE_WIRE_BYTES,
                                         pdMS_TO_TICKS(200)) == VOICE_WIRE_BYTES;
}

static void handle_control(const char *text, int len)
{
    cJSON *root = cJSON_ParseWithLength(text, (size_t)len);
    if (root == NULL) {
        return;
    }
    const cJSON *type = cJSON_GetObjectItemCaseSensitive(root, "type");
    if (!cJSON_IsString(type) || type->valuestring == NULL) {
        cJSON_Delete(root);
        return;
    }
    if (strcmp(type->valuestring, "hello_ok") == 0) {
        s_rt.helloed = true;
        xEventGroupSetBits(s_rt.events, HELLO_OK_BIT);
    } else if (strcmp(type->valuestring, "playback_start") == 0) {
        begin_playback();
    } else if (strcmp(type->valuestring, "playback_end") == 0) {
        if (s_rt.play != PLAY_IDLE) {
            s_rt.play = PLAY_DRAINING;
        }
    } else if (strcmp(type->valuestring, "conversation_end") == 0) {
        invalidate_session("ended", VOICE_FAULT_SESSION_CLOSED);
    } else if (strcmp(type->valuestring, "conversation_opened") == 0) {
        const cJSON *cid = cJSON_GetObjectItemCaseSensitive(root, "conversation_id");
        if (cJSON_IsNumber(cid)) {
            s_rt.conversation_id = (uint32_t)cid->valuedouble;
        }
        s_rt.conversation_creates++;
        s_rt.recovery.conversation_valid = true;
        s_rt.recovery.conversation_id = s_rt.conversation_id;
        voice_wake_disarm(&s_rt.wake);
        xEventGroupSetBits(s_rt.events, OPENED_BIT);
    } else if (strcmp(type->valuestring, "conversation_reject") == 0 ||
               strcmp(type->valuestring, "hello_error") == 0) {
        xEventGroupSetBits(s_rt.events, REJECT_BIT);
    } else if (strcmp(type->valuestring, "error") == 0) {
        /* A bridge-side conversation invalidation (e.g. after reconnect) must
         * clear device conversation state so the next utterance re-opens. */
        const cJSON *code = cJSON_GetObjectItemCaseSensitive(root, "code");
        if (cJSON_IsString(code) && code->valuestring != NULL &&
            strcmp(code->valuestring, "unknown_conversation") == 0) {
            invalidate_session("invalid", VOICE_FAULT_UNKNOWN_CONVERSATION);
            ESP_LOGW(TAG, "conversation invalidated by bridge; will re-open");
        }
    }
    cJSON_Delete(root);
}

static void handle_downlink(const uint8_t *data, int len)
{
    if (len != VOICE_WIRE_BYTES || data == NULL) {
        return;
    }
    voice_frame_view_t view;
    if (voice_unpack_frame(data, (size_t)len, &view) != 0) {
        return;
    }
    if (s_rt.conversation_id == 0 || view.conversation_id != s_rt.conversation_id) {
        s_rt.rx_drop_cid++;
        return;
    }
    if (!s_rt.accept_downlink) {
        s_rt.rx_drop_barge++;
        return;
    }
    if (s_rt.rx_seq_seen >= 0) {
        if (view.seq == (uint32_t)s_rt.rx_seq_seen) {
            s_rt.rx_dup++;
            return;
        }
        if (view.seq < (uint32_t)s_rt.rx_seq_seen) {
            s_rt.rx_reorder++;
            return;
        }
        if (view.seq > (uint32_t)s_rt.rx_seq_seen + 1) {
            s_rt.rx_gap += view.seq - (uint32_t)s_rt.rx_seq_seen - 1;
        }
    }
    s_rt.rx_seq_seen = (int32_t)view.seq;
    if (s_rt.play == PLAY_IDLE) {
        s_rt.play = PLAY_BUFFERING;
        s_rt.play_start_us = esp_timer_get_time();
    }
    if (s_rt.mu != NULL && xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(5)) == pdTRUE) {
        voice_rxq_push_pcm(s_rt.rxq, (const int16_t *)view.pcm, VOICE_SAMPLES_PER_FRAME);
        xSemaphoreGive(s_rt.mu);
    }
    s_rt.frames_rx++;
    if (s_rt.first_rx_us == 0) {
        s_rt.first_rx_us = esp_timer_get_time();
        printf("PHASE2C_C2 first_audio cid=%lu seq=%lu speech_end_to_rx_ms=%ld\n",
               (unsigned long)s_rt.conversation_id, (unsigned long)view.seq,
               s_rt.speech_end_us > 0
                   ? (long)((s_rt.first_rx_us - s_rt.speech_end_us) / 1000)
                   : -1);
        fflush(stdout);
    }
}

static void ws_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    (void)base;
    const esp_websocket_event_data_t *evt = data;
    switch (id) {
    case WEBSOCKET_EVENT_CONNECTED:
        xEventGroupSetBits(s_rt.events, WS_CONNECTED_BIT);
        break;
    case WEBSOCKET_EVENT_DISCONNECTED:
    case WEBSOCKET_EVENT_CLOSED:
    case WEBSOCKET_EVENT_ERROR:
        invalidate_session("disconnect", id == WEBSOCKET_EVENT_ERROR ? VOICE_FAULT_TRANSPORT
                                                                     : VOICE_FAULT_WS_CLOSE);
        xEventGroupSetBits(s_rt.events, WS_CLOSED_BIT);
        break;
    case WEBSOCKET_EVENT_DATA:
        if (evt == NULL || evt->data_ptr == NULL || !evt->fin || evt->payload_offset != 0 ||
            evt->data_len != evt->payload_len) {
            break;
        }
        if (evt->op_code == 0x01) {
            handle_control(evt->data_ptr, evt->data_len);
        } else if (evt->op_code == 0x02) {
            handle_downlink((const uint8_t *)evt->data_ptr, evt->data_len);
        }
        break;
    default:
        break;
    }
}

static void close_ws(void)
{
    if (s_rt.ws == NULL) {
        return;
    }
    esp_websocket_client_close(s_rt.ws, pdMS_TO_TICKS(200));
    esp_websocket_client_destroy(s_rt.ws);
    s_rt.ws = NULL;
    s_rt.helloed = false;
}

static bool ensure_connected(void)
{
    if (s_rt.ws != NULL && esp_websocket_client_is_connected(s_rt.ws) && s_rt.helloed) {
        return true;
    }
    close_ws();
    xEventGroupClearBits(s_rt.events, WS_CONNECTED_BIT | HELLO_OK_BIT | OPENED_BIT |
                                          REJECT_BIT | WS_CLOSED_BIT);
    const esp_websocket_client_config_t cfg = {
        .uri = CONFIG_VOICE_BRIDGE_URI,
        .disable_auto_reconnect = true,
        .network_timeout_ms = 8000,
        .buffer_size = 4096,
        .task_stack = 8192,
    };
    s_rt.ws = esp_websocket_client_init(&cfg);
    if (s_rt.ws == NULL) {
        return false;
    }
    if (esp_websocket_register_events(s_rt.ws, WEBSOCKET_EVENT_ANY, ws_event, NULL) != ESP_OK ||
        esp_websocket_client_start(s_rt.ws) != ESP_OK) {
        close_ws();
        return false;
    }
    EventBits_t bits = xEventGroupWaitBits(s_rt.events, WS_CONNECTED_BIT | WS_CLOSED_BIT,
                                           pdFALSE, pdFALSE, pdMS_TO_TICKS(4000));
    if ((bits & WS_CONNECTED_BIT) == 0) {
        close_ws();
        return false;
    }
    char hello[256];
    if (voice_hello_json(hello, sizeof(hello), CONFIG_VOICE_DEVICE_ID, "phase-2c-c5") <= 0 ||
        !send_text(hello)) {
        close_ws();
        return false;
    }
    bits = xEventGroupWaitBits(s_rt.events, HELLO_OK_BIT | REJECT_BIT | WS_CLOSED_BIT,
                               pdFALSE, pdFALSE, pdMS_TO_TICKS(3000));
    if ((bits & HELLO_OK_BIT) == 0) {
        close_ws();
        return false;
    }
    ESP_LOGI(TAG, "hello_ok uri=%s", CONFIG_VOICE_BRIDGE_URI);
    return true;
}

static int flush_queue(void)
{
    uint8_t frame[VOICE_WIRE_BYTES];
    int sent = 0;
    while (true) {
        int n = 0;
        if (xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(20)) == pdTRUE) {
            n = voice_txq_pop(s_rt.txq, frame);
            xSemaphoreGive(s_rt.mu);
        }
        if (n != VOICE_WIRE_BYTES) {
            break;
        }
        if (!send_bin(frame)) {
            break;
        }
        s_rt.frames_sent++;
        s_rt.bytes_sent += VOICE_FRAME_BYTES;
        if (s_rt.first_frame_us == 0) {
            s_rt.first_frame_us = esp_timer_get_time();
        }
        sent++;
    }
    return sent;
}

static bool send_interrupt(const char *why)
{
    char msg[128];
    if (s_rt.conversation_id == 0) {
        return false;
    }
    s_rt.accept_downlink = false;
    s_rt.barge_pending = false;
    s_rt.stop_play = false;
    if (voice_control_json(msg, sizeof(msg), "interrupt", s_rt.conversation_id, NULL) <= 0 ||
        !send_text(msg)) {
        return false;
    }
    s_rt.interrupts_sent++;
    printf("PHASE2C_C3 interrupt_sent cid=%lu why=%s residual=%lu play_rms=%lu\n",
           (unsigned long)s_rt.conversation_id, why,
           (unsigned long)s_rt.overlap_residual, (unsigned long)s_rt.overlap_play);
    fflush(stdout);
    return true;
}

static void end_conversation_local(const char *reason)
{
    char msg[160];
    if (s_rt.conversation_id == 0) {
        return;
    }
    printf("PHASE2C_C4 conversation_end reason=%s cid=%lu turns=%lu\n", reason,
           (unsigned long)s_rt.conversation_id, (unsigned long)s_rt.turn_index);
    fflush(stdout);
    if (voice_control_json(msg, sizeof(msg), "conversation_end", s_rt.conversation_id,
                           reason) > 0) {
        send_text(msg);
    }
    s_rt.conversation_id = 0;
    s_rt.listen_followup = false;
    s_rt.await_reply = false;
    s_rt.turn_index = 0;
    voice_wake_arm(&s_rt.wake);
}

static bool run_utterance(void)
{
    if (!ensure_connected()) {
        printf("PHASE2C_C1 talk_fail reason=connect\n");
        fflush(stdout);
        return false;
    }
    char msg[128];
    if (s_rt.conversation_id == 0) {
        xEventGroupClearBits(s_rt.events, OPENED_BIT | REJECT_BIT);
        if (voice_control_json(msg, sizeof(msg), "conversation_open", 0, "manual") <= 0 ||
            !send_text(msg)) {
            printf("PHASE2C_C1 talk_fail reason=open_send\n");
            fflush(stdout);
            return false;
        }
        EventBits_t bits = xEventGroupWaitBits(
            s_rt.events, OPENED_BIT | REJECT_BIT | WS_CLOSED_BIT, pdTRUE, pdFALSE,
            pdMS_TO_TICKS(12000));
        if ((bits & OPENED_BIT) == 0) {
            printf("PHASE2C_C1 talk_fail reason=open\n");
            fflush(stdout);
            return false;
        }
    }
    if (xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(50)) == pdTRUE) {
        voice_txq_clear(s_rt.txq);
        xSemaphoreGive(s_rt.mu);
    }
    s_rt.listen_followup = false;
    s_rt.await_reply = false;
    s_rt.turn_index++;
    printf("PHASE2C_C4 turn_start n=%lu cid=%lu\n", (unsigned long)s_rt.turn_index,
           (unsigned long)s_rt.conversation_id);
    fflush(stdout);
    s_rt.seq = 0;
    s_rt.frames_sent = 0;
    s_rt.bytes_sent = 0;
    s_rt.first_frame_us = 0;
    s_rt.speech_start_us = esp_timer_get_time();
    s_rt.speech_end_us = 0;
    const bool barging = s_rt.barge_pending || s_rt.play != PLAY_IDLE;
    if (s_rt.play != PLAY_IDLE) {
        local_stop_playback("barge_in");
    } else {
        reset_playback();
    }
    if (barging && !send_interrupt("utterance")) {
        printf("PHASE2C_C3 interrupt_fail cid=%lu\n", (unsigned long)s_rt.conversation_id);
        fflush(stdout);
    }
    if (voice_control_json(msg, sizeof(msg), "speech_start", s_rt.conversation_id, NULL) <= 0 ||
        !send_text(msg)) {
        printf("PHASE2C_C1 talk_fail reason=speech_start\n");
        fflush(stdout);
        return false;
    }
    s_rt.speaking = true;
    TickType_t deadline = xTaskGetTickCount() + pdMS_TO_TICKS(CONFIG_VOICE_UTTERANCE_MS);
    while (xTaskGetTickCount() < deadline && s_rt.speaking) {
        flush_queue();
        if (!esp_websocket_client_is_connected(s_rt.ws)) {
            s_rt.speaking = false;
            printf("PHASE2C_C1 talk_fail reason=disconnect\n");
            fflush(stdout);
            return false;
        }
        if (s_rt.barge_pending) {
            send_interrupt("mid_utterance");
            if (xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(50)) == pdTRUE) {
                voice_txq_clear(s_rt.txq);
                xSemaphoreGive(s_rt.mu);
            }
            s_rt.seq = 0;
            s_rt.frames_sent = 0;
            s_rt.bytes_sent = 0;
            s_rt.first_frame_us = 0;
            s_rt.speech_start_us = esp_timer_get_time();
            if (voice_control_json(msg, sizeof(msg), "speech_start", s_rt.conversation_id,
                                   NULL) > 0) {
                send_text(msg);
            }
            deadline = xTaskGetTickCount() + pdMS_TO_TICKS(CONFIG_VOICE_UTTERANCE_MS);
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    s_rt.speaking = false;
    vTaskDelay(pdMS_TO_TICKS(30));
    flush_queue();
    voice_control_json(msg, sizeof(msg), "speech_end", s_rt.conversation_id, NULL);
    send_text(msg);
    s_rt.speech_end_us = esp_timer_get_time();
    const int64_t now = esp_timer_get_time();
    printf("PHASE2C_C1 talk_done cid=%lu frames=%lu bytes=%lu drop=%lu drop_total=%lu "
           "qpeak=%lu open_to_first_ms=%ld capture_ms=%ld\n",
           (unsigned long)s_rt.conversation_id, (unsigned long)s_rt.frames_sent,
           (unsigned long)s_rt.bytes_sent,
           (unsigned long)(s_rt.txq != NULL ? s_rt.txq->dropped : 0),
           (unsigned long)(s_rt.txq != NULL ? s_rt.txq->dropped_total : 0),
           (unsigned long)(s_rt.txq != NULL ? s_rt.txq->peak_count : 0),
           s_rt.first_frame_us > 0
               ? (long)((s_rt.first_frame_us - s_rt.speech_start_us) / 1000)
               : -1,
           (long)((now - s_rt.speech_start_us) / 1000));
    fflush(stdout);
    s_rt.await_reply = true;
    printf("PHASE2C_C4 turn_end n=%lu cid=%lu frames=%lu\n",
           (unsigned long)s_rt.turn_index, (unsigned long)s_rt.conversation_id,
           (unsigned long)s_rt.frames_sent);
    fflush(stdout);
    log_metrics("after_talk");
    return true;
}

static void net_task(void *arg)
{
    (void)arg;
    while (true) {
        if (!network_is_connected()) {
            if (s_rt.ws != NULL || s_rt.helloed || s_rt.conversation_id != 0) {
                s_rt.wifi_losses++;
                invalidate_session("wifi", VOICE_FAULT_WIFI_LOST);
                close_ws();
            }
            xEventGroupWaitBits(s_rt.events, TALK_BIT | END_BIT, pdTRUE, pdFALSE,
                                pdMS_TO_TICKS(500));
            continue;
        }
        if (!s_rt.helloed) {
            if (ensure_connected()) {
                voice_recovery_on_hello_ok(&s_rt.recovery);
                s_rt.hello_ok_count++;
                if (s_rt.recovery.reconnects > 1) {
                    s_rt.ws_reconnects = s_rt.recovery.reconnects - 1;
                }
                printf("PHASE2C_C5 hello_ok reconnects=%lu backoff=%lu\n",
                       (unsigned long)s_rt.ws_reconnects,
                       (unsigned long)s_rt.recovery.last_backoff_ms);
                fflush(stdout);
            } else {
                const uint32_t wait_ms = voice_recovery_next_backoff_ms(&s_rt.recovery);
                printf("PHASE2C_C5 reconnect_wait ms=%lu fault=bridge_gone\n",
                       (unsigned long)wait_ms);
                fflush(stdout);
                vTaskDelay(pdMS_TO_TICKS(wait_ms));
                continue;
            }
        }
        EventBits_t bits = xEventGroupWaitBits(
            s_rt.events, TALK_BIT | END_BIT | WS_CLOSED_BIT, pdTRUE, pdFALSE, pdMS_TO_TICKS(1000));
        if ((bits & END_BIT) != 0 && (bits & TALK_BIT) == 0) {
            end_conversation_local("timeout");
            voice_wake_arm(&s_rt.wake);
            continue;
        }
        if ((bits & TALK_BIT) != 0) {
            s_rt.talk_req_us = esp_timer_get_time();
            run_utterance();
        }
    }
}

static esp_err_t setup_audio_path(aec_handle_t **aec)
{
    ESP_RETURN_ON_ERROR(audio_hw_init(), TAG, "audio_hw_init");
    ESP_RETURN_ON_ERROR(audio_hw_input_enable(true), TAG, "input");
    ESP_RETURN_ON_ERROR(audio_hw_output_enable(true), TAG, "output");
    *aec = aec_create(AUDIO_HW_SAMPLE_RATE, 4, 1, AEC_MODE_VOIP_HIGH_PERF);
    ESP_RETURN_ON_FALSE(*aec != NULL, ESP_FAIL, TAG, "aec_create");
    return ESP_OK;
}

static void teardown_audio_path(aec_handle_t **aec)
{
    if (*aec != NULL) {
        aec_destroy(*aec);
        *aec = NULL;
    }
}

/* Owns the audio path or returns false with the owner, the AEC and every
 * hardware resource released; callers retry without holding AUDIO_OWNER_VOICE. */
static bool establish_audio_path(aec_handle_t **aec)
{
    if (audio_owner_acquire(AUDIO_OWNER_VOICE, portMAX_DELAY) != ESP_OK) {
        return false;
    }
    if (setup_audio_path(aec) == ESP_OK) {
        return true;
    }
    ESP_LOGE(TAG, "audio path setup failed; releasing owner");
    teardown_audio_path(aec);
    audio_owner_release(AUDIO_OWNER_VOICE);
    return false;
}

static void release_audio_path(aec_handle_t **aec)
{
    teardown_audio_path(aec);
    audio_owner_release(AUDIO_OWNER_VOICE);
}

static void free_audio_buffers(int16_t *buffers[], int n)
{
    for (int i = 0; i < n; i++) {
        heap_caps_free(buffers[i]);
        buffers[i] = NULL;
    }
}

static void audio_task(void *arg)
{
    (void)arg;
    for (int i = 0; i < 50 && !network_is_connected(); i++) {
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    audio_owner_request(AUDIO_OWNER_VOICE);
    if (audio_owner_acquire(AUDIO_OWNER_VOICE, pdMS_TO_TICKS(2000)) != ESP_OK) {
        ESP_LOGE(TAG, "voice could not acquire audio");
        vTaskDelete(NULL);
        return;
    }
    aec_handle_t *aec = NULL;
    if (setup_audio_path(&aec) != ESP_OK) {
        release_audio_path(&aec);
        vTaskDelete(NULL);
        return;
    }
    /* Buffers are sized for the largest chunk a re-created AEC may report so
     * yield/re-acquire cycles never need reallocation. */
    const size_t buf_samples = 1024;
    int16_t *buffers[5] = { 0 };
    for (int i = 0; i < 4; i++) {
        buffers[i] = heap_caps_malloc(buf_samples * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    }
    buffers[4] = heap_caps_calloc(buf_samples, sizeof(int16_t), MALLOC_CAP_INTERNAL);
    if (buffers[0] == NULL || buffers[1] == NULL || buffers[2] == NULL ||
        buffers[3] == NULL || buffers[4] == NULL) {
        ESP_LOGE(TAG, "audio buffers missing");
        free_audio_buffers(buffers, 5);
        release_audio_path(&aec);
        vTaskDelete(NULL);
        return;
    }
    int16_t *mic0 = buffers[0];
    int16_t *ref = buffers[1];
    int16_t *mic1 = buffers[2];
    int16_t *out = buffers[3];
    int16_t *silence = buffers[4];
    int chunk = aec_get_chunksize(aec);
    if (chunk <= 0 || chunk > (int)buf_samples) {
        chunk = 256;
    }
    int16_t acc[VOICE_SAMPLES_PER_FRAME];
    int acc_n = 0;
    uint8_t wire[VOICE_WIRE_BYTES];
    TickType_t last_log = xTaskGetTickCount();
    log_metrics("audio_ready");
    while (true) {
        if (audio_owner_should_yield(AUDIO_OWNER_VOICE)) {
            s_rt.audio_yields++;
            s_rt.speaking = false;
            s_rt.stop_play = false;
            s_rt.barge_pending = false;
            s_rt.listen_followup = false;
            s_rt.await_reply = false;
            if (s_rt.play != PLAY_IDLE) {
                local_stop_playback("yield");
            } else {
                reset_playback();
            }
            release_audio_path(&aec);
            /* Give the requesting owner a clear window to take ownership;
             * re-grabbing in a tight loop would starve it. */
            vTaskDelay(pdMS_TO_TICKS(100));
            while (audio_owner_current() != AUDIO_OWNER_NONE) {
                vTaskDelay(pdMS_TO_TICKS(100));
            }
            while (!establish_audio_path(&aec)) {
                vTaskDelay(pdMS_TO_TICKS(500));
            }
            s_rt.audio_reacquires++;
            chunk = aec_get_chunksize(aec);
            if (chunk <= 0 || chunk > (int)buf_samples) {
                chunk = 256;
            }
            acc_n = 0;
            continue;
        }
        if (s_rt.vol_req >= 0) {
            audio_hw_set_output_volume(s_rt.vol_req);
            s_rt.vol_req = -1;
        }
        if (audio_hw_read(mic0, ref, mic1, chunk) != ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }
        aec_process(aec, mic0, ref, out);
        int16_t play_pcm[1024];
        const int16_t *tx = silence;
        if (s_rt.stop_play && s_rt.play != PLAY_IDLE) {
            local_stop_playback("button");
            s_rt.stop_play = false;
            s_rt.barge_pending = true;
        }
        play_state_t play = s_rt.play;
        const int64_t now_us = esp_timer_get_time();
        const bool holdoff_ok =
            play == PLAY_ACTIVE && s_rt.play_start_us > 0 &&
            (now_us - s_rt.play_start_us) >= (int64_t)VOICE_BARGE_HOLDOFF_MS * 1000 &&
            (s_rt.speech_end_us == 0 ||
             (now_us - s_rt.speech_end_us) >= (int64_t)VOICE_BARGE_POST_SPEECH_MS * 1000);
        if (play == PLAY_ACTIVE) {
            const uint32_t residual = voice_pcm_mean_abs(out, chunk);
            if (holdoff_ok &&
                voice_vad_feed(&s_rt.vad, residual, s_rt.overlap_play, false) &&
                voice_barge_should_stop(true, true, true)) {
                local_stop_playback("vad");
                s_rt.barge_pending = true;
                s_rt.stop_play = false;
                if (!s_rt.speaking && s_rt.events != NULL) {
                    xEventGroupSetBits(s_rt.events, TALK_BIT);
                }
                printf("PHASE2C_C3 barge_in why=vad cid=%lu energy=%lu play_rms=%lu floor=%lu\n",
                       (unsigned long)s_rt.conversation_id, (unsigned long)s_rt.vad.last_abs,
                       (unsigned long)s_rt.overlap_play, (unsigned long)s_rt.vad.floor_abs);
                fflush(stdout);
                play = PLAY_IDLE;
            } else if (!holdoff_ok) {
                voice_vad_feed(&s_rt.vad, residual, s_rt.overlap_play, true);
            }
        } else if (voice_followup_should_listen(s_rt.listen_followup, play == PLAY_ACTIVE ||
                                                                        play == PLAY_DRAINING ||
                                                                        play == PLAY_BUFFERING,
                                               s_rt.speaking, s_rt.conversation_id)) {
            if (voice_followup_expired(now_us, s_rt.listen_start_us)) {
                s_rt.listen_followup = false;
                s_rt.followup_timeouts++;
                if (s_rt.events != NULL) {
                    xEventGroupSetBits(s_rt.events, END_BIT);
                }
            } else if (voice_followup_holdoff_ok(now_us, s_rt.listen_start_us)) {
                const uint32_t mag = voice_pcm_mean_abs(out, chunk);
                if (voice_followup_should_trigger(
                        true, false, false, s_rt.conversation_id, true,
                        voice_vad_feed(&s_rt.vad, mag, 0, false))) {
                    s_rt.listen_followup = false;
                    s_rt.followup_vad_hits++;
                    if (s_rt.events != NULL) {
                        xEventGroupSetBits(s_rt.events, TALK_BIT);
                    }
                    printf("PHASE2C_C4 follow_up why=vad cid=%lu energy=%lu floor=%lu "
                           "turn=%lu\n",
                           (unsigned long)s_rt.conversation_id,
                           (unsigned long)s_rt.vad.last_abs,
                           (unsigned long)s_rt.vad.floor_abs,
                           (unsigned long)s_rt.turn_index);
                    fflush(stdout);
                }
            } else {
                voice_vad_feed(&s_rt.vad, voice_pcm_mean_abs(out, chunk), 0, true);
            }
        } else if (!s_rt.listen_followup) {
            voice_vad_reset(&s_rt.vad);
        }
        if (s_rt.await_reply && play == PLAY_IDLE && !s_rt.speaking &&
            !s_rt.listen_followup && s_rt.conversation_id != 0 && s_rt.speech_end_us > 0 &&
            (now_us - s_rt.speech_end_us) >= (int64_t)VOICE_FOLLOWUP_WAIT_REPLY_MS * 1000) {
            s_rt.await_reply = false;
            start_followup_listen("no_reply");
        }
        if (play == PLAY_BUFFERING) {
            int ready = 0;
            if (xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(5)) == pdTRUE) {
                ready = voice_rxq_ready(s_rt.rxq);
                xSemaphoreGive(s_rt.mu);
            }
            if (ready) {
                s_rt.play = PLAY_ACTIVE;
                s_rt.fade_in = true;
                play = PLAY_ACTIVE;
            }
        }
        if ((play == PLAY_ACTIVE || play == PLAY_DRAINING) && chunk <= 1024) {
            int n = 0;
            if (xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(5)) == pdTRUE) {
                n = voice_rxq_pop_pcm(s_rt.rxq, play_pcm, chunk);
                xSemaphoreGive(s_rt.mu);
            }
            if (n < chunk) {
                memset(play_pcm + n, 0, (size_t)(chunk - n) * sizeof(int16_t));
                if (play == PLAY_ACTIVE) {
                    s_rt.play_underrun++;
                }
                if (play == PLAY_DRAINING && n == 0) {
                    finish_playback("drained");
                }
            }
            if (n > 0) {
                if (s_rt.fade_in) {
                    fade_from_zero(play_pcm, n);
                    s_rt.fade_in = false;
                }
                const uint32_t peak = pcm_peak(play_pcm, n);
                if (peak > s_rt.play_peak) {
                    s_rt.play_peak = peak;
                }
                s_rt.samples_play += (uint32_t)n;
                tx = play_pcm;
            }
        }
        if (play == PLAY_ACTIVE || play == PLAY_DRAINING || s_rt.speaking) {
            const uint32_t residual = voice_pcm_mean_abs(out, chunk);
            const uint32_t play_rms = voice_pcm_mean_abs(tx, chunk);
            s_rt.overlap_residual = residual;
            s_rt.overlap_play = play_rms;
            if (residual > s_rt.residual_peak) {
                s_rt.residual_peak = residual;
            }
            if (play == PLAY_ACTIVE && (s_rt.samples_play / chunk % 50) == 0) {
                printf("PHASE2C_C3 overlap residual=%lu play_rms=%lu floor=%lu onset=%lu speaking=%d\n",
                       (unsigned long)residual, (unsigned long)play_rms,
                       (unsigned long)s_rt.vad.floor_abs, (unsigned long)s_rt.vad.onset,
                       s_rt.speaking);
                fflush(stdout);
            }
        }
        audio_hw_write(tx, chunk);
        if (s_rt.speaking) {
            for (int i = 0; i < chunk; i++) {
                acc[acc_n++] = out[i];
                if (acc_n == VOICE_SAMPLES_PER_FRAME) {
                    const uint8_t flags = s_rt.seq == 0 ? VOICE_FLAG_UTTERANCE_START : 0;
                    const uint32_t ts = (uint32_t)(esp_timer_get_time() / 1000);
                    if (voice_pack_frame(wire, sizeof(wire), s_rt.conversation_id, s_rt.seq, ts,
                                         flags, acc, VOICE_SAMPLES_PER_FRAME) == VOICE_WIRE_BYTES) {
                        if (xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(5)) == pdTRUE) {
                            const int rc = voice_txq_push(s_rt.txq, wire);
                            xSemaphoreGive(s_rt.mu);
                            if (rc == -2) {
                                s_rt.speaking = false;
                                printf("PHASE2C_C1 transport_error drop=%lu drop_total=%lu\n",
                                       (unsigned long)s_rt.txq->dropped,
                                       (unsigned long)s_rt.txq->dropped_total);
                                fflush(stdout);
                            }
                        }
                        s_rt.seq++;
                    }
                    acc_n = 0;
                }
            }
        } else {
            acc_n = 0;
        }
        if ((xTaskGetTickCount() - last_log) >= pdMS_TO_TICKS(60000)) {
            log_metrics("tick");
            last_log = xTaskGetTickCount();
        }
    }
}

esp_err_t voice_runtime_start(void)
{
    ESP_RETURN_ON_ERROR(audio_owner_init(), TAG, "audio owner");
    if (s_rt.events == NULL) {
        s_rt.events = xEventGroupCreateStatic(&s_event_buf);
        s_rt.mu = xSemaphoreCreateMutexStatic(&s_mu_buf);
        s_rt.txq = heap_caps_calloc(1, sizeof(*s_rt.txq), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (s_rt.txq != NULL) {
            voice_txq_init(s_rt.txq);
        }
        s_rt.rxq = heap_caps_calloc(1, sizeof(*s_rt.rxq), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (s_rt.rxq != NULL) {
            voice_rxq_init(s_rt.rxq);
        }
        s_rt.rx_seq_seen = -1;
        s_rt.accept_downlink = true;
        s_rt.vol_req = -1;
        s_rt.listen_followup = false;
        s_rt.await_reply = false;
        voice_vad_init(&s_rt.vad);
        voice_recovery_init(&s_rt.recovery);
        voice_wake_init(&s_rt.wake, VOICE_WAKE_SRC_NONE);
    }
    ESP_RETURN_ON_FALSE(s_rt.events != NULL && s_rt.mu != NULL && s_rt.txq != NULL &&
                            s_rt.rxq != NULL,
                        ESP_ERR_NO_MEM, TAG, "sync");
    BaseType_t ok = xTaskCreate(audio_task, "voice_audio", AUDIO_TASK_STACK, NULL,
                                AUDIO_TASK_PRIO, NULL);
    ESP_RETURN_ON_FALSE(ok == pdPASS, ESP_FAIL, TAG, "audio task");
    ok = xTaskCreate(net_task, "voice_net", NET_TASK_STACK, NULL, NET_TASK_PRIO, NULL);
    ESP_RETURN_ON_FALSE(ok == pdPASS, ESP_FAIL, TAG, "net task");
    ESP_LOGI(TAG, "C5 runtime ready uri=%s wake=%s", CONFIG_VOICE_BRIDGE_URI,
             voice_wake_model_status());
    return ESP_OK;
}

void voice_runtime_request_talk(void)
{
    voice_wake_feed_manual(&s_rt.wake);
    if (s_rt.play != PLAY_IDLE) {
        s_rt.stop_play = true;
        s_rt.barge_pending = true;
        if (s_rt.speaking) {
            ESP_LOGI(TAG, "manual barge during capture");
            return;
        }
    }
    if (s_rt.events != NULL) {
        xEventGroupSetBits(s_rt.events, TALK_BIT);
        ESP_LOGI(TAG, "manual talk requested play=%d", (int)s_rt.play);
    }
}

void voice_runtime_on_wake(void)
{
    if (s_rt.conversation_id != 0) {
        ESP_LOGI(TAG, "wake ignored; follow-up uses VAD cid=%lu",
                 (unsigned long)s_rt.conversation_id);
        return;
    }
    if (!voice_wake_feed_mock(&s_rt.wake, true) && s_rt.wake.source != VOICE_WAKE_SRC_NONE) {
        return;
    }
    voice_wake_take(&s_rt.wake);
    voice_runtime_request_talk();
}

void voice_runtime_on_network(bool connected)
{
    if (!connected && s_rt.events != NULL) {
        xEventGroupSetBits(s_rt.events, WS_CLOSED_BIT);
    }
}
