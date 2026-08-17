#include "stock_gateway_client.h"

#include <stdio.h>
#include <string.h>

#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "stock_gateway_parser.h"

static const char *TAG = "stock-http";
static const size_t MAX_RESPONSE_BYTES = 128U * 1024U;

esp_err_t stock_gateway_fetch(stock_dashboard_t *dashboard, size_t *response_bytes)
{
    if (dashboard == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    char url[256];
    const int url_length = snprintf(
        url, sizeof(url), "%s/api/v1/dashboard/%s?intraday_samples=%u",
        CONFIG_STOCK_GATEWAY_BASE_URL, CONFIG_STOCK_GATEWAY_DEVICE_ID,
        (unsigned)STOCK_INTRADAY_SAMPLES);
    if (url_length <= 0 || (size_t)url_length >= sizeof(url)) {
        return ESP_ERR_INVALID_SIZE;
    }

    const esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = CONFIG_STOCK_GATEWAY_TIMEOUT_MS,
        .buffer_size = 4096,
        .buffer_size_tx = 512,
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == NULL) {
        return ESP_ERR_NO_MEM;
    }
    esp_http_client_set_header(client, "Accept", "application/json");

    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        esp_http_client_cleanup(client);
        return err;
    }
    const int64_t content_length = esp_http_client_fetch_headers(client);
    const int status = esp_http_client_get_status_code(client);
    if (content_length <= 0 || content_length > (int64_t)MAX_RESPONSE_BYTES ||
        status != 200) {
        ESP_LOGW(TAG, "gateway rejected status=%d content_length=%lld", status,
                 (long long)content_length);
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return status == 200 ? ESP_ERR_INVALID_SIZE : ESP_ERR_HTTP_BASE;
    }

    char *body = heap_caps_malloc((size_t)content_length + 1,
                                  MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (body == NULL) {
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return ESP_ERR_NO_MEM;
    }
    const int read = esp_http_client_read_response(client, body, (int)content_length);
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    if (read != content_length) {
        heap_caps_free(body);
        return read < 0 ? ESP_FAIL : ESP_ERR_INVALID_SIZE;
    }
    body[read] = '\0';

    const stock_gateway_parse_result_t parsed =
        stock_gateway_parse_dashboard(body, (size_t)read, dashboard);
    heap_caps_free(body);
    if (parsed != STOCK_GATEWAY_PARSE_OK) {
        ESP_LOGW(TAG, "gateway payload rejected: %s",
                 stock_gateway_parse_result_text(parsed));
        return ESP_ERR_INVALID_RESPONSE;
    }
    if (response_bytes != NULL) {
        *response_bytes = (size_t)read;
    }
    return ESP_OK;
}
