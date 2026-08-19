idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    REQUIRES audio board display network stock voice spi_flash esp_psram
)
