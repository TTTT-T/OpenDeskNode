idf_component_register(
    SRCS "display_rlcd.c"
    INCLUDE_DIRS "include"
    REQUIRES board esp_lcd esp_driver_spi esp_driver_gpio esp_psram esp_lvgl_port lvgl freertos
    # esp_timer/heap headers are only used inside display_rlcd.c, not in the
    # public display.h, so they stay private dependencies.
    PRIV_REQUIRES esp_timer heap
)
