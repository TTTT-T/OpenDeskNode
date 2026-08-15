idf_component_register(
    SRCS "display_rlcd.c"
    INCLUDE_DIRS "include"
    REQUIRES board esp_lcd esp_driver_spi esp_driver_gpio esp_psram esp_lvgl_port lvgl freertos
)
