# The terminal player: the imported korre sources, the patched imtui, pffft for the spectrum display.

# ncurses with wide characters (the box-drawing interface needs it). Homebrew keeps its ncurses out of
# the default search path, so look there first; a /usr/local build is found by the default search.
find_library(NCURSESW_LIBRARY NAMES ncursesw
        HINTS /opt/homebrew/opt/ncurses/lib /usr/local/opt/ncurses/lib REQUIRED)
get_filename_component(_ncursesw_lib_dir ${NCURSESW_LIBRARY} DIRECTORY)
find_path(NCURSESW_INCLUDE_DIR NAMES ncurses.h
        HINTS ${_ncursesw_lib_dir}/../include REQUIRED)
find_library(PORTAUDIO_LIBRARY NAMES portaudio REQUIRED)
find_path(PORTAUDIO_INCLUDE_DIR NAMES portaudio.h REQUIRED)
find_library(FLACPP_LIBRARY NAMES FLAC++ REQUIRED)
message(STATUS "ncursesw:  ${NCURSESW_LIBRARY}")
message(STATUS "portaudio: ${PORTAUDIO_LIBRARY}")

# imtui and its Dear ImGui, built by their own CMake files
set(IMTUI_STANDALONE OFF)
set(IMTUI_LIBRARY_TYPE STATIC)
set(IMTUI_SUPPORT_NCURSES ON)
set(CURSES_INCLUDE_DIR ${NCURSESW_INCLUDE_DIR})
set(CURSES_LIBRARIES ${NCURSESW_LIBRARY})
add_subdirectory(imtui/third-party)
add_subdirectory(imtui/src)

add_library(pffft STATIC pffft/pffft.c)
target_include_directories(pffft PUBLIC ${CMAKE_SOURCE_DIR})

add_executable(kora
        main.cpp
        src/elements/korre.cpp
        src/elements/player.cpp
        src/elements/queue.cpp
        src/elements/audio_select.cpp
        src/elements/meter.cpp
        src/windowth.cpp
        src/tukey.cpp
        src/sampler.cpp
        src/sinks/sink.cpp
        src/sinks/portaudio_sink.cpp
        src/sources/wave.cpp
        src/sources/wave_source.cpp
        src/decoders/flac_decode.cpp
        src/decoders/mp3_decode.cpp)

# The imported sources are C++17 (u8 string literals changed type in C++20); they move to C++23
# with the rest of the rewrite.
set_target_properties(kora PROPERTIES CXX_STANDARD 17)
target_include_directories(kora PRIVATE ${CMAKE_SOURCE_DIR} ${CMAKE_SOURCE_DIR}/include ${CMAKE_SOURCE_DIR}/imtui)
target_include_directories(kora SYSTEM PRIVATE
        ${PORTAUDIO_INCLUDE_DIR} ${FLAC_INCLUDE_DIR} ${NCURSESW_INCLUDE_DIR} ${CMAKE_SOURCE_DIR}/third_party/minimp3)
target_link_libraries(kora PRIVATE
        korre_warnings imtui-ncurses pffft ${PORTAUDIO_LIBRARY} ${FLAC_LIBRARY} ${FLACPP_LIBRARY})

install(TARGETS kora RUNTIME DESTINATION bin)
