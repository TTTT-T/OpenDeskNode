#include "audio_hw.h"

#include <string.h>

#include "audio_codec_data_if.h"
#include "audio_codec_gpio_if.h"
#include "board.h"
#include "driver/i2c_master.h"
#include "driver/i2s_std.h"
#include "driver/i2s_tdm.h"
#include "esp_check.h"
#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"
#include "esp_log.h"

static const char *TAG = "audio_hw";

/* Mirror of the accepted reference configuration for this board. */
#define DMA_DESC_NUM 6
#define DMA_FRAME_NUM 240

typedef struct {
    i2c_master_bus_handle_t i2c_bus;
    i2s_chan_handle_t tx;
    i2s_chan_handle_t rx;
    const audio_codec_data_if_t *data_if;
    const audio_codec_ctrl_if_t *es8311_ctrl;
    const audio_codec_ctrl_if_t *es7210_ctrl;
    const audio_codec_gpio_if_t *gpio_if;
    const audio_codec_if_t *es8311_codec;
    const audio_codec_if_t *es7210_codec;
    esp_codec_dev_handle_t output_dev;
    esp_codec_dev_handle_t input_dev;
    bool input_enabled;
    bool output_enabled;
} audio_hw_t;

static audio_hw_t s_hw;

static esp_err_t init_i2c(void)
{
    const i2c_master_bus_config_t cfg = {
        .i2c_port = BOARD_I2C_PORT,
        .sda_io_num = BOARD_I2C_SDA_GPIO,
        .scl_io_num = BOARD_I2C_SCL_GPIO,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .intr_priority = 0,
        .trans_queue_depth = 0,
        .flags = { .enable_internal_pullup = 1 },
    };
    esp_err_t err = i2c_new_master_bus(&cfg, &s_hw.i2c_bus);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2c_new_master_bus: %s", esp_err_to_name(err));
    }
    return err;
}

static esp_err_t init_i2s_duplex(void)
{
    const i2s_chan_config_t chan_cfg = {
        .id = I2S_NUM_0,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = DMA_DESC_NUM,
        .dma_frame_num = DMA_FRAME_NUM,
        .auto_clear_after_cb = true,
        .auto_clear_before_cb = false,
        .intr_priority = 0,
    };
    ESP_RETURN_ON_ERROR(i2s_new_channel(&chan_cfg, &s_hw.tx, &s_hw.rx), TAG, "i2s_new_channel");

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_HW_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = BOARD_I2S_MCLK_GPIO,
            .bclk = BOARD_I2S_BCLK_GPIO,
            .ws = BOARD_I2S_WS_GPIO,
            .dout = BOARD_I2S_DOUT_GPIO,
            .din = I2S_GPIO_UNUSED,
            .invert_flags = { 0 },
        },
    };
    std_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_BOTH;
    ESP_RETURN_ON_ERROR(i2s_channel_init_std_mode(s_hw.tx, &std_cfg), TAG, "init std tx");

    i2s_tdm_config_t tdm_cfg = {
        .clk_cfg = I2S_TDM_CLK_DEFAULT_CONFIG(AUDIO_HW_SAMPLE_RATE),
        .slot_cfg = I2S_TDM_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO,
                                                        I2S_TDM_SLOT0 | I2S_TDM_SLOT1 | I2S_TDM_SLOT2),
        .gpio_cfg = {
            .mclk = BOARD_I2S_MCLK_GPIO,
            .bclk = BOARD_I2S_BCLK_GPIO,
            .ws = BOARD_I2S_WS_GPIO,
            .dout = I2S_GPIO_UNUSED,
            .din = BOARD_I2S_DIN_GPIO,
            .invert_flags = { 0 },
        },
    };
    tdm_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
    tdm_cfg.slot_cfg.total_slot = 4;
    ESP_RETURN_ON_ERROR(i2s_channel_init_tdm_mode(s_hw.rx, &tdm_cfg), TAG, "init tdm rx");
    ESP_LOGI(TAG, "I2S0 duplex ready: tx std + rx tdm slots 0/1/2 at %d Hz", AUDIO_HW_SAMPLE_RATE);
    return ESP_OK;
}

esp_err_t audio_hw_init(void)
{
    if (s_hw.output_dev != NULL) {
        return ESP_OK;
    }
    ESP_RETURN_ON_ERROR(init_i2c(), TAG, "i2c");
    ESP_RETURN_ON_ERROR(init_i2s_duplex(), TAG, "i2s");

    audio_codec_i2s_cfg_t i2s_data_cfg = {
        .port = I2S_NUM_0,
        .tx_handle = s_hw.tx,
        .rx_handle = s_hw.rx,
    };
    s_hw.data_if = audio_codec_new_i2s_data((audio_codec_i2s_cfg_t *)&i2s_data_cfg);
    ESP_RETURN_ON_FALSE(s_hw.data_if != NULL, ESP_FAIL, TAG, "audio_codec_new_i2s_data");

    audio_codec_i2c_cfg_t es8311_i2c = {
        .port = BOARD_I2C_PORT,
        .addr = ES8311_CODEC_DEFAULT_ADDR,
        .bus_handle = s_hw.i2c_bus,
    };
    s_hw.es8311_ctrl = audio_codec_new_i2c_ctrl(&es8311_i2c);
    ESP_RETURN_ON_FALSE(s_hw.es8311_ctrl != NULL, ESP_FAIL, TAG, "es8311 ctrl");

    audio_codec_i2c_cfg_t es7210_i2c = {
        .port = BOARD_I2C_PORT,
        .addr = ES7210_CODEC_DEFAULT_ADDR,
        .bus_handle = s_hw.i2c_bus,
    };
    s_hw.es7210_ctrl = audio_codec_new_i2c_ctrl(&es7210_i2c);
    ESP_RETURN_ON_FALSE(s_hw.es7210_ctrl != NULL, ESP_FAIL, TAG, "es7210 ctrl");

    s_hw.gpio_if = audio_codec_new_gpio();
    ESP_RETURN_ON_FALSE(s_hw.gpio_if != NULL, ESP_FAIL, TAG, "gpio if");

    es8311_codec_cfg_t es8311_cfg = {
        .ctrl_if = s_hw.es8311_ctrl,
        .gpio_if = s_hw.gpio_if,
        .codec_mode = ESP_CODEC_DEV_WORK_MODE_DAC,
        .pa_pin = BOARD_AUDIO_PA_GPIO,
        .use_mclk = true,
        .hw_gain = {
            .pa_voltage = 5.0,
            .codec_dac_voltage = 3.3,
        },
    };
    s_hw.es8311_codec = es8311_codec_new(&es8311_cfg);
    ESP_RETURN_ON_FALSE(s_hw.es8311_codec != NULL, ESP_FAIL, TAG, "es8311_codec_new");

    es7210_codec_cfg_t es7210_cfg = {
        .ctrl_if = s_hw.es7210_ctrl,
        .mic_selected = ES7210_SEL_MIC1 | ES7210_SEL_MIC2 | ES7210_SEL_MIC3,
    };
    s_hw.es7210_codec = es7210_codec_new(&es7210_cfg);
    ESP_RETURN_ON_FALSE(s_hw.es7210_codec != NULL, ESP_FAIL, TAG, "es7210_codec_new");

    esp_codec_dev_cfg_t out_dev_cfg = {
        .dev_type = ESP_CODEC_DEV_TYPE_OUT,
        .codec_if = s_hw.es8311_codec,
        .data_if = s_hw.data_if,
    };
    s_hw.output_dev = esp_codec_dev_new(&out_dev_cfg);
    ESP_RETURN_ON_FALSE(s_hw.output_dev != NULL, ESP_FAIL, TAG, "esp_codec_dev_new out");

    esp_codec_dev_cfg_t in_dev_cfg = {
        .dev_type = ESP_CODEC_DEV_TYPE_IN,
        .codec_if = s_hw.es7210_codec,
        .data_if = s_hw.data_if,
    };
    s_hw.input_dev = esp_codec_dev_new(&in_dev_cfg);
    ESP_RETURN_ON_FALSE(s_hw.input_dev != NULL, ESP_FAIL, TAG, "esp_codec_dev_new in");

    int es7210_reset = -1;
    int es8311_dac = -1;
    if (esp_codec_dev_read_reg(s_hw.input_dev, 0x00, &es7210_reset) != ESP_CODEC_DEV_OK ||
        esp_codec_dev_read_reg(s_hw.output_dev, 0x31, &es8311_dac) != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "codec register probe failed");
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "I2C probe OK: ES7210 REG00=0x%02x ES8311 REG31=0x%02x", es7210_reset, es8311_dac);
    return ESP_OK;
}

esp_err_t audio_hw_input_enable(bool enable)
{
    if (s_hw.input_dev == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    if (enable == s_hw.input_enabled) {
        return ESP_OK;
    }
    if (enable) {
        esp_codec_dev_sample_info_t fs = {
            .sample_rate = AUDIO_HW_SAMPLE_RATE,
            .channel = 4,
            .channel_mask = ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0)
                           | ESP_CODEC_DEV_MAKE_CHANNEL_MASK(1)
                           | ESP_CODEC_DEV_MAKE_CHANNEL_MASK(2),
            .bits_per_sample = 16,
            .mclk_multiple = 0,
        };
        const int ret = esp_codec_dev_open(s_hw.input_dev, &fs);
        if (ret != ESP_CODEC_DEV_OK) {
            return ESP_FAIL;
        }
        /* The accepted reference configuration runs this board's mics at
         * 30 dB input gain (BoxAudioCodec input_gain default). */
        esp_codec_dev_set_in_gain(s_hw.input_dev, 30.0);
    } else {
        esp_codec_dev_close(s_hw.input_dev);
    }
    s_hw.input_enabled = enable;
    ESP_LOGI(TAG, "input %s", enable ? "enabled (TDM slots 0/1/2)" : "disabled");
    return ESP_OK;
}

esp_err_t audio_hw_output_enable(bool enable)
{
    if (s_hw.output_dev == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    if (enable == s_hw.output_enabled) {
        return ESP_OK;
    }
    if (enable) {
        esp_codec_dev_sample_info_t fs = {
            .sample_rate = AUDIO_HW_SAMPLE_RATE,
            .channel = 1,
            .bits_per_sample = 16,
            .mclk_multiple = 0,
        };
        const int ret = esp_codec_dev_open(s_hw.output_dev, &fs);
        if (ret != ESP_CODEC_DEV_OK) {
            return ESP_FAIL;
        }
        esp_codec_dev_set_out_vol(s_hw.output_dev, 70);
    } else {
        esp_codec_dev_close(s_hw.output_dev);
    }
    s_hw.output_enabled = enable;
    ESP_LOGI(TAG, "output %s", enable ? "enabled (mono, vol 70)" : "disabled");
    return ESP_OK;
}

esp_err_t audio_hw_read(int16_t *mic0, int16_t *ref, int16_t *mic1, int samples)
{
    int16_t interleaved[3 * 64];
    int done = 0;
    while (done < samples) {
        const int chunk = (samples - done) > 64 ? 64 : (samples - done);
        const int ret = esp_codec_dev_read(s_hw.input_dev, interleaved, chunk * 3 * sizeof(int16_t));
        if (ret != ESP_CODEC_DEV_OK) {
            ESP_LOGE(TAG, "esp_codec_dev_read: %d", ret);
            return ESP_FAIL;
        }
        for (int i = 0; i < chunk; i++) {
            mic0[done + i] = interleaved[3 * i + 0];
            ref[done + i] = interleaved[3 * i + 1];
            mic1[done + i] = interleaved[3 * i + 2];
        }
        done += chunk;
    }
    return ESP_OK;
}

esp_err_t audio_hw_write(const int16_t *pcm, int samples)
{
    const int ret = esp_codec_dev_write(s_hw.output_dev, (void *)pcm, samples * sizeof(int16_t));
    if (ret != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "esp_codec_dev_write: %d", ret);
        return ESP_FAIL;
    }
    return ESP_OK;
}

esp_err_t audio_hw_set_output_volume(int volume)
{
    const int ret = esp_codec_dev_set_out_vol(s_hw.output_dev, volume);
    return ret == ESP_CODEC_DEV_OK ? ESP_OK : ESP_FAIL;
}

esp_err_t audio_hw_probe_registers(int *es7210_reset_reg, int *es8311_dac_reg)
{
    if (s_hw.input_dev == NULL || s_hw.output_dev == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    if (esp_codec_dev_read_reg(s_hw.input_dev, 0x00, es7210_reset_reg) != ESP_CODEC_DEV_OK) {
        return ESP_FAIL;
    }
    if (esp_codec_dev_read_reg(s_hw.output_dev, 0x31, es8311_dac_reg) != ESP_CODEC_DEV_OK) {
        return ESP_FAIL;
    }
    return ESP_OK;
}
