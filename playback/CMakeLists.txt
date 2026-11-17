# Playback: a decoder thread, the tape engine and a lock-free queue to the audio callback.
# No user interface in here; the audio device sits behind korre::audio_output.

add_library(korre_playback STATIC src/playback.cpp)
target_include_directories(korre_playback PUBLIC include)
target_link_libraries(korre_playback PUBLIC korre_audio korre_tape PRIVATE korre_strict_warnings)

# The one piece that needs a sound card library, built only with the player.
if (KORRE_BUILD_PLAYER)
    find_library(PORTAUDIO_LIBRARY NAMES portaudio REQUIRED)
    find_path(PORTAUDIO_INCLUDE_DIR NAMES portaudio.h REQUIRED)
    add_library(korre_portaudio STATIC src/portaudio_output.cpp)
    target_include_directories(korre_portaudio PUBLIC include)
    target_include_directories(korre_portaudio SYSTEM PRIVATE ${PORTAUDIO_INCLUDE_DIR})
    target_link_libraries(korre_portaudio PUBLIC ${PORTAUDIO_LIBRARY} PRIVATE korre_strict_warnings)
endif ()
