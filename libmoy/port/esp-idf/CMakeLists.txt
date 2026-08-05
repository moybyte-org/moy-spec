# libmoy as an ESP-IDF component.
#
# Drop this directory into your project's components/ (or add libmoy/port/esp-idf
# to EXTRA_COMPONENT_DIRS) and `#include "moy.h"`. The library is C99 with no
# dependencies, so there is nothing to configure and nothing to fetch.
#
# The Lua binding is opt-in: set CONFIG_MOY_WITH_LUA=y (or just add the vendored
# sources yourself). Without it you get the raster and the cart model, which is
# all a host needs if it drives the console from C.

set(MOY_ROOT "${CMAKE_CURRENT_LIST_DIR}/../..")

set(MOY_SRCS
    "${MOY_ROOT}/src/moy_canvas.c"
    "${MOY_ROOT}/src/moy_sprite.c"
    "${MOY_ROOT}/src/moy_data.c")

set(MOY_DEFS "")

if(CONFIG_MOY_WITH_LUA)
    file(GLOB MOY_LUA_SRCS "${MOY_ROOT}/vendor/lua/*.c")
    list(APPEND MOY_SRCS "${MOY_ROOT}/src/moy_lua.c" ${MOY_LUA_SRCS})
    list(APPEND MOY_DEFS "MOY_WITH_LUA")
endif()

idf_component_register(
    SRCS ${MOY_SRCS}
    INCLUDE_DIRS "${MOY_ROOT}/include" "${MOY_ROOT}/vendor/lua"
    REQUIRES driver esp_timer nvs_flash)

target_compile_definitions(${COMPONENT_LIB} PUBLIC ${MOY_DEFS})

# The vendored Lua is upstream code; its warnings are not ours to fix, and the
# IDF's -Werror would otherwise stop the build on them.
foreach(src ${MOY_SRCS})
    if(src MATCHES "vendor/lua/")
        set_source_files_properties(${src} PROPERTIES COMPILE_FLAGS "-w")
    endif()
endforeach()
