#include "level_meter.h"

#include <algorithm>
#include <cmath>

namespace korre
{

void level_meter::set_mode(reading mode) noexcept
{
    if (mode != mode_)
    {
        mode_ = mode;
        reset();
    }
}

void level_meter::reset() noexcept
{
    for (int c = 0; c < 2; ++c)
    {
        power_[c] = 0.0;
        bar_[c] = mark_[c] = floor_db;
        held_s_[c] = 0.0;
    }
}

void level_meter::update(const float peak[2], const double energy[2], std::uint64_t frames, std::uint64_t clipped_total, double elapsed_s) noexcept
{
    elapsed_s = std::max(elapsed_s, 0.0);
    over_s_ = std::max(0.0, over_s_ - elapsed_s);
    if (clipped_total != clipped_seen_)
    {
        clipped_seen_ = clipped_total;
        over_s_ = over_s;
    }
    for (int c = 0; c < 2; ++c)
    {
        // The mean square always runs, so that the RMS reading is right from the moment it is chosen.
        const double mean_square = frames > 0 ? energy[c] / static_cast<double>(frames) : 0.0;
        const double keep = std::exp(-elapsed_s / rms_time_s);
        power_[c] = power_[c] * keep + mean_square * (1.0 - keep);

        if (mode_ == reading::peak)
        {
            const double now = peak[c] > 0 ? 20.0 * std::log10(static_cast<double>(peak[c])) : floor_db;
            bar_[c] = std::max({now, bar_[c] - peak_fall_db_s * elapsed_s, floor_db});
        }
        else
        {
            // Twice the mean square: a sine of amplitude 1 has a mean square of one half and reads 0 dB.
            bar_[c] = power_[c] > 0 ? std::max(10.0 * std::log10(2.0 * power_[c]), floor_db) : floor_db;
        }

        if (bar_[c] >= mark_[c])
        {
            mark_[c] = bar_[c];
            held_s_[c] = 0.0;
        }
        else
        {
            const double before = held_s_[c];
            held_s_[c] += elapsed_s;
            const double falling_s = held_s_[c] - std::max(before, hold_s); // the part of this step past the hold
            if (falling_s > 0)
            {
                mark_[c] = std::max({mark_[c] - mark_fall_db_s * falling_s, bar_[c], floor_db});
            }
        }
    }
}

} // namespace korre
