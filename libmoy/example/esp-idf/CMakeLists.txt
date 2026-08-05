# A minimal ESP-IDF project that consumes libmoy -- and, by being built for a
# real target in CI (.github/workflows/libmoy.yml), the thing that keeps the
# component honest. If this configures, compiles and links, then the component
# registers, its include paths resolve, its Kconfig applies, and the C is clean
# on a 32-bit RISC-V ABI under the IDF's own warning flags.
#
# The one line below is also the entire integration story for your own project:
cmake_minimum_required(VERSION 3.16)

set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../../port/esp-idf")

# ... and this project lives OUTSIDE that directory on purpose. IDF treats every
# subdirectory of an EXTRA_COMPONENT_DIRS entry that holds a CMakeLists.txt as a
# component, so a project sitting next to the component gets scanned as one --
# which fails deep inside CMake with an error naming neither. port/esp-idf/
# therefore contains components and nothing else.

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(moy_example)
