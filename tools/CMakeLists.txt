add_executable(korre-render render.cpp)
target_link_libraries(korre-render PRIVATE korre_strict_warnings korre_audio korre_tape)
install(TARGETS korre-render RUNTIME DESTINATION bin)
