idf_component_register(
  SRCS "voice_protocol.c" "voice_vad.c" "voice_recovery.c" "voice_wake.c" "voice_runtime.c"
  INCLUDE_DIRS "include"
  REQUIRES audio network freertos esp_timer heap
  PRIV_REQUIRES espressif__esp_websocket_client espressif__cjson
)
