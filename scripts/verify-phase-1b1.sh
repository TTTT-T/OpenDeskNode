#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
product_dir="$repo_root/firmware/product"

required_files=(
  "$product_dir/CMakeLists.txt"
  "$product_dir/sdkconfig.defaults"
  "$product_dir/partitions.csv"
  "$product_dir/main/app_main.c"
  "$product_dir/main/idf_component.yml"
  "$product_dir/components/board/include/board.h"
  "$product_dir/components/display/display_rlcd.c"
  "$product_dir/components/network/network_wifi.c"
)
for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || { echo "Missing required product file: $file" >&2; exit 1; }
done

rg -q 'set\(IDF_TARGET "esp32s3"\)' "$product_dir/CMakeLists.txt"
rg -q 'CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y' "$product_dir/sdkconfig.defaults"
rg -q 'CONFIG_SPIRAM=y' "$product_dir/sdkconfig.defaults"
rg -q 'CONFIG_SPIRAM_MODE_OCT=y' "$product_dir/sdkconfig.defaults"
rg -q 'CONFIG_SPIRAM_SPEED_80M=y' "$product_dir/sdkconfig.defaults"
rg -q '^factory,[[:space:]]+app,[[:space:]]+factory,[[:space:]]+0x10000,[[:space:]]+0xF00000,' "$product_dir/partitions.csv"
! rg -qi 'ota' "$product_dir/partitions.csv"

rg -q 'lvgl/lvgl: ">=9\.5\.0,<9\.6\.0"' "$product_dir/main/idf_component.yml"
rg -q 'espressif/esp_lvgl_port: ">=2\.8\.0,<2\.9\.0"' "$product_dir/main/idf_component.yml"
rg -q 'ESP32-S3 Dashboard' "$product_dir/components/display/display_rlcd.c"
rg -q 'Clean Firmware' "$product_dir/components/display/display_rlcd.c"
rg -q 'Display: OK' "$product_dir/components/display/display_rlcd.c"
rg -q 'PSRAM: Checking' "$product_dir/components/display/display_rlcd.c"
rg -Fq 'display_set_psram_status(psram_ok ? "OK" : "Mismatch")' "$product_dir/main/app_main.c"
rg -q 'Wi-Fi: Starting' "$product_dir/components/display/display_rlcd.c"
rg -q 'Button: Ready' "$product_dir/components/display/display_rlcd.c"
rg -q 'BOARD_BOOT_BUTTON_GPIO 0' "$product_dir/components/board/include/board.h"
rg -q 'BOARD_RLCD_DC_GPIO 5' "$product_dir/components/board/include/board.h"
rg -q 'BOARD_RLCD_CS_GPIO 40' "$product_dir/components/board/include/board.h"
rg -q 'BOARD_RLCD_SCK_GPIO 11' "$product_dir/components/board/include/board.h"
rg -q 'BOARD_RLCD_MOSI_GPIO 12' "$product_dir/components/board/include/board.h"
rg -q 'BOARD_RLCD_RST_GPIO 41' "$product_dir/components/board/include/board.h"
rg -q 'BOARD_RLCD_TE_GPIO 6' "$product_dir/components/board/include/board.h"
rg -q 'BOARD_RLCD_WIDTH 400' "$product_dir/components/board/include/board.h"
rg -q 'BOARD_RLCD_HEIGHT 300' "$product_dir/components/board/include/board.h"
rg -q 'lvgl_port_lock' "$product_dir/components/display/display_rlcd.c"
rg -q 'esp_psram_get_size' "$product_dir/main/app_main.c"
rg -q 'esp_flash_get_size' "$product_dir/main/app_main.c"
rg -q 'WIFI_STORAGE_FLASH' "$product_dir/components/network/network_wifi.c"
rg -q 'NETWORK_STATUS_UNCONFIGURED' "$product_dir/components/network/network_wifi.c"
rg -q 'SC_TYPE_ESPTOUCH_AIRKISS' "$product_dir/components/network/network_wifi.c"
rg -q 'nvs_open\("wifi", NVS_READONLY' "$product_dir/components/network/network_wifi.c"
! rg -q 'CLEAN_FIRMWARE_WIFI_(SSID|PASSWORD)' "$product_dir"

# Product source may cite the reference for provenance, but must not import it.
if rg -n --glob '*.[ch]' --glob 'CMakeLists.txt' --glob 'idf_component.yml' \
  '#include[[:space:]]+[<"][^>"]*(xiaozhi|application\.h|wifi_board\.h)|add_subdirectory\([^)]*xiaozhi|EXTRA_COMPONENT_DIRS[^\n]*xiaozhi' \
  "$product_dir"; then
  echo "Product source imports the frozen reference" >&2
  exit 1
fi

# These hosts were present only in the frozen reference, never in product code.
if rg -n --glob '*.[ch]' --glob 'CMakeLists.txt' --glob 'idf_component.yml' \
  'api\.tenclass\.net|xiaozhi\.me' "$product_dir"; then
  echo "Product source contains a forbidden reference-cloud host" >&2
  exit 1
fi

git -C "$repo_root" diff --check
echo "PHASE_1B1_STATIC_CHECKS_OK"
