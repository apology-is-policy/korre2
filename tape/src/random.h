#pragma once

// Random numbers for the engine: a small, fast generator with a fixed algorithm, so that a seed gives
// the same wobble on every machine (the standard library's distributions differ between vendors).

#include <cmath>
#include <cstdint>

namespace tape::detail
{

/// xoshiro256++ (Blackman and Vigna), seeded through splitmix64.
class rng
{
public:
    /// `stream` separates the engine's random processes: each gets its own sequence from one seed.
    explicit rng(std::uint64_t seed, std::uint64_t stream = 0) noexcept
    {
        std::uint64_t x = seed ^ (0x9E3779B97F4A7C15ull * (stream + 1));
        for (auto& s : state_)
        {
            x += 0x9E3779B97F4A7C15ull;
            std::uint64_t z = x;
            z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
            z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
            s = z ^ (z >> 31);
        }
    }

    std::uint64_t next() noexcept
    {
        const std::uint64_t result = rotl(state_[0] + state_[3], 23) + state_[0];
        const std::uint64_t t = state_[1] << 17;
        state_[2] ^= state_[0];
        state_[3] ^= state_[1];
        state_[1] ^= state_[2];
        state_[0] ^= state_[3];
        state_[2] ^= t;
        state_[3] = rotl(state_[3], 45);
        return result;
    }

    /// Uniform in [0, 1).
    double uniform() noexcept { return static_cast<double>(next() >> 11) * 0x1.0p-53; }

    /// Standard normal (Marsaglia's polar method; the second value of each pair is kept for the next call).
    double normal() noexcept
    {
        if (have_spare_)
        {
            have_spare_ = false;
            return spare_;
        }
        double u, v, s;
        do
        {
            u = 2.0 * uniform() - 1.0;
            v = 2.0 * uniform() - 1.0;
            s = u * u + v * v;
        } while (s >= 1.0 || s == 0.0);
        const double f = std::sqrt(-2.0 * std::log(s) / s);
        spare_ = v * f;
        have_spare_ = true;
        return u * f;
    }

private:
    static std::uint64_t rotl(std::uint64_t x, int k) noexcept { return (x << k) | (x >> (64 - k)); }

    std::uint64_t state_[4];
    double spare_ = 0;
    bool have_spare_ = false;
};

} // namespace tape::detail
