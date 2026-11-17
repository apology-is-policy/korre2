#pragma once

// The spectrum shown in the player window: 100 columns from 20 Hz to 20 kHz, evenly spaced in
// pitch, each the level in its band on a decibel scale.
//
// The original display normalised every frame to its own strongest bin on a linear scale, so quiet
// and loud passages looked the same and only the peaks showed. Here the scale is fixed: 0 on the plot
// is -78 dBFS in a band, 1 is -6 dBFS.

#include <cstddef>
#include <span>
#include <vector>

struct PFFFT_Setup;

namespace korre
{

class spectrum
{
public:
    static constexpr int columns = 100;
    static constexpr double low_hz = 20.0;
    static constexpr double high_hz = 20000.0;
    static constexpr double floor_db = -78.0; ///< plotted as 0
    static constexpr double top_db = -6.0;    ///< plotted as 1

    spectrum();
    ~spectrum();
    spectrum(const spectrum&) = delete;
    spectrum& operator=(const spectrum&) = delete;

    /// Call when a track of a different sample rate starts. Clears the display.
    void set_sample_rate(double sample_rate);

    /// Adds the samples just played (one channel), oldest first.
    void feed(std::span<const float> samples);

    /// Recomputes the columns from the most recent samples. `elapsed_s` is the time since the last
    /// call: columns rise at once and fall at a fixed rate, so short peaks stay readable.
    void update(double elapsed_s);

    /// Lets the columns fall to nothing (playback stopped).
    void decay(double elapsed_s);

    /// The columns, each 0..1.
    const float* values() const noexcept { return shown_.data(); }

    /// The level a steady sine of the given amplitude reads in its column, in dB. For tests.
    double column_db(int column) const noexcept { return level_db_[static_cast<std::size_t>(column)]; }
    /// The column a frequency falls in (clamped to the ends).
    static int column_of(double hz) noexcept;

private:
    void rebuild();

    double sample_rate_ = 0;
    std::size_t size_ = 0; ///< FFT length
    PFFFT_Setup* setup_ = nullptr;
    float* in_ = nullptr;  ///< aligned, size_
    float* out_ = nullptr; ///< aligned, size_
    float* work_ = nullptr;
    std::vector<float> window_;
    std::vector<float> recent_; ///< the last size_ samples, a ring
    std::size_t write_ = 0;
    double window_sum_ = 1;

    std::vector<double> level_db_; ///< per column, before smoothing
    std::vector<float> shown_;     ///< per column, 0..1, smoothed
};

} // namespace korre
