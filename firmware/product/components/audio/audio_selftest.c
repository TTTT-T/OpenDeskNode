#include "audio_selftest.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "audio_hw.h"
#include "audio_stimulus.h"
#include "esp_aec.h"
#include "esp_check.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_rom_crc.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"

static const char *TAG = "audio_p2a";

#define AUDIO_TASK_STACK_BYTES 20480
#define AUDIO_TASK_PRIORITY 4
#define RERUN_BIT (1 << 0)
#define STIMULUS_TAIL_SILENCE_MS 1500
#define STABILITY_LOG_PERIOD_S 60
#define ERLE_WINDOW_MS 500

typedef struct {
    int16_t *data;   /* interleaved PCM16 */
    size_t samples;  /* per-channel sample count stored */
    size_t capacity; /* per-channel capacity */
    int channels;
} capture_buf_t;

typedef struct {
    double sq_sum[3];
    int64_t peak[3];
    int32_t clip[3];
    int32_t identical_mic_samples;
    int32_t total_samples;
} channel_stats_t;

static EventGroupHandle_t s_events;
static StaticEventGroup_t s_event_group;
static bool s_volume_muted;
static volatile bool s_selftest_busy;

static void capture_reset(capture_buf_t *buf, int16_t *storage, size_t capacity_per_ch, int channels)
{
    buf->data = storage;
    buf->samples = 0;
    buf->capacity = capacity_per_ch;
    buf->channels = channels;
}

static bool capture_push(capture_buf_t *buf, const int16_t *const *channels, int samples)
{
    if (buf->samples + (size_t)samples > buf->capacity) {
        return false;
    }
    for (int s = 0; s < samples; s++) {
        for (int c = 0; c < buf->channels; c++) {
            buf->data[buf->samples * buf->channels + s * buf->channels + c] = channels[c][s];
        }
    }
    buf->samples += samples;
    return true;
}

static void stats_update(channel_stats_t *stats, const int16_t *mic0, const int16_t *ref,
                         const int16_t *mic1, int samples)
{
    const int16_t *ch[3] = { mic0, ref, mic1 };
    for (int c = 0; c < 3; c++) {
        for (int i = 0; i < samples; i++) {
            const int v = ch[c][i];
            stats->sq_sum[c] += (double)v * v;
            const int64_t mag = v < 0 ? -(int64_t)v : v;
            if (mag > stats->peak[c]) {
                stats->peak[c] = mag;
            }
            if (mag >= 32000) {
                stats->clip[c]++;
            }
        }
    }
    for (int i = 0; i < samples; i++) {
        if (mic0[i] == mic1[i]) {
            stats->identical_mic_samples++;
        }
    }
    stats->total_samples += samples;
}

static double rms_of(const channel_stats_t *stats, int channel)
{
    if (stats->total_samples == 0) {
        return 0.0;
    }
    return sqrt(stats->sq_sum[channel] / stats->total_samples);
}

/* Builds the 44-byte RIFF WAVE header for interleaved PCM16 data. */
static void wav_header(uint8_t hdr[44], size_t payload_bytes, int channels, int sample_rate)
{
    const uint32_t riff_size = 36 + (uint32_t)payload_bytes;
    const uint32_t fmt_size = 16;
    const uint16_t audio_format = 1;
    const uint32_t byte_rate = (uint32_t)sample_rate * channels * 2;
    const uint16_t block_align = (uint16_t)(channels * 2);
    const uint16_t bits = 16;
    const uint32_t payload = (uint32_t)payload_bytes;
    memcpy(hdr + 0, "RIFF", 4);
    memcpy(hdr + 4, &riff_size, 4);
    memcpy(hdr + 8, "WAVE", 4);
    memcpy(hdr + 12, "fmt ", 4);
    memcpy(hdr + 16, &fmt_size, 4);
    memcpy(hdr + 20, &audio_format, 2);
    memcpy(hdr + 22, &channels, 2);
    memcpy(hdr + 24, &sample_rate, 4);
    memcpy(hdr + 28, &byte_rate, 4);
    memcpy(hdr + 32, &block_align, 2);
    memcpy(hdr + 34, &bits, 2);
    memcpy(hdr + 36, "data", 4);
    memcpy(hdr + 40, &payload, 4);
}

static uint8_t wav_byte(const capture_buf_t *buf, size_t index)
{
    static uint8_t hdr[44];
    static const capture_buf_t *hdr_owner;
    if (hdr_owner != buf) {
        wav_header(hdr, buf->samples * buf->channels * 2, buf->channels, AUDIO_HW_SAMPLE_RATE);
        hdr_owner = (const capture_buf_t *)buf;
    }
    if (index < 44) {
        return hdr[index];
    }
    const size_t byte_index = index - 44;
    const uint16_t sample = (uint16_t)buf->data[byte_index / 2];
    return (byte_index % 2 == 0) ? (uint8_t)(sample & 0xff) : (uint8_t)(sample >> 8);
}

/* Dumps one capture as a complete WAV file over stdout using 72-char base64
 * rows prefixed with WAVD. Rows are emitted in batches with a tick of delay
 * between batches: the USB-Serial/JTAG console drops whole lines when its
 * TX buffer overflows under a per-line printf flood. */
/* Diagnostic: CRC of the full WAV image computed in an independent pass
 * before streaming, to cross-check the streaming CRC accumulation. */
static uint32_t precompute_crc(const capture_buf_t *buf, size_t total)
{
    uint32_t crc = 0;
    for (size_t i = 0; i < total; i++) {
        const uint8_t byte = wav_byte(buf, i);
        crc = esp_rom_crc32_le(crc, &byte, 1);
    }
    return crc;
}

static void dump_wav(const char *name, const capture_buf_t *buf)
{
    const size_t total = 44 + buf->samples * buf->channels * 2;
    printf("PHASE2A_WAV_BEGIN name=%s bytes=%u channels=%d rate=%d\n",
           name, (unsigned)total, buf->channels, AUDIO_HW_SAMPLE_RATE);
    fflush(stdout);

    static const char b64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    const int cols = 72;
    const int rows_per_batch = 12;
    /* "WAVD " prefix + row + newline + NUL per row. */
    char batch[rows_per_batch * (cols + 8) + 8];
    char *cursor = batch;
    uint32_t crc = 0;
    size_t emitted = 0;
    int col = 0;
    int rows_in_batch = 0;
    uint32_t acc = 0;
    int bits = 0;
    char row[cols + 1];

    for (size_t i = 0; i < total; i++) {
        const uint8_t byte = wav_byte(buf, i);
        crc = esp_rom_crc32_le(crc, &byte, 1);
        acc = (acc << 8) | byte;
        bits += 8;
        if (bits == 24) {
            row[col++] = b64[(acc >> 18) & 0x3f];
            row[col++] = b64[(acc >> 12) & 0x3f];
            row[col++] = b64[(acc >> 6) & 0x3f];
            row[col++] = b64[acc & 0x3f];
            acc = 0;
            bits = 0;
            if (col >= cols) {
                row[col] = 0;
                cursor += sprintf(cursor, "WAVD %s\n", row);
                emitted += (size_t)col;
                col = 0;
                rows_in_batch++;
                if (rows_in_batch == rows_per_batch) {
                    *cursor = 0;
                    fputs(batch, stdout);
                    fflush(stdout);
                    vTaskDelay(1);
                    cursor = batch;
                    rows_in_batch = 0;
                }
            }
        }
    }
    if (bits == 8) {
        const uint32_t v = acc << 4;
        row[col++] = b64[(v >> 18) & 0x3f];
        row[col++] = b64[(v >> 12) & 0x3f];
        row[col++] = '=';
        row[col++] = '=';
    } else if (bits == 16) {
        const uint32_t v = acc << 2;
        row[col++] = b64[(v >> 18) & 0x3f];
        row[col++] = b64[(v >> 12) & 0x3f];
        row[col++] = b64[(v >> 6) & 0x3f];
        row[col++] = '=';
    }
    if (col > 0) {
        row[col] = 0;
        cursor += sprintf(cursor, "WAVD %s\n", row);
        emitted += (size_t)col;
        rows_in_batch++;
    }
    if (rows_in_batch > 0) {
        *cursor = 0;
        fputs(batch, stdout);
        fflush(stdout);
    }
    printf("PHASE2A_WAV_END name=%s emitted=%u crc32=0x%08lx pre_crc=0x%08lx\n",
           name, (unsigned)emitted, (unsigned long)crc,
           (unsigned long)precompute_crc(buf, total));
    fflush(stdout);
}

static int16_t *alloc_psram(size_t samples_per_ch, int channels)
{
    void *p = heap_caps_malloc(samples_per_ch * channels * sizeof(int16_t), MALLOC_CAP_SPIRAM);
    if (p == NULL) {
        ESP_LOGE(TAG, "PSRAM alloc failed (%d ch x %d samples)", channels, (int)samples_per_ch);
    }
    return (int16_t *)p;
}

/* Plays the embedded stimulus once while capturing. When aec_out is given,
 * mic0 is additionally processed through AEC with the loopback reference. */
static esp_err_t stimulus_run(const char *label, aec_handle_t *aec, capture_buf_t *mic01,
                              capture_buf_t *raw_mic0, capture_buf_t *ref_buf, capture_buf_t *aec_out,
                              channel_stats_t *raw_stats, double *mean_erle_db)
{
    const int chunk = aec_get_chunksize(aec);
    if (chunk <= 0 || chunk > 1024) {
        ESP_LOGE(TAG, "invalid aec chunksize %d", chunk);
        return ESP_FAIL;
    }
    const size_t total_samples = AUDIO_STIMULUS_SAMPLE_COUNT
        + ((size_t)AUDIO_HW_SAMPLE_RATE * STIMULUS_TAIL_SILENCE_MS) / 1000;
    int16_t *mic0 = heap_caps_malloc((size_t)chunk * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *ref = heap_caps_malloc((size_t)chunk * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *mic1 = heap_caps_malloc((size_t)chunk * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *out = heap_caps_malloc((size_t)chunk * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *tx = heap_caps_malloc((size_t)chunk * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    if (!mic0 || !ref || !mic1 || !out || !tx) {
        return ESP_ERR_NO_MEM;
    }

    const int erle_window = AUDIO_HW_SAMPLE_RATE * ERLE_WINDOW_MS / 1000;
    double raw_sq = 0, out_sq = 0;
    int window_filled = 0;
    double erle_sum = 0.0;
    int erle_windows = 0;

    ESP_LOGI(TAG, "%s: chunk=%d total=%d samples (%.1f s)", label, chunk,
             (int)total_samples, (double)total_samples / AUDIO_HW_SAMPLE_RATE);

    size_t tx_pos = 0;
    size_t done = 0;
    while (done < total_samples) {
        const int n = (total_samples - done) > (size_t)chunk ? chunk : (int)(total_samples - done);
        if (audio_hw_read(mic0, ref, mic1, n) != ESP_OK) {
            return ESP_FAIL;
        }
        const size_t remain = AUDIO_STIMULUS_SAMPLE_COUNT > tx_pos
                                  ? AUDIO_STIMULUS_SAMPLE_COUNT - tx_pos : 0;
        const int tx_n = remain > (size_t)n ? n : (int)remain;
        if (tx_n > 0) {
            memcpy(tx, &audio_stimulus_pcm[tx_pos], (size_t)tx_n * sizeof(int16_t));
        }
        if (tx_n < n) {
            memset(tx + tx_n, 0, (size_t)(n - tx_n) * sizeof(int16_t));
        }
        tx_pos += (size_t)tx_n;
        if (audio_hw_write(tx, n) != ESP_OK) {
            return ESP_FAIL;
        }

        stats_update(raw_stats, mic0, ref, mic1, n);
        const int16_t *push01[2] = { mic0, mic1 };
        const int16_t *push_mic[1] = { mic0 };
        const int16_t *push_ref[1] = { ref };
        const int16_t *push_out[1] = { out };
        if (mic01 && !capture_push(mic01, push01, n)) return ESP_FAIL;
        if (raw_mic0 && !capture_push(raw_mic0, push_mic, n)) return ESP_FAIL;
        if (ref_buf && !capture_push(ref_buf, push_ref, n)) return ESP_FAIL;

        for (int i = 0; i < n; i++) {
            raw_sq += (double)mic0[i] * mic0[i];
        }
        if (aec_out != NULL) {
            aec_process(aec, mic0, ref, out);
            if (!capture_push(aec_out, push_out, n)) return ESP_FAIL;
            for (int i = 0; i < n; i++) {
                out_sq += (double)out[i] * out[i];
            }
        }
        /* ERLE windows are only counted while the stimulus is audible. */
        window_filled += n;
        if (window_filled >= erle_window) {
            const bool stimulus_active = tx_pos < AUDIO_STIMULUS_SAMPLE_COUNT;
            if (stimulus_active && raw_sq > 1.0) {
                erle_sum += 10.0 * log10(raw_sq / (out_sq > 1.0 ? out_sq : 1.0));
                erle_windows++;
            }
            raw_sq = 0;
            out_sq = 0;
            window_filled = 0;
        }
        done += (size_t)n;
    }
    *mean_erle_db = erle_windows > 0 ? erle_sum / erle_windows : 0.0;
    heap_caps_free(mic0);
    heap_caps_free(ref);
    heap_caps_free(mic1);
    heap_caps_free(out);
    heap_caps_free(tx);
    return ESP_OK;
}

static void log_channel_stats(const char *label, const channel_stats_t *stats)
{
    const double identical = stats->total_samples > 0
        ? 100.0 * stats->identical_mic_samples / stats->total_samples : 0.0;
    printf("PHASE2A_STAT run=%s mic0_rms=%.1f mic1_rms=%.1f ref_rms=%.1f "
           "mic0_peak=%lld mic1_peak=%lld ref_peak=%lld "
           "clip=%ld/%ld/%ld identical_mic0_mic1=%.4f%%\n",
           label, rms_of(stats, 0), rms_of(stats, 2), rms_of(stats, 1),
           (long long)stats->peak[0], (long long)stats->peak[2], (long long)stats->peak[1],
           (long)stats->clip[0], (long)stats->clip[2], (long)stats->clip[1], identical);
    fflush(stdout);
}

static void log_resource_line(const char *label, uint32_t frames)
{
    multi_heap_info_t internal = { 0 };
    heap_caps_get_info(&internal, MALLOC_CAP_INTERNAL);
    const size_t ps_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    printf("PHASE2A_STAB %s uptime_s=%lu free_int=%u largest_int=%u free_psram=%u frames=%lu wm=%u\n",
           label, (unsigned long)(xTaskGetTickCount() * portTICK_PERIOD_MS / 1000),
           (unsigned)internal.total_free_bytes, (unsigned)internal.largest_free_block,
           (unsigned)ps_free, (unsigned long)frames,
           (unsigned)uxTaskGetStackHighWaterMark(NULL));
    fflush(stdout);
}

static esp_err_t run_selftest_sequence(void)
{
    s_selftest_busy = true;
    printf("PHASE2A_SEQ selftest_begin\n");
    fflush(stdout);
    esp_err_t err = audio_hw_init();
    if (err == ESP_OK) {
        err = audio_hw_input_enable(true);
    }
    if (err == ESP_OK) {
        err = audio_hw_output_enable(true);
    }
    if (err != ESP_OK) {
        s_selftest_busy = false;
        return err;
    }

    const size_t cap = AUDIO_STIMULUS_SAMPLE_COUNT
        + ((size_t)AUDIO_HW_SAMPLE_RATE * STIMULUS_TAIL_SILENCE_MS) / 1000;

    int16_t *mic01_ps = alloc_psram(cap, 2);
    int16_t *raw_ps = alloc_psram(cap, 1);
    int16_t *ref_ps = alloc_psram(cap, 1);
    int16_t *aec_ps = alloc_psram(cap, 1);
    if (!mic01_ps || !raw_ps || !ref_ps || !aec_ps) {
        s_selftest_busy = false;
        return ESP_ERR_NO_MEM;
    }
    capture_buf_t mic01 = { 0 }, raw = { 0 }, ref = { 0 }, aec_on = { 0 };
    capture_reset(&mic01, mic01_ps, cap, 2);
    capture_reset(&raw, raw_ps, cap, 1);
    capture_reset(&ref, ref_ps, cap, 1);
    capture_reset(&aec_on, aec_ps, cap, 1);

    aec_handle_t *aec = aec_create(AUDIO_HW_SAMPLE_RATE, 4, 1, AEC_MODE_VOIP_HIGH_PERF);
    if (aec == NULL) {
        ESP_LOGE(TAG, "aec_create failed");
        s_selftest_busy = false;
        return ESP_FAIL;
    }
    printf("PHASE2A_AEC chunk=%d mode=%s\n", aec_get_chunksize(aec),
           aec_get_mode_string(AEC_MODE_VOIP_HIGH_PERF));
    fflush(stdout);

    channel_stats_t stats_off = { 0 };
    double unused_erle = 0;
    err = stimulus_run("aec_off", aec, &mic01, &raw, &ref, NULL, &stats_off, &unused_erle);
    if (err == ESP_OK) {
        log_channel_stats("aec_off", &stats_off);
        channel_stats_t stats_on = { 0 };
        double erle = 0;
        err = stimulus_run("aec_on", aec, NULL, NULL, NULL, &aec_on, &stats_on, &erle);
        if (err == ESP_OK) {
            log_channel_stats("aec_on", &stats_on);
            printf("PHASE2A_ERLE mean_window_db=%.2f\n", erle);
            fflush(stdout);
            dump_wav("mic0_mic1", &mic01);
            dump_wav("mic0_mic1_b", &mic01);
            dump_wav("playback_reference", &ref);
            dump_wav("aec_off", &raw);
            dump_wav("aec_on", &aec_on);
            printf("PHASE2A_SEQ selftest_end PASS\n");
            fflush(stdout);
        }
    }

    heap_caps_free(mic01_ps);
    heap_caps_free(raw_ps);
    heap_caps_free(ref_ps);
    heap_caps_free(aec_ps);
    aec_destroy(aec);
    s_selftest_busy = false;
    return err;
}

static void audio_task(void *arg)
{
    /* Let Wi-Fi join and the stock service take its first snapshot first. */
    vTaskDelay(pdMS_TO_TICKS(8000));

    if (run_selftest_sequence() != ESP_OK) {
        printf("PHASE2A_SEQ selftest_end FAIL\n");
        fflush(stdout);
    }

    /* Stability loop: keep RX + AEC + TX continuously active. */
    aec_handle_t *aec = aec_create(AUDIO_HW_SAMPLE_RATE, 4, 1, AEC_MODE_VOIP_HIGH_PERF);
    int chunk = aec != NULL ? aec_get_chunksize(aec) : 0;
    if (chunk <= 0) {
        ESP_LOGE(TAG, "stability aec unavailable");
        chunk = 320;
    }
    int16_t *mic0 = heap_caps_malloc(1024 * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *ref = heap_caps_malloc(1024 * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *mic1 = heap_caps_malloc(1024 * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *out = heap_caps_malloc(1024 * sizeof(int16_t), MALLOC_CAP_INTERNAL);
    int16_t *silence = heap_caps_calloc(1024, sizeof(int16_t), MALLOC_CAP_INTERNAL);
    TickType_t last_log = xTaskGetTickCount();
    uint32_t frames = 0;
    bool buffers_ok = mic0 && ref && mic1 && out && silence;

    while (buffers_ok) {
        if (xEventGroupGetBits(s_events) & RERUN_BIT) {
            xEventGroupClearBits(s_events, RERUN_BIT);
            if (!s_selftest_busy && aec != NULL) {
                aec_destroy(aec);
                aec = NULL;
            }
            if (!s_selftest_busy) {
                run_selftest_sequence();
                aec = aec_create(AUDIO_HW_SAMPLE_RATE, 4, 1, AEC_MODE_VOIP_HIGH_PERF);
            }
        }
        if (audio_hw_read(mic0, ref, mic1, chunk) == ESP_OK) {
            if (aec != NULL) {
                aec_process(aec, mic0, ref, out);
            }
            audio_hw_write(silence, chunk);
            frames++;
        }
        if ((xTaskGetTickCount() - last_log) >= pdMS_TO_TICKS(STABILITY_LOG_PERIOD_S * 1000)) {
            log_resource_line("tick", frames);
            last_log = xTaskGetTickCount();
        }
    }
    ESP_LOGE(TAG, "stability loop buffers missing; task exiting");
    vTaskDelete(NULL);
}

esp_err_t audio_selftest_start(void)
{
    if (s_events == NULL) {
        s_events = xEventGroupCreateStatic(&s_event_group);
    }
    ESP_RETURN_ON_FALSE(s_events != NULL, ESP_ERR_NO_MEM, TAG, "event group");
    const BaseType_t ok = xTaskCreate(audio_task, "audio_p2a", AUDIO_TASK_STACK_BYTES,
                                      NULL, AUDIO_TASK_PRIORITY, NULL);
    return ok == pdPASS ? ESP_OK : ESP_FAIL;
}

void audio_selftest_request_rerun(void)
{
    if (s_events != NULL) {
        xEventGroupSetBits(s_events, RERUN_BIT);
        ESP_LOGI(TAG, "BOOT press: self-test rerun requested");
    }
}

void audio_selftest_toggle_volume(void)
{
    s_volume_muted = !s_volume_muted;
    audio_hw_set_output_volume(s_volume_muted ? 0 : 70);
    ESP_LOGI(TAG, "BOOT double press: volume %d", s_volume_muted ? 0 : 70);
}
