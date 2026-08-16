#include "board.h"

#include <stdbool.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_log.h"

static const char *TAG = "board_button";
static const TickType_t DEBOUNCE_TICKS = pdMS_TO_TICKS(50);
static const TickType_t DOUBLE_PRESS_TICKS = pdMS_TO_TICKS(400);
static QueueHandle_t s_button_events;
static board_button_callback_t s_callback;

static void IRAM_ATTR boot_button_isr(void *arg)
{
    const uint32_t event = (uint32_t)(uintptr_t)arg;
    BaseType_t task_woken = pdFALSE;
    xQueueSendFromISR(s_button_events, &event, &task_woken);
    if (task_woken) {
        portYIELD_FROM_ISR();
    }
}

static void boot_button_task(void *arg)
{
    uint32_t event = 0;
    TickType_t last_press = 0;
    bool have_last_press = false;

    while (true) {
        if (xQueueReceive(s_button_events, &event, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        const TickType_t now = xTaskGetTickCount();
        if (have_last_press && (now - last_press) < DEBOUNCE_TICKS) {
            continue;
        }

        /* Confirm the active-low level after the debounce window. */
        vTaskDelay(DEBOUNCE_TICKS);
        if (gpio_get_level(BOARD_BOOT_BUTTON_GPIO) != 0) {
            last_press = now;
            have_last_press = true;
            continue;
        }

        /*
         * Wait briefly for a second confirmed press to classify the event as
         * a double press; otherwise report a single press.
         */
        board_button_event_t kind = BOARD_BUTTON_PRESS;
        while ((xTaskGetTickCount() - now) < DOUBLE_PRESS_TICKS) {
            TickType_t probe_at = xTaskGetTickCount();
            if (xQueueReceive(s_button_events, &event,
                              DOUBLE_PRESS_TICKS - (probe_at - now)) == pdTRUE) {
                if (gpio_get_level(BOARD_BOOT_BUTTON_GPIO) == 0) {
                    kind = BOARD_BUTTON_DOUBLE_PRESS;
                    break;
                }
            }
        }

        last_press = xTaskGetTickCount();
        have_last_press = true;
        if (kind == BOARD_BUTTON_DOUBLE_PRESS) {
            ESP_LOGI(TAG, "BOOT double press");
        } else {
            ESP_LOGI(TAG, "BOOT press");
        }
        s_callback(kind);
    }
}

esp_err_t board_button_init(board_button_callback_t callback)
{
    ESP_RETURN_ON_FALSE(callback != NULL, ESP_ERR_INVALID_ARG, TAG, "callback is required");

    s_callback = callback;
    s_button_events = xQueueCreate(4, sizeof(uint32_t));
    ESP_RETURN_ON_FALSE(s_button_events != NULL, ESP_ERR_NO_MEM, TAG, "button queue allocation failed");

    const gpio_config_t config = {
        .pin_bit_mask = 1ULL << BOARD_BOOT_BUTTON_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&config), TAG, "BOOT GPIO configuration failed");
    ESP_RETURN_ON_ERROR(gpio_install_isr_service(0), TAG, "GPIO ISR service setup failed");
    ESP_RETURN_ON_ERROR(gpio_isr_handler_add(BOARD_BOOT_BUTTON_GPIO, boot_button_isr,
                                             (void *)(uintptr_t)BOARD_BOOT_BUTTON_GPIO),
                        TAG, "BOOT ISR registration failed");

    const BaseType_t task_created = xTaskCreate(boot_button_task, "boot_button", 3072,
                                                 NULL, 5, NULL);
    ESP_RETURN_ON_FALSE(task_created == pdPASS, ESP_ERR_NO_MEM, TAG, "button task allocation failed");
    ESP_LOGI(TAG, "BOOT button ready on GPIO %d", BOARD_BOOT_BUTTON_GPIO);
    return ESP_OK;
}
