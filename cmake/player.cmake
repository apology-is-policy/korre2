# The terminal player: player/ on top of the playback core, with the patched imtui for the interface
# and pffft for the spectrum display.

# ncurses with wide characters (the box-drawing interface needs it). Homebrew keeps its ncurses out of
# the default search path, so look there first; a /usr/local build is found by the default search.
find_library(NCURSESW_LIBRARY NAMES ncursesw
        HINTS /opt/homebrew/opt/ncurses/lib /usr/local/opt/ncurses/lib REQUIRED)
get_filename_component(_ncursesw_lib_dir ${NCURSESW_LIBRARY} DIRECTORY)
find_path(NCURSESW_INCLUDE_DIR NAMES ncurses.h
        HINTS ${_ncursesw_lib_dir}/../include REQUIRED)
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

add_executable(kora
        player/main.cpp
        player/app.cpp
        player/player_window.cpp
        player/meter_window.cpp
        player/queue_window.cpp
        player/file_window.cpp
        player/frame.cpp
        player/tape_shelf.cpp)

# SYSTEM: imtui's and Dear ImGui's headers are not ours to warn about
target_include_directories(kora SYSTEM PRIVATE
        ${CMAKE_SOURCE_DIR}/imtui/include ${CMAKE_SOURCE_DIR}/imtui/third-party/imgui)
target_link_libraries(kora PRIVATE korre_strict_warnings korre_player_parts korre_playback korre_portaudio imtui-ncurses)

install(TARGETS kora RUNTIME DESTINATION bin)
install(DIRECTORY profiles/ DESTINATION share/korre/profiles FILES_MATCHING PATTERN "*.json")
