idf_component_register(
    SRCS "board_button.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_gpio freertos
)
