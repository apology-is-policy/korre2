#pragma once

// The numbers behind the level meter: for each channel a bar and a mark that sticks at the highest
// point the bar has reached.
//
// Two ways of reading the level, as on a tape deck's meter switch:
//   peak  the largest sample: the bar jumps up at once and falls back at 12 dB a second;
//   rms   the power averaged over about a third of a second, the way a needle moves. A full-scale
//         sine reads 0 dB in both, so one scale serves the two (plain RMS would read 3 dB less).
// The mark stays where the bar last pushed it for a second and a half, then falls at 6 dB a second
// until the bar meets it again.

#include <cstdint>

namespace korre
{

class level_meter
{
public:
    enum class reading
    {
        rms,
        peak,
    };

    static constexpr double floor_db = -96.0;      ///< "nothing"
    static constexpr double peak_fall_db_s = 12.0; ///< how fast the bar falls back in peak reading
    static constexpr double rms_time_s = 0.3;      ///< averaging time of the RMS reading
    static constexpr double hold_s = 1.5;          ///< how long the mark stays put
    static constexpr double mark_fall_db_s = 6.0;  ///< and how fast it falls after that
    static constexpr double over_s = 2.0;          ///< how long the OVER lamp stays lit

    reading mode() const noexcept { return mode_; }
    /// Switching the reading restarts the bars and marks: the two are not on the same footing.
    void set_mode(reading mode) noexcept;

    /// What was played since the last call (per channel: the largest sample, the sum of the squared
    /// samples, over `frames` frames; none while nothing plays), how many samples have hit full scale
    /// in all, and how much time went by.
    void update(const float peak[2], const double energy[2], std::uint64_t frames, std::uint64_t clipped_total, double elapsed_s) noexcept;

    /// Bars and marks back to nothing.
    void reset() noexcept;

    double bar_db(int channel) const noexcept { return bar_[channel]; }
    double mark_db(int channel) const noexcept { return mark_[channel]; }
    /// Samples hit full scale within the last two seconds.
    bool over() const noexcept { return over_s_ > 0; }

private:
    reading mode_ = reading::rms;
    double power_[2] = {0.0, 0.0};          ///< the running mean square, for the RMS reading
    double bar_[2] = {floor_db, floor_db};
    double mark_[2] = {floor_db, floor_db};
    double held_s_[2] = {0.0, 0.0};         ///< how long each mark has been where it is
    std::uint64_t clipped_seen_ = 0;
    double over_s_ = 0.0;                   ///< how much longer the OVER lamp stays lit
};

} // namespace korre
