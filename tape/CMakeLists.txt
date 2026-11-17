# The tape engine: plays audio through a measured profile (profiles/*.json).
# It depends on nothing but the C++ standard library and the vendored JSON reader.

add_library(korre_tape STATIC
        src/profile.cpp
        src/fft.cpp
        src/noise.cpp
        src/design.cpp
        src/convolver.cpp
        src/engine.cpp)

target_include_directories(korre_tape PUBLIC include)
target_include_directories(korre_tape PRIVATE src)
target_include_directories(korre_tape SYSTEM PRIVATE ${CMAKE_SOURCE_DIR}/third_party)
target_link_libraries(korre_tape PRIVATE korre_strict_warnings)

# The tests reach into the engine's parts (FFT, convolver, filter design).
add_library(korre_tape_internals INTERFACE)
target_include_directories(korre_tape_internals INTERFACE src)
target_link_libraries(korre_tape_internals INTERFACE korre_tape)
