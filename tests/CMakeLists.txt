# Tests are plain programs registered with CTest:  ctest --test-dir build --output-on-failure

set(KORRE_FIXTURES ${CMAKE_CURRENT_SOURCE_DIR}/fixtures)

function(korre_test name)
    add_executable(${name} ${name}.cpp)
    target_link_libraries(${name} PRIVATE korre_strict_warnings ${ARGN})
    target_compile_definitions(${name} PRIVATE KORRE_FIXTURES="${KORRE_FIXTURES}")
    add_test(NAME ${name} COMMAND ${name} WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
    # A sanitizer finding fails the test instead of only being printed.
    set_tests_properties(${name} PROPERTIES ENVIRONMENT
            "UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1;ASAN_OPTIONS=detect_leaks=0")
endfunction()

korre_test(test_audio korre_audio)
