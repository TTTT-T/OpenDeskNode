idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    REQUIRES audio board display network stock spi_flash esp_psram
)
