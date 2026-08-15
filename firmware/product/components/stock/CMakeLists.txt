idf_component_register(
    SRCS
        "stock_model.c"
        "stock_mock.c"
        "stock_view.c"
        "stock_service.c"
        "fonts/stock_font_cjk_24.c"
        "fonts/stock_font_num_48.c"
    INCLUDE_DIRS "include"
    REQUIRES display lvgl freertos esp_timer heap
)

# The lv_font_conv-generated font files include "lvgl.h" only when
# LV_LVGL_H_INCLUDE_SIMPLE is defined; ESP-IDF's lvgl component exposes lvgl.h
# at the root of its public include dir.
target_compile_definitions(${COMPONENT_LIB} PRIVATE LV_LVGL_H_INCLUDE_SIMPLE)

# stock_model.c and stock_mock.c stay pure C99 (no ESP-IDF/LVGL includes) so
# they can also be compiled and tested directly on the host.
