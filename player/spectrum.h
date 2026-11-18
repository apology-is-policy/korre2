#pragma once

// The spectrum shown in the player window: a curve from 20 Hz to 20 kHz, evenly spaced in pitch, on
// a decibel scale.
//
// Each point is analysed with the shortest stretch of sound that still tells it from its neighbours.
// A point high in the treble is hundreds of Hz wide, so a few milliseconds are enough and it follows
// the music at once; a point in the bass is a few Hz wide and needs a sixth of a second, so it moves
// slowly and together with the points around it. (One long window for everything, as before, made
// the treble as sluggish as the bass.) There is no hold and no smoothing: what is drawn is what is
// sounding now.
//
// The scale is fixed: 0 on the plot is floor_db in a point's band, 1 is top_db, with a full-scale sine
// at 0 dB.

#include <cstddef>
#include <memory>
#include <span>
#include <vector>

namespace korre
{

class spectrum
{
public:
    static constexpr double low_hz = 20.0;
    static constexpr double high_hz = 20000.0;
    static constexpr double floor_db = -72.0; ///< plotted as 0
    static constexpr double top_db = -12.0;   ///< plotted as 1

    /// `columns` points along the frequency axis (the display draws two per character cell).
    explicit spectrum(int columns = 152);
    ~spectrum();
    spectrum(const spectrum&) = delete;
    spectrum& operator=(const spectrum&) = delete;

    int columns() const noexcept { return columns_; }

    /// Call when a track of a different sample rate starts. Clears the display.
    void set_sample_rate(double sample_rate);

    /// Adds the samples just played (one channel), oldest first.
    void feed(std::span<const float> samples);

    /// Recomputes the points from the most recent samples. A point with a short window takes in all
    /// the sound fed since the last call (the mean power of several windows), so a click between two
    /// frames is not missed and steady noise reads the same whatever the frame rate.
    void update();

    /// Forgets the samples and empties the display (playback stopped).
    void clear();

    /// The points, each 0..1.
    std::span<const float> values() const noexcept { return shown_; }

    /// The level in a point's band in dB; a steady full-scale sine reads about 0 at its own point.
    double column_db(int column) const noexcept { return level_db_[static_cast<std::size_t>(column)]; }
    /// The point a frequency falls on (clamped to the ends).
    int column_of(double hz) const noexcept;
    /// Length in seconds of the stretch of sound a point is analysed from.
    double window_seconds(int column) const noexcept;

private:
    struct analysis; ///< one FFT length: its plan, window and the power per bin
    void rebuild();

    int columns_;
    double sample_rate_ = 0;
    std::vector<std::unique_ptr<analysis>> sizes_; ///< shortest first
    std::vector<std::size_t> size_of_column_;      ///< index into sizes_
    std::vector<float> recent_;                    ///< the latest samples, a ring as long as the longest window
    std::size_t write_ = 0;
    std::size_t fresh_ = 0; ///< samples fed since the last update()

    std::vector<double> level_db_;
    std::vector<float> shown_;
};

} // namespace korre
