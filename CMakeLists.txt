cmake_minimum_required(VERSION 3.20)

project(korre VERSION 0.2.0 LANGUAGES C CXX)

# ---- build settings ---------------------------------------------------------------------------

if (NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "Build type" FORCE)
    set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS Debug Release RelWithDebInfo)
endif ()

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

option(KORRE_BUILD_PLAYER "Build the terminal player (needs PortAudio and ncursesw)" ON)
option(KORRE_BUILD_TESTS "Build the tests (run them with ctest)" ON)

# Sanitizer builds, in their own build directory:
#   cmake -S . -B build-asan -DCMAKE_BUILD_TYPE=Debug -DKORRE_SANITIZE=address
#   cmake -S . -B build-tsan -DCMAKE_BUILD_TYPE=Debug -DKORRE_SANITIZE=thread
# "address" also turns on the undefined-behaviour checks; "thread" cannot be combined with it.
set(KORRE_SANITIZE "" CACHE STRING "Sanitizer build: empty, 'address' or 'thread'")
set_property(CACHE KORRE_SANITIZE PROPERTY STRINGS "" address thread)

if (KORRE_SANITIZE STREQUAL "address")
    add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
    add_link_options(-fsanitize=address,undefined)
elseif (KORRE_SANITIZE STREQUAL "thread")
    add_compile_options(-fsanitize=thread -fno-omit-frame-pointer)
    add_link_options(-fsanitize=thread)
elseif (KORRE_SANITIZE)
    message(FATAL_ERROR "KORRE_SANITIZE must be empty, 'address' or 'thread' (got '${KORRE_SANITIZE}')")
endif ()

# Warnings apply to our own code only; the vendored libraries are built as they came.
add_library(korre_warnings INTERFACE)
target_compile_options(korre_warnings INTERFACE -Wall -Wextra -Wpedantic)

# New code (everything outside the imported player) is held to a stricter set.
add_library(korre_strict_warnings INTERFACE)
target_link_libraries(korre_strict_warnings INTERFACE korre_warnings)
target_compile_options(korre_strict_warnings INTERFACE -Wshadow -Wconversion -Wno-sign-conversion)

# ---- dependencies -----------------------------------------------------------------------------

find_library(FLAC_LIBRARY NAMES FLAC REQUIRED)
find_path(FLAC_INCLUDE_DIR NAMES FLAC/stream_decoder.h REQUIRED)

# ---- libraries --------------------------------------------------------------------------------

add_subdirectory(audio)   # reading and writing audio files

if (KORRE_BUILD_PLAYER)
    include(cmake/player.cmake)
endif ()

if (KORRE_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif ()
