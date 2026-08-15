/*
 * ST7305 RLCD transport and minimal LVGL page for the Waveshare
 * ESP32-S3-RLCD-4.2.
 *
 * Provenance: the controller command sequence and the landscape pixel mapping
 * below were independently adapted from the board-only portions of the fixed
 * Xiaozhi v2.4.2 reference at
 * firmware/xiaozhi/main/boards/waveshare/esp32-s3-rlcd-4.2/
 * custom_lcd_display.cc. This implementation deliberately does not include
 * any Xiaozhi Display, Application, asset, or protocol code.
 */
#include "display.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "board.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_check.h"
#include "esp_heap_caps.h"
#include "esp_lcd_io_spi.h"
#include "esp_lcd_panel_io.h"
#include "esp_log.h"
#include "esp_lvgl_port.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lvgl.h"

static const char *TAG = "rlcd";
static const size_t RLCD_FRAMEBUFFER_SIZE = (BOARD_RLCD_WIDTH * BOARD_RLCD_HEIGHT) / 8U;
static const size_t DRAW_BUFFER_LINES = 40U;
static const size_t DRAW_BUFFER_SIZE = BOARD_RLCD_WIDTH * DRAW_BUFFER_LINES * sizeof(uint16_t);

typedef struct {
    esp_lcd_panel_io_handle_t io;
    uint8_t *framebuffer;
    lv_display_t *lv_display;
    lv_obj_t *psram_label;
    lv_obj_t *wifi_label;
    lv_obj_t *button_label;
} rlcd_state_t;

static rlcd_state_t s_rlcd;

/* Full-frame flush counters, shared between the LVGL task and readers. */
static portMUX_TYPE s_flush_metrics_mux = portMUX_INITIALIZER_UNLOCKED;
static display_flush_metrics_t s_flush_metrics;

static void record_flush_us(int64_t duration_us)
{
    portENTER_CRITICAL(&s_flush_metrics_mux);
    s_flush_metrics.flush_count += 1U;
    s_flush_metrics.flush_total_us += (uint64_t)(duration_us > 0 ? duration_us : 0);
    if ((uint32_t)duration_us > s_flush_metrics.flush_max_us) {
        s_flush_metrics.flush_max_us = (uint32_t)duration_us;
    }
    portEXIT_CRITICAL(&s_flush_metrics_mux);
}

static esp_err_t rlcd_send_command(uint8_t command)
{
    return esp_lcd_panel_io_tx_param(s_rlcd.io, command, NULL, 0);
}

static esp_err_t rlcd_send_data(uint8_t data)
{
    return esp_lcd_panel_io_tx_param(s_rlcd.io, -1, &data, 1);
}

static esp_err_t rlcd_send_sequence(uint8_t command, const uint8_t *data, size_t length)
{
    ESP_RETURN_ON_ERROR(rlcd_send_command(command), TAG, "RLCD command 0x%02x failed", command);
    for (size_t index = 0; index < length; ++index) {
        ESP_RETURN_ON_ERROR(rlcd_send_data(data[index]), TAG, "RLCD data for 0x%02x failed", command);
    }
    return ESP_OK;
}

static esp_err_t rlcd_reset(void)
{
    ESP_RETURN_ON_ERROR(gpio_set_level(BOARD_RLCD_RST_GPIO, 1), TAG, "RLCD reset high failed");
    vTaskDelay(pdMS_TO_TICKS(50));
    ESP_RETURN_ON_ERROR(gpio_set_level(BOARD_RLCD_RST_GPIO, 0), TAG, "RLCD reset low failed");
    vTaskDelay(pdMS_TO_TICKS(20));
    ESP_RETURN_ON_ERROR(gpio_set_level(BOARD_RLCD_RST_GPIO, 1), TAG, "RLCD reset release failed");
    vTaskDelay(pdMS_TO_TICKS(50));
    return ESP_OK;
}

static esp_err_t rlcd_init_controller(void)
{
    /*
     * This is the known-working ST7305 sequence from the Phase 1B reference.
     * The command order and values are preserved to avoid changing panel
     * electrical timing during this bootstrap phase.
     */
    static const uint8_t d6[] = {0x17, 0x02};
    static const uint8_t d1[] = {0x01};
    static const uint8_t c0[] = {0x11, 0x04};
    static const uint8_t c1[] = {0x69, 0x69, 0x69, 0x69};
    static const uint8_t c2[] = {0x19, 0x19, 0x19, 0x19};
    static const uint8_t c4[] = {0x4b, 0x4b, 0x4b, 0x4b};
    static const uint8_t c5[] = {0x19, 0x19, 0x19, 0x19};
    static const uint8_t d8[] = {0x80, 0xe9};
    static const uint8_t b2[] = {0x02};
    static const uint8_t b3[] = {0xe5, 0xf6, 0x05, 0x46, 0x77, 0x77, 0x77, 0x77, 0x76, 0x45};
    static const uint8_t b4[] = {0x05, 0x46, 0x77, 0x77, 0x77, 0x77, 0x76, 0x45};
    static const uint8_t p62[] = {0x32, 0x03, 0x1f};
    static const uint8_t b7[] = {0x13};
    static const uint8_t b0[] = {0x64};
    static const uint8_t c9[] = {0x00};
    static const uint8_t p36[] = {0x48};
    static const uint8_t p3a[] = {0x11};
    static const uint8_t b9[] = {0x20};
    static const uint8_t b8[] = {0x29};
    static const uint8_t p2a[] = {0x12, 0x2a};
    static const uint8_t p2b[] = {0x00, 0xc7};
    static const uint8_t p35[] = {0x00};
    static const uint8_t d0[] = {0xff};

    ESP_RETURN_ON_ERROR(rlcd_reset(), TAG, "RLCD reset failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xd6, d6, sizeof(d6)), TAG, "RLCD NVM load setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xd1, d1, sizeof(d1)), TAG, "RLCD booster setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xc0, c0, sizeof(c0)), TAG, "RLCD gate voltage setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xc1, c1, sizeof(c1)), TAG, "RLCD VSHP setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xc2, c2, sizeof(c2)), TAG, "RLCD C2 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xc4, c4, sizeof(c4)), TAG, "RLCD C4 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xc5, c5, sizeof(c5)), TAG, "RLCD C5 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xd8, d8, sizeof(d8)), TAG, "RLCD D8 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xb2, b2, sizeof(b2)), TAG, "RLCD B2 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xb3, b3, sizeof(b3)), TAG, "RLCD B3 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xb4, b4, sizeof(b4)), TAG, "RLCD B4 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0x62, p62, sizeof(p62)), TAG, "RLCD 62 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xb7, b7, sizeof(b7)), TAG, "RLCD B7 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xb0, b0, sizeof(b0)), TAG, "RLCD B0 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_command(0x11), TAG, "RLCD sleep-out failed");
    vTaskDelay(pdMS_TO_TICKS(200));
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xc9, c9, sizeof(c9)), TAG, "RLCD C9 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0x36, p36, sizeof(p36)), TAG, "RLCD orientation setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0x3a, p3a, sizeof(p3a)), TAG, "RLCD pixel format setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xb9, b9, sizeof(b9)), TAG, "RLCD B9 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xb8, b8, sizeof(b8)), TAG, "RLCD B8 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_command(0x21), TAG, "RLCD inversion setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0x2a, p2a, sizeof(p2a)), TAG, "RLCD column range setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0x2b, p2b, sizeof(p2b)), TAG, "RLCD page range setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0x35, p35, sizeof(p35)), TAG, "RLCD tearing setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_sequence(0xd0, d0, sizeof(d0)), TAG, "RLCD D0 setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_command(0x38), TAG, "RLCD display-off setup failed");
    ESP_RETURN_ON_ERROR(rlcd_send_command(0x29), TAG, "RLCD display-on setup failed");

    memset(s_rlcd.framebuffer, 0xff, RLCD_FRAMEBUFFER_SIZE);
    return ESP_OK;
}

static void rlcd_set_pixel(uint16_t x, uint16_t y, bool white)
{
    /* Exact algebraic form of the v2.4.2 landscape LUT mapping. */
    const uint16_t inverted_y = BOARD_RLCD_HEIGHT - 1U - y;
    const size_t byte_index = (x >> 1U) * (BOARD_RLCD_HEIGHT >> 2U) + (inverted_y >> 2U);
    const uint8_t bit = 7U - (((inverted_y & 0x3U) << 1U) | (x & 0x1U));
    const uint8_t mask = 1U << bit;

    if (white) {
        s_rlcd.framebuffer[byte_index] |= mask;
    } else {
        s_rlcd.framebuffer[byte_index] &= (uint8_t)~mask;
    }
}

static void rlcd_flush_cb(lv_display_t *display, const lv_area_t *area, uint8_t *pixel_bytes)
{
    const uint16_t *pixels = (const uint16_t *)pixel_bytes;
    const int32_t width = lv_area_get_width(area);

    for (int32_t y = area->y1; y <= area->y2; ++y) {
        for (int32_t x = area->x1; x <= area->x2; ++x) {
            const size_t pixel_index = (size_t)(y - area->y1) * (size_t)width + (size_t)(x - area->x1);
            /* Preserve the v2.4.2 RGB565 threshold for the 1-bit RLCD frame. */
            const bool white = pixels[pixel_index] >= 0x7fffU;
            rlcd_set_pixel((uint16_t)x, (uint16_t)y, white);
        }
    }

    static const uint8_t column_range[] = {0x12, 0x2a};
    static const uint8_t page_range[] = {0x00, 0xc7};
    const int64_t flush_started_us = esp_timer_get_time();
    ESP_ERROR_CHECK(rlcd_send_sequence(0x2a, column_range, sizeof(column_range)));
    ESP_ERROR_CHECK(rlcd_send_sequence(0x2b, page_range, sizeof(page_range)));
    ESP_ERROR_CHECK(rlcd_send_command(0x2c));
    ESP_ERROR_CHECK(esp_lcd_panel_io_tx_color(s_rlcd.io, -1, s_rlcd.framebuffer, RLCD_FRAMEBUFFER_SIZE));
    record_flush_us(esp_timer_get_time() - flush_started_us);
    lv_display_flush_ready(display);
}

static lv_obj_t *create_label(lv_obj_t *parent, const char *text, int16_t x, int16_t y)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_pos(label, x, y);
    lv_obj_set_style_text_color(label, lv_color_black(), 0);
    return label;
}

static void create_bootstrap_page(void)
{
    lv_obj_t *screen = lv_screen_active();
    lv_obj_set_style_bg_color(screen, lv_color_white(), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    lv_obj_t *title = create_label(screen, "ESP32-S3 Dashboard", 18, 18);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_14, 0);
    create_label(screen, "Clean Firmware", 20, 50);
    create_label(screen, "Display: OK", 20, 105);
    s_rlcd.psram_label = create_label(screen, "PSRAM: Checking", 20, 140);
    s_rlcd.wifi_label = create_label(screen, "Wi-Fi: Starting", 20, 175);
    s_rlcd.button_label = create_label(screen, "Button: Ready", 20, 210);
}

static esp_err_t configure_rlcd_spi(void)
{
    const spi_bus_config_t bus_config = {
        .mosi_io_num = BOARD_RLCD_MOSI_GPIO,
        .miso_io_num = -1,
        .sclk_io_num = BOARD_RLCD_SCK_GPIO,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = RLCD_FRAMEBUFFER_SIZE,
    };
    ESP_RETURN_ON_ERROR(spi_bus_initialize(SPI3_HOST, &bus_config, SPI_DMA_CH_AUTO), TAG,
                        "RLCD SPI bus setup failed");

    const esp_lcd_panel_io_spi_config_t io_config = {
        .cs_gpio_num = BOARD_RLCD_CS_GPIO,
        .dc_gpio_num = BOARD_RLCD_DC_GPIO,
        .spi_mode = 0,
        .pclk_hz = 40U * 1000U * 1000U,
        .trans_queue_depth = 7,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
    };
    ESP_RETURN_ON_ERROR(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI3_HOST,
                                                  &io_config, &s_rlcd.io),
                        TAG, "RLCD SPI panel IO setup failed");

    const gpio_config_t reset_config = {
        .pin_bit_mask = 1ULL << BOARD_RLCD_RST_GPIO,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    return gpio_config(&reset_config);
}

esp_err_t display_init(void)
{
    ESP_RETURN_ON_ERROR(configure_rlcd_spi(), TAG, "RLCD transport initialization failed");

    s_rlcd.framebuffer = heap_caps_malloc(RLCD_FRAMEBUFFER_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    ESP_RETURN_ON_FALSE(s_rlcd.framebuffer != NULL, ESP_ERR_NO_MEM, TAG, "RLCD framebuffer allocation failed");

    const lvgl_port_cfg_t port_config = {
        .task_priority = 2,
        .task_stack = 7168,
        .task_affinity = -1,
        .task_max_sleep_ms = 500,
        .task_stack_caps = MALLOC_CAP_INTERNAL | MALLOC_CAP_DEFAULT,
        .timer_period_ms = 50,
    };
    ESP_RETURN_ON_ERROR(lvgl_port_init(&port_config), TAG, "LVGL port initialization failed");
    ESP_RETURN_ON_FALSE(lvgl_port_lock(0), ESP_ERR_TIMEOUT, TAG, "LVGL port lock failed");

    s_rlcd.lv_display = lv_display_create(BOARD_RLCD_WIDTH, BOARD_RLCD_HEIGHT);
    if (s_rlcd.lv_display == NULL) {
        lvgl_port_unlock();
        return ESP_ERR_NO_MEM;
    }
    lv_display_set_flush_cb(s_rlcd.lv_display, rlcd_flush_cb);
    lv_display_set_color_format(s_rlcd.lv_display, LV_COLOR_FORMAT_RGB565);

    uint8_t *draw_buffer = heap_caps_malloc(DRAW_BUFFER_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (draw_buffer == NULL) {
        lvgl_port_unlock();
        return ESP_ERR_NO_MEM;
    }
    lv_display_set_buffers(s_rlcd.lv_display, draw_buffer, NULL, DRAW_BUFFER_SIZE,
                           LV_DISPLAY_RENDER_MODE_PARTIAL);

    esp_err_t err = rlcd_init_controller();
    if (err == ESP_OK) {
        create_bootstrap_page();
    }
    lvgl_port_unlock();
    ESP_RETURN_ON_ERROR(err, TAG, "RLCD controller initialization failed");

    ESP_LOGI(TAG, "RLCD and LVGL bootstrap page ready");
    return ESP_OK;
}

static void set_status_label(lv_obj_t *label, const char *prefix, const char *status)
{
    if (label == NULL || status == NULL) {
        return;
    }
    if (!lvgl_port_lock(1000)) {
        ESP_LOGW(TAG, "LVGL lock timeout while updating %s status", prefix);
        return;
    }
    lv_label_set_text_fmt(label, "%s: %s", prefix, status);
    lvgl_port_unlock();
}

void display_set_wifi_status(const char *status)
{
    set_status_label(s_rlcd.wifi_label, "Wi-Fi", status);
}

void display_set_button_status(const char *status)
{
    set_status_label(s_rlcd.button_label, "Button", status);
}

void display_set_psram_status(const char *status)
{
    set_status_label(s_rlcd.psram_label, "PSRAM", status);
}

bool display_lock(uint32_t timeout_ms)
{
    return lvgl_port_lock(timeout_ms);
}

void display_unlock(void)
{
    lvgl_port_unlock();
}

display_flush_metrics_t display_flush_metrics_take(void)
{
    display_flush_metrics_t snapshot;
    portENTER_CRITICAL(&s_flush_metrics_mux);
    snapshot = s_flush_metrics;
    memset(&s_flush_metrics, 0, sizeof(s_flush_metrics));
    portEXIT_CRITICAL(&s_flush_metrics_mux);
    return snapshot;
}
