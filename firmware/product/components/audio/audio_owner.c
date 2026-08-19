#include "audio_owner.h"

#include "esp_check.h"
#include "esp_log.h"
#include "freertos/semphr.h"

static const char *TAG = "audio_owner";

static SemaphoreHandle_t s_mu;
static StaticSemaphore_t s_mu_buf;
static audio_owner_id_t s_current = AUDIO_OWNER_NONE;
static audio_owner_id_t s_wanted = AUDIO_OWNER_NONE;

esp_err_t audio_owner_init(void)
{
    if (s_mu == NULL) {
        s_mu = xSemaphoreCreateMutexStatic(&s_mu_buf);
    }
    return s_mu != NULL ? ESP_OK : ESP_ERR_NO_MEM;
}

void audio_owner_request(audio_owner_id_t id)
{
    if (s_mu == NULL || id == AUDIO_OWNER_NONE) {
        return;
    }
    if (xSemaphoreTake(s_mu, portMAX_DELAY) == pdTRUE) {
        s_wanted = id;
        xSemaphoreGive(s_mu);
    }
}

esp_err_t audio_owner_acquire(audio_owner_id_t id, TickType_t timeout)
{
    ESP_RETURN_ON_FALSE(s_mu != NULL, ESP_ERR_INVALID_STATE, TAG, "owner not init");
    ESP_RETURN_ON_FALSE(id != AUDIO_OWNER_NONE, ESP_ERR_INVALID_ARG, TAG, "owner");
    const TickType_t start = xTaskGetTickCount();
    while (true) {
        if (xSemaphoreTake(s_mu, portMAX_DELAY) != pdTRUE) {
            return ESP_FAIL;
        }
        if (s_current == AUDIO_OWNER_NONE || s_current == id) {
            s_current = id;
            s_wanted = id;
            xSemaphoreGive(s_mu);
            return ESP_OK;
        }
        xSemaphoreGive(s_mu);
        if (timeout != portMAX_DELAY) {
            const TickType_t elapsed = xTaskGetTickCount() - start;
            if (elapsed >= timeout) {
                return ESP_ERR_TIMEOUT;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

esp_err_t audio_owner_release(audio_owner_id_t id)
{
    ESP_RETURN_ON_FALSE(s_mu != NULL, ESP_ERR_INVALID_STATE, TAG, "owner not init");
    if (xSemaphoreTake(s_mu, portMAX_DELAY) != pdTRUE) {
        return ESP_FAIL;
    }
    if (s_current != id) {
        xSemaphoreGive(s_mu);
        return ESP_ERR_INVALID_STATE;
    }
    s_current = AUDIO_OWNER_NONE;
    if (s_wanted == id) {
        s_wanted = AUDIO_OWNER_NONE;
    }
    xSemaphoreGive(s_mu);
    ESP_LOGI(TAG, "released %d", (int)id);
    return ESP_OK;
}

audio_owner_id_t audio_owner_current(void)
{
    audio_owner_id_t current = AUDIO_OWNER_NONE;
    if (s_mu != NULL && xSemaphoreTake(s_mu, portMAX_DELAY) == pdTRUE) {
        current = s_current;
        xSemaphoreGive(s_mu);
    }
    return current;
}

bool audio_owner_is(audio_owner_id_t id)
{
    return audio_owner_current() == id;
}

bool audio_owner_should_yield(audio_owner_id_t id)
{
    bool yield = false;
    if (s_mu != NULL && xSemaphoreTake(s_mu, portMAX_DELAY) == pdTRUE) {
        yield = s_current == id && s_wanted != AUDIO_OWNER_NONE && s_wanted != id;
        xSemaphoreGive(s_mu);
    }
    return yield;
}
