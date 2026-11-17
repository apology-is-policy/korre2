# Reading and writing audio files: WAV, FLAC (libFLAC) and MP3 (the vendored minimp3).

add_library(korre_audio STATIC
        src/audio_file.cpp
        src/reader_wav.cpp
        src/reader_flac.cpp
        src/reader_mp3.cpp
        src/writers.cpp)

target_include_directories(korre_audio PUBLIC include)
# SYSTEM: no warnings from other people's headers (minimp3's implementation is compiled from its header)
target_include_directories(korre_audio SYSTEM PRIVATE ${FLAC_INCLUDE_DIR} ${CMAKE_SOURCE_DIR}/third_party/minimp3)
target_link_libraries(korre_audio PRIVATE korre_strict_warnings ${FLAC_LIBRARY})
