/*
 * Minimal ESP-IDF Wi-Fi station bootstrap. This component owns only local
 * NVS-backed station configuration and connection state. It has no captive
 * portal, cloud activation, OTA, WebSocket, MQTT, or application protocol.
 */
#include "network.h"

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_smartconfig.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "network";
static const uint8_t MAX_CONNECT_RETRIES = 5;
static network_status_callback_t s_status_callback;
static bool s_has_station_credentials;
static bool s_smartconfig_running;
static uint8_t s_connect_retries;
static volatile bool s_connected;

bool network_is_connected(void)
{
    return s_connected;
}

static void report_status(network_status_t status)
{
    if (s_status_callback != NULL) {
        s_status_callback(status);
    }
}

const char *network_status_text(network_status_t status)
{
    switch (status) {
    case NETWORK_STATUS_STARTING:
        return "Starting";
    case NETWORK_STATUS_CONNECTING:
        return "Connecting";
    case NETWORK_STATUS_CONNECTED:
        return "Connected";
    case NETWORK_STATUS_DISCONNECTED:
        return "Disconnected";
    case NETWORK_STATUS_PROVISIONING:
        return "Provisioning";
    case NETWORK_STATUS_UNCONFIGURED:
        return "Unconfigured";
    default:
        return "Unknown";
    }
}

static void smartconfig_task(void *arg)
{
    (void)arg;
    esp_err_t err = esp_smartconfig_set_type(SC_TYPE_ESPTOUCH_AIRKISS);
    if (err == ESP_OK) {
        const smartconfig_start_config_t config = SMARTCONFIG_START_CONFIG_DEFAULT();
        err = esp_smartconfig_start(&config);
    }
    if (err != ESP_OK) {
        s_smartconfig_running = false;
        ESP_LOGE(TAG, "SmartConfig start failed: %s", esp_err_to_name(err));
        report_status(NETWORK_STATUS_UNCONFIGURED);
    } else {
        ESP_LOGI(TAG, "SmartConfig provisioning started");
    }
    vTaskDelete(NULL);
}

static void start_smartconfig(void)
{
    if (s_smartconfig_running) {
        return;
    }
    s_smartconfig_running = true;
    report_status(NETWORK_STATUS_PROVISIONING);
    if (xTaskCreate(smartconfig_task, "smartconfig", 4096, NULL, 3, NULL) != pdPASS) {
        s_smartconfig_running = false;
        ESP_LOGE(TAG, "SmartConfig task allocation failed");
        report_status(NETWORK_STATUS_UNCONFIGURED);
    }
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    (void)arg;
    (void)event_data;

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        s_connected = false;
        if (s_has_station_credentials) {
            s_connect_retries = 0;
            report_status(NETWORK_STATUS_CONNECTING);
            ESP_ERROR_CHECK_WITHOUT_ABORT(esp_wifi_connect());
        } else {
            ESP_LOGW(TAG, "Wi-Fi station has no configured credentials; starting provisioning");
            start_smartconfig();
        }
        return;
    }

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        s_connected = false;
        if (s_has_station_credentials && s_connect_retries < MAX_CONNECT_RETRIES) {
            ++s_connect_retries;
            ESP_LOGW(TAG, "Wi-Fi disconnected; retry %u of %u", s_connect_retries,
                     MAX_CONNECT_RETRIES);
            report_status(NETWORK_STATUS_CONNECTING);
            ESP_ERROR_CHECK_WITHOUT_ABORT(esp_wifi_connect());
        } else {
            ESP_LOGW(TAG, "Wi-Fi remains disconnected");
            report_status(NETWORK_STATUS_DISCONNECTED);
        }
        return;
    }

    if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        s_connect_retries = 0;
        s_connected = true;
        /* Deliberately do not log the assigned address or station identity. */
        ESP_LOGI(TAG, "Wi-Fi station connected");
        report_status(NETWORK_STATUS_CONNECTED);
        return;
    }

    if (event_base == SC_EVENT && event_id == SC_EVENT_GOT_SSID_PSWD) {
        const smartconfig_event_got_ssid_pswd_t *credentials = event_data;
        wifi_config_t station_config = {0};
        memcpy(station_config.sta.ssid, credentials->ssid, sizeof(station_config.sta.ssid));
        memcpy(station_config.sta.password, credentials->password,
               sizeof(station_config.sta.password));
        station_config.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
        ESP_LOGI(TAG, "SmartConfig received station credentials");
        ESP_ERROR_CHECK_WITHOUT_ABORT(esp_wifi_disconnect());
        esp_err_t err = esp_wifi_set_config(WIFI_IF_STA, &station_config);
        memset(&station_config, 0, sizeof(station_config));
        if (err == ESP_OK) {
            s_has_station_credentials = true;
            s_connect_retries = 0;
            report_status(NETWORK_STATUS_CONNECTING);
            ESP_ERROR_CHECK_WITHOUT_ABORT(esp_wifi_connect());
        } else {
            ESP_LOGE(TAG, "SmartConfig credential storage failed: %s", esp_err_to_name(err));
            report_status(NETWORK_STATUS_UNCONFIGURED);
        }
        return;
    }

    if (event_base == SC_EVENT && event_id == SC_EVENT_SEND_ACK_DONE) {
        ESP_ERROR_CHECK_WITHOUT_ABORT(esp_smartconfig_stop());
        s_smartconfig_running = false;
        ESP_LOGI(TAG, "SmartConfig provisioning completed");
    }
}

static esp_err_t initialize_nvs(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS requires initialization recovery");
        ESP_RETURN_ON_ERROR(nvs_flash_erase(), TAG, "NVS recovery erase failed");
        err = nvs_flash_init();
    }
    return err;
}

static esp_err_t import_reference_credentials(wifi_config_t *station_config)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open("wifi", NVS_READONLY, &handle);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        return ESP_ERR_NOT_FOUND;
    }
    ESP_RETURN_ON_ERROR(err, TAG, "reference Wi-Fi NVS open failed");

    char ssid[sizeof(station_config->sta.ssid) + 1] = {0};
    char password[sizeof(station_config->sta.password) + 1] = {0};
    size_t ssid_length = sizeof(ssid);
    size_t password_length = sizeof(password);
    err = nvs_get_str(handle, "ssid", ssid, &ssid_length);
    if (err == ESP_OK) {
        err = nvs_get_str(handle, "password", password, &password_length);
    }
    nvs_close(handle);
    if (err != ESP_OK || ssid[0] == '\0') {
        memset(password, 0, sizeof(password));
        return ESP_ERR_NOT_FOUND;
    }

    snprintf((char *)station_config->sta.ssid, sizeof(station_config->sta.ssid), "%s", ssid);
    snprintf((char *)station_config->sta.password, sizeof(station_config->sta.password), "%s",
             password);
    station_config->sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    memset(password, 0, sizeof(password));
    ESP_LOGI(TAG, "Imported one station credential from the frozen reference NVS schema");
    return ESP_OK;
}

static esp_err_t configure_station_credentials(void)
{
    wifi_config_t station_config = {0};

    /* ESP-IDF keeps previously provisioned station settings in its Wi-Fi NVS namespace. */
    ESP_RETURN_ON_ERROR(esp_wifi_get_config(WIFI_IF_STA, &station_config), TAG,
                        "stored Wi-Fi configuration read failed");
    s_has_station_credentials = station_config.sta.ssid[0] != '\0';
    if (s_has_station_credentials) {
        ESP_LOGI(TAG, "Wi-Fi station will use stored credentials");
        return ESP_OK;
    }

    esp_err_t err = import_reference_credentials(&station_config);
    if (err == ESP_OK) {
        ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &station_config), TAG,
                            "reference Wi-Fi credential import failed");
        memset(&station_config, 0, sizeof(station_config));
        s_has_station_credentials = true;
        return ESP_OK;
    }
    if (err != ESP_ERR_NOT_FOUND) {
        return err;
    }
    ESP_LOGW(TAG, "Wi-Fi is unconfigured; runtime provisioning is required");
    return ESP_OK;
}

esp_err_t network_init(network_status_callback_t callback)
{
    ESP_RETURN_ON_FALSE(callback != NULL, ESP_ERR_INVALID_ARG, TAG, "status callback is required");
    s_status_callback = callback;
    report_status(NETWORK_STATUS_STARTING);

    ESP_RETURN_ON_ERROR(initialize_nvs(), TAG, "NVS initialization failed");
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "network interface initialization failed");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG, "default event loop initialization failed");
    ESP_RETURN_ON_FALSE(esp_netif_create_default_wifi_sta() != NULL, ESP_ERR_NO_MEM, TAG,
                        "default station interface allocation failed");

    const wifi_init_config_t wifi_init_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&wifi_init_config), TAG, "Wi-Fi driver initialization failed");
    ESP_RETURN_ON_ERROR(esp_wifi_set_storage(WIFI_STORAGE_FLASH), TAG, "Wi-Fi storage setup failed");
    ESP_RETURN_ON_ERROR(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                                             &wifi_event_handler, NULL, NULL),
                        TAG, "Wi-Fi event handler setup failed");
    ESP_RETURN_ON_ERROR(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                                             &wifi_event_handler, NULL, NULL),
                        TAG, "IP event handler setup failed");
    ESP_RETURN_ON_ERROR(esp_event_handler_instance_register(SC_EVENT, ESP_EVENT_ANY_ID,
                                                             &wifi_event_handler, NULL, NULL),
                        TAG, "SmartConfig event handler setup failed");
    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG, "station mode setup failed");
    ESP_RETURN_ON_ERROR(configure_station_credentials(), TAG, "station credential setup failed");
    ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "Wi-Fi station start failed");

    ESP_LOGI(TAG, "Wi-Fi station initialized");
    return ESP_OK;
}
