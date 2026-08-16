idf_component_register(
  SRCS "audio_hw.c" "audio_selftest.c" "audio_stimulus.c"
  INCLUDE_DIRS "include"
  REQUIRES board esp_driver_i2c esp_driver_i2s espressif__esp_codec_dev espressif__esp-sr
  PRIV_REQUIRES heap spi_flash
)
