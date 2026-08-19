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

static const char *TAG = "voice_c1";

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

typedef struct {
    EventGroupHandle_t events;
    SemaphoreHandle_t mu;
    voice_txq_t *txq;
    esp_websocket_client_handle_t ws;
    volatile uint32_t conversation_id;
    uint32_t seq;
    volatile bool speaking;
    volatile bool helloed;
    uint32_t frames_sent;
    uint32_t bytes_sent;
    int64_t talk_req_us;
    int64_t speech_start_us;
    int64_t first_frame_us;
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
    uint32_t dropped = 0;
    if (xSemaphoreTake(s_rt.mu, pdMS_TO_TICKS(20)) == pdTRUE) {
        qdepth = voice_txq_count(s_rt.txq);
        dropped = s_rt.txq != NULL ? s_rt.txq->dropped : 0;
        xSemaphoreGive(s_rt.mu);
    }
    printf("PHASE2C_C1 %s conn=%d hello=%d cid=%lu frames=%lu bytes=%lu drop=%lu "
           "q=%d heap=%u psram=%u\n",
           label,
           s_rt.ws != NULL && esp_websocket_client_is_connected(s_rt.ws),
           s_rt.helloed, (unsigned long)s_rt.conversation_id,
           (unsigned long)s_rt.frames_sent, (unsigned long)s_rt.bytes_sent,
           (unsigned long)dropped, qdepth, (unsigned)internal.total_free_bytes,
           (unsigned)ps_free);
    fflush(stdout);
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
    } else if (strcmp(type->valuestring, "conversation_opened") == 0) {
        const cJSON *cid = cJSON_GetObjectItemCaseSensitive(root, "conversation_id");
        if (cJSON_IsNumber(cid)) {
            s_rt.conversation_id = (uint32_t)cid->valuedouble;
        }
        xEventGroupSetBits(s_rt.events, OPENED_BIT);
    } else if (strcmp(type->valuestring, "conversation_reject") == 0 ||
               strcmp(type->valuestring, "hello_error") == 0) {
        xEventGroupSetBits(s_rt.events, REJECT_BIT);
    }
    cJSON_Delete(root);
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
        s_rt.helloed = false;
        s_rt.speaking = false;
        xEventGroupSetBits(s_rt.events, WS_CLOSED_BIT);
        break;
    case WEBSOCKET_EVENT_DATA:
        if (evt != NULL && evt->op_code == 0x01 && evt->fin && evt->payload_offset == 0 &&
            evt->data_ptr != NULL && evt->data_len == evt->payload_len) {
            handle_control(evt->data_ptr, evt->data_len);
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
        .network_timeout_ms = 4000,
        .buffer_size = 2048,
        .task_stack = 6144,
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
    if (voice_hello_json(hello, sizeof(hello), CONFIG_VOICE_DEVICE_ID, "phase-2c-c1") <= 0 ||
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
        if (s_rt.txq != NULL) {
            s_rt.txq->dropped = 0;
        }
        xSemaphoreGive(s_rt.mu);
    }
    s_rt.seq = 0;
    s_rt.frames_sent = 0;
    s_rt.bytes_sent = 0;
    s_rt.first_frame_us = 0;
    s_rt.speech_start_us = esp_timer_get_time();
    if (voice_control_json(msg, sizeof(msg), "speech_start", s_rt.conversation_id, NULL) <= 0 ||
        !send_text(msg)) {
        printf("PHASE2C_C1 talk_fail reason=speech_start\n");
        fflush(stdout);
        return false;
    }
    s_rt.speaking = true;
    const TickType_t deadline = xTaskGetTickCount() + pdMS_TO_TICKS(CONFIG_VOICE_UTTERANCE_MS);
    while (xTaskGetTickCount() < deadline && s_rt.speaking) {
        flush_queue();
        if (!esp_websocket_client_is_connected(s_rt.ws)) {
            s_rt.speaking = false;
            printf("PHASE2C_C1 talk_fail reason=disconnect\n");
            fflush(stdout);
            return false;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    s_rt.speaking = false;
    vTaskDelay(pdMS_TO_TICKS(30));
    flush_queue();
    voice_control_json(msg, sizeof(msg), "speech_end", s_rt.conversation_id, NULL);
    send_text(msg);
    const int64_t now = esp_timer_get_time();
    printf("PHASE2C_C1 talk_done cid=%lu frames=%lu bytes=%lu drop=%lu "
           "open_to_first_ms=%ld capture_ms=%ld\n",
           (unsigned long)s_rt.conversation_id, (unsigned long)s_rt.frames_sent,
           (unsigned long)s_rt.bytes_sent,            (unsigned long)(s_rt.txq != NULL ? s_rt.txq->dropped : 0),
           s_rt.first_frame_us > 0
               ? (long)((s_rt.first_frame_us - s_rt.speech_start_us) / 1000)
               : -1,
           (long)((now - s_rt.speech_start_us) / 1000));
    fflush(stdout);
    log_metrics("after_talk");
    return true;
}

static void net_task(void *arg)
{
    (void)arg;
    while (true) {
        xEventGroupWaitBits(s_rt.events, TALK_BIT, pdTRUE, pdTRUE, portMAX_DELAY);
        if (!network_is_connected()) {
            printf("PHASE2C_C1 talk_fail reason=wifi\n");
            fflush(stdout);
            continue;
        }
        s_rt.talk_req_us = esp_timer_get_time();
        run_utterance();
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
        audio_owner_release(AUDIO_OWNER_VOICE);
        vTaskDelete(NULL);
        return;
    }
    int chunk = aec_get_chunksize(aec);
    if (chunk <= 0 || chunk > 1024) {
        chunk = 256;
    }
    int16_t *mic0 = heap_caps_malloc((size_t)chunk * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *ref = heap_caps_malloc((size_t)chunk * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *mic1 = heap_caps_malloc((size_t)chunk * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *out = heap_caps_malloc((size_t)chunk * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *silence = heap_caps_calloc((size_t)chunk, sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t acc[VOICE_SAMPLES_PER_FRAME];
    int acc_n = 0;
    uint8_t wire[VOICE_WIRE_BYTES];
    TickType_t last_log = xTaskGetTickCount();
    if (!mic0 || !ref || !mic1 || !out || !silence) {
        ESP_LOGE(TAG, "audio buffers missing");
        vTaskDelete(NULL);
        return;
    }
    log_metrics("audio_ready");
    while (true) {
        if (audio_owner_should_yield(AUDIO_OWNER_VOICE)) {
            s_rt.speaking = false;
            teardown_audio_path(&aec);
            audio_owner_release(AUDIO_OWNER_VOICE);
            while (audio_owner_acquire(AUDIO_OWNER_VOICE, pdMS_TO_TICKS(200)) != ESP_OK) {
                vTaskDelay(pdMS_TO_TICKS(50));
            }
            if (setup_audio_path(&aec) != ESP_OK) {
                vTaskDelay(pdMS_TO_TICKS(500));
                continue;
            }
            chunk = aec_get_chunksize(aec);
            if (chunk <= 0 || chunk > 1024) {
                chunk = 256;
            }
            acc_n = 0;
            continue;
        }
        if (audio_hw_read(mic0, ref, mic1, chunk) != ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }
        aec_process(aec, mic0, ref, out);
        audio_hw_write(silence, chunk);
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
                                printf("PHASE2C_C1 transport_error drop=%lu\n",
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
    }
    ESP_RETURN_ON_FALSE(s_rt.events != NULL && s_rt.mu != NULL && s_rt.txq != NULL,
                        ESP_ERR_NO_MEM, TAG, "sync");
    BaseType_t ok = xTaskCreate(audio_task, "voice_audio", AUDIO_TASK_STACK, NULL,
                                AUDIO_TASK_PRIO, NULL);
    ESP_RETURN_ON_FALSE(ok == pdPASS, ESP_FAIL, TAG, "audio task");
    ok = xTaskCreate(net_task, "voice_net", NET_TASK_STACK, NULL, NET_TASK_PRIO, NULL);
    ESP_RETURN_ON_FALSE(ok == pdPASS, ESP_FAIL, TAG, "net task");
    ESP_LOGI(TAG, "C1 runtime ready uri=%s", CONFIG_VOICE_BRIDGE_URI);
    return ESP_OK;
}

void voice_runtime_request_talk(void)
{
    if (s_rt.events != NULL) {
        xEventGroupSetBits(s_rt.events, TALK_BIT);
        ESP_LOGI(TAG, "manual talk requested");
    }
}
