#pragma once

// A minimal test harness: CHECK records a failure and carries on, so one run reports everything
// that is wrong. Each test program ends with `return check::result();`.

#include <cmath>
#include <cstdio>
#include <string>

namespace check
{

inline int checks = 0;
inline int failures = 0;

inline void record(bool ok, const char* file, int line, const std::string& what)
{
    ++checks;
    if (!ok)
    {
        ++failures;
        std::fprintf(stderr, "FAILED %s:%d: %s\n", file, line, what.c_str());
    }
}

inline int result()
{
    std::printf("%d checks, %d failed\n", checks, failures);
    return failures == 0 ? 0 : 1;
}

} // namespace check

#define CHECK(cond) ::check::record(static_cast<bool>(cond), __FILE__, __LINE__, #cond)

#define CHECK_MSG(cond, msg) ::check::record(static_cast<bool>(cond), __FILE__, __LINE__, std::string(#cond) + ": " + (msg))

#define CHECK_NEAR(a, b, tol)                                                                              \
    ::check::record(std::fabs(static_cast<double>(a) - static_cast<double>(b)) <= (tol), __FILE__, __LINE__, \
                    std::string(#a " ~ " #b ": ") + std::to_string(static_cast<double>(a)) + " vs " +       \
                        std::to_string(static_cast<double>(b)) + " (tolerance " + std::to_string(tol) + ")")
