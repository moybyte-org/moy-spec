# libmoy as an ESP-IDF component.
#
# Add the PARENT of this directory to EXTRA_COMPONENT_DIRS and `#include "moy.h"`:
#
#   set(EXTRA_COMPONENT_DIRS "path/to/libmoy/port/esp-idf")
#
# The component is then named after this directory -- `libmoy` -- which is what
# you put in your own component's REQUIRES. (Pointing EXTRA_COMPONENT_DIRS at a
# directory that is itself a component names the component after THAT directory
# instead, which is why this level exists rather than the files living one up.)
#
# The Lua binding is opt-in via CONFIG_MOY_WITH_LUA. Without it you get the
# raster and the cart model, which is all a host needs if it drives the console
# from C.

set(MOY_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../..")

set(MOY_SRCS
    "${MOY_ROOT}/src/moy_canvas.c"
    "${MOY_ROOT}/src/moy_sprite.c"
    "${MOY_ROOT}/src/moy_data.c")

set(MOY_INCS "${MOY_ROOT}/include")

if(CONFIG_MOY_WITH_LUA)
    file(GLOB MOY_LUA_SRCS "${MOY_ROOT}/vendor/lua/*.c")
    list(APPEND MOY_SRCS "${MOY_ROOT}/src/moy_lua.c" ${MOY_LUA_SRCS})
    # Public, because the host is the one that calls luaL_newstate and hands the
    # state to moy_lua_open. moy.h only forward-declares struct lua_State.
    list(APPEND MOY_INCS "${MOY_ROOT}/vendor/lua")
endif()

# REQUIRES nothing, deliberately. libmoy is freestanding C99 that never
# allocates, reads no clock and touches no peripheral -- the platform hands it
# buffers and function pointers. Naming driver/esp_timer/nvs_flash here would
# force them on every consumer and quietly contradict that claim; those belong
# to the port that implements moy_host, which is example/main/CMakeLists.txt.
idf_component_register(
    SRCS ${MOY_SRCS}
    INCLUDE_DIRS ${MOY_INCS})

if(CONFIG_MOY_WITH_LUA)
    target_compile_definitions(${COMPONENT_LIB} PUBLIC MOY_WITH_LUA)
endif()

# The vendored Lua is upstream code; its warnings are not ours to fix, and the
# IDF's warning flags would otherwise bury the build in them.
foreach(src ${MOY_SRCS})
    if(src MATCHES "vendor/lua/")
        set_source_files_properties(${src} PROPERTIES COMPILE_FLAGS "-w")
    endif()
endforeach()
