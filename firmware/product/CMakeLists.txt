cmake_minimum_required(VERSION 3.16)

# The product target is fixed here and enforced again by scripts/build-clean-firmware.sh.
set(IDF_TARGET "esp32s3")
set(PROJECT_VER "0.1.0")
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(opendesknode)
