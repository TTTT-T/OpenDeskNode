/*
 * Stock dashboard view: four 200x138 panels plus a 24 px global status strip
 * 400x300 monochrome RLCD, rendered through LVGL on top of the display
 * component transport. All glyphs come from the subset fonts generated from
 * Source Han Sans SC (see fonts/README.md); the view never renders a glyph
 * outside those subsets.
 */
#include "stock_view.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "display.h"
#include "lvgl.h"

#define STOCK_VIEW_PANEL_WIDTH 200
#define STOCK_VIEW_PANEL_HEIGHT 138
#define STOCK_VIEW_STATUS_HEIGHT 24
#define STOCK_VIEW_CHART_WIDTH 190
#define STOCK_VIEW_CHART_HEIGHT 28

extern const lv_font_t stock_font_cjk_24;
extern const lv_font_t stock_font_num_48;

typedef struct {
    lv_obj_t *panel;
    lv_obj_t *name_label;
    lv_obj_t *status_label;
    lv_obj_t *price_label;
    lv_obj_t *change_label;
    lv_obj_t *sparkline;
    lv_obj_t *baseline;
    lv_point_precise_t sparkline_points[STOCK_INTRADAY_SAMPLES];
    lv_point_precise_t baseline_points[2];
} stock_panel_view_t;

static lv_obj_t *s_screen;
static lv_obj_t *s_banner;
static stock_panel_view_t s_panels[STOCK_COUNT];

static lv_obj_t *create_panel(uint16_t column, uint16_t row)
{
    lv_obj_t *panel = lv_obj_create(s_screen);
    const int32_t y = row == 0
                          ? 0
                          : STOCK_VIEW_PANEL_HEIGHT + STOCK_VIEW_STATUS_HEIGHT;
    lv_obj_set_pos(panel, column * STOCK_VIEW_PANEL_WIDTH, y);
    lv_obj_set_size(panel, STOCK_VIEW_PANEL_WIDTH, STOCK_VIEW_PANEL_HEIGHT);
    lv_obj_set_style_bg_color(panel, lv_color_white(), 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(panel, 1, 0);
    lv_obj_set_style_border_color(panel, lv_color_black(), 0);
    lv_obj_set_style_pad_all(panel, 0, 0);
    lv_obj_set_scrollbar_mode(panel, LV_SCROLLBAR_MODE_OFF);
    return panel;
}

static lv_obj_t *create_text(lv_obj_t *parent, const lv_font_t *font,
                             int32_t x, int32_t y, int32_t w,
                             lv_text_align_t align)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_obj_set_pos(label, x, y);
    lv_obj_set_width(label, w);
    lv_obj_set_style_text_color(label, lv_color_black(), 0);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_align(label, align, 0);
    return label;
}

static void create_panel_content(stock_panel_view_t *view, uint16_t column, uint16_t row)
{
    view->panel = create_panel(column, row);

    /* Row 1: Chinese name left, signed change amount right. */
    view->name_label = create_text(view->panel, &stock_font_cjk_24, 6, 2, 100,
                                   LV_TEXT_ALIGN_LEFT);
    view->status_label = create_text(view->panel, &stock_font_cjk_24, 94, 2, 100,
                                      LV_TEXT_ALIGN_RIGHT);

    /* Row 2: large price. */
    view->price_label = create_text(view->panel, &stock_font_num_48, 6, 28, 188,
                                     LV_TEXT_ALIGN_LEFT);

    /* Row 3: percent line with special-state prefix, e.g.
     * "涨停 ▲ +10.00%" / "▼ -0.86%". */
    view->change_label = create_text(view->panel, &stock_font_cjk_24, 6, 80, 188,
                                      LV_TEXT_ALIGN_LEFT);

    /* Row 4: sparkline with a dashed previous-close baseline. */
    lv_obj_t *chart = lv_obj_create(view->panel);
    lv_obj_set_pos(chart, 5, 104);
    lv_obj_set_size(chart, STOCK_VIEW_CHART_WIDTH, STOCK_VIEW_CHART_HEIGHT);
    lv_obj_set_style_bg_opa(chart, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(chart, 0, 0);
    lv_obj_set_style_pad_all(chart, 0, 0);
    lv_obj_set_scrollbar_mode(chart, LV_SCROLLBAR_MODE_OFF);

    view->baseline = lv_line_create(chart);
    lv_obj_set_style_line_color(view->baseline, lv_color_black(), 0);
    lv_obj_set_style_line_width(view->baseline, 1, 0);
    lv_obj_set_style_line_dash_width(view->baseline, 4, 0);
    lv_obj_set_style_line_dash_gap(view->baseline, 3, 0);

    view->sparkline = lv_line_create(chart);
    lv_obj_set_style_line_color(view->sparkline, lv_color_black(), 0);
    lv_obj_set_style_line_width(view->sparkline, 2, 0);
}

esp_err_t stock_view_create(void)
{
    if (!display_lock(1000)) {
        return ESP_ERR_TIMEOUT;
    }

    s_screen = lv_obj_create(NULL);
    if (s_screen == NULL) {
        display_unlock();
        return ESP_ERR_NO_MEM;
    }
    lv_obj_set_style_bg_color(s_screen, lv_color_white(), 0);
    lv_obj_set_style_bg_opa(s_screen, LV_OPA_COVER, 0);

    for (size_t i = 0; i < STOCK_COUNT; ++i) {
        create_panel_content(&s_panels[i], (uint16_t)(i % 2), (uint16_t)(i / 2));
    }

    s_banner = create_text(s_screen, &stock_font_cjk_24, 0,
                           STOCK_VIEW_PANEL_HEIGHT, 400, LV_TEXT_ALIGN_CENTER);
    lv_obj_set_height(s_banner, STOCK_VIEW_STATUS_HEIGHT);
    lv_obj_set_style_bg_color(s_banner, lv_color_white(), 0);
    lv_obj_set_style_bg_opa(s_banner, LV_OPA_COVER, 0);

    lv_screen_load(s_screen);
    display_unlock();
    return ESP_OK;
}

static int32_t map_price_to_y(stock_price_t price, stock_price_t min, stock_price_t max)
{
    if (max <= min) {
        return STOCK_VIEW_CHART_HEIGHT / 2;
    }
    const int64_t span = (int64_t)max - min;
    const int64_t offset = (int64_t)price - min;
    const int32_t usable = STOCK_VIEW_CHART_HEIGHT - 1;
    return (int32_t)(usable - (offset * usable + span / 2) / span);
}

static void update_chart(stock_panel_view_t *view, const stock_quote_t *quote)
{
    if (quote->intraday_count == 0) {
        lv_obj_add_flag(view->sparkline, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(view->baseline, LV_OBJ_FLAG_HIDDEN);
        return;
    }

    stock_price_t min = quote->prev_close;
    stock_price_t max = quote->prev_close;
    for (uint16_t i = 0; i < quote->intraday_count; ++i) {
        if (quote->intraday[i] < min) {
            min = quote->intraday[i];
        }
        if (quote->intraday[i] > max) {
            max = quote->intraday[i];
        }
    }

    const uint16_t count = quote->intraday_count;
    if (count > 1) {
        for (uint16_t i = 0; i < count; ++i) {
            view->sparkline_points[i].x = (int32_t)((STOCK_VIEW_CHART_WIDTH - 1) * i) / (count - 1);
            view->sparkline_points[i].y = map_price_to_y(quote->intraday[i], min, max);
        }
        lv_line_set_points(view->sparkline, view->sparkline_points, count);
        lv_obj_clear_flag(view->sparkline, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(view->sparkline, LV_OBJ_FLAG_HIDDEN);
    }

    const int32_t baseline_y = map_price_to_y(quote->prev_close, min, max);
    view->baseline_points[0].x = 0;
    view->baseline_points[0].y = baseline_y;
    view->baseline_points[1].x = STOCK_VIEW_CHART_WIDTH - 1;
    view->baseline_points[1].y = baseline_y;
    lv_line_set_points(view->baseline, view->baseline_points, 2);
    lv_obj_clear_flag(view->baseline, LV_OBJ_FLAG_HIDDEN);
}

void stock_view_update(const stock_dashboard_t *dashboard)
{
    if (s_screen == NULL || !display_lock(1000)) {
        return;
    }

    for (size_t i = 0; i < STOCK_COUNT; ++i) {
        const stock_quote_t *quote = &dashboard->quotes[i];
        stock_panel_view_t *view = &s_panels[i];
        char price[16];
        char amount[16];
        char percent[32];

        if (!dashboard->has_data) {
            lv_label_set_text(view->name_label, "");
            lv_label_set_text(view->status_label, "");
            lv_label_set_text(view->price_label, "--");
            lv_label_set_text(view->change_label, "");
            lv_obj_add_flag(view->sparkline, LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(view->baseline, LV_OBJ_FLAG_HIDDEN);
            continue;
        }

        lv_label_set_text(view->name_label, quote->name);

        /* Change amount is always visible; special states never replace it. */
        stock_format_change_amount(amount, sizeof(amount), quote);
        lv_label_set_text(view->status_label, amount);

        stock_format_price(price, sizeof(price), quote->current);
        lv_label_set_text(view->price_label, price);

        /* Percent line carries the special state as a prefix, e.g.
         * "涨停 ▲ +10.00%"; NORMAL keeps the exact plain semantics. */
        stock_format_change_percent_with_state(percent, sizeof(percent), quote);
        lv_label_set_text(view->change_label, percent);

        update_chart(view, quote);
    }

    char banner[48];
    stock_format_dashboard_banner(banner, sizeof(banner), dashboard);
    lv_label_set_text(s_banner, banner);

    /* Render synchronously so the caller's flush metrics cover exactly this
     * update and cannot leak into the next reporting interval. */
    lv_refr_now(NULL);
    display_unlock();
}
