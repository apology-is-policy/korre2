#include "spectrum.h"

#include <algorithm>
#include <cmath>
#include <numbers>

#include "pffft/pffft.h"

namespace korre
{
namespace
{

constexpr double fall_db_per_s = 36.0;

/// Lower edge of a column in Hz.
double column_edge(int column) { return spectrum::low_hz * std::pow(spectrum::high_hz / spectrum::low_hz, static_cast<double>(column) / spectrum::columns); }

} // namespace

spectrum::spectrum() : level_db_(columns, -200.0), shown_(columns, 0.0f) { set_sample_rate(44100); }

spectrum::~spectrum()
{
    if (setup_)
    {
        pffft_destroy_setup(setup_);
        pffft_aligned_free(in_);
        pffft_aligned_free(out_);
        pffft_aligned_free(work_);
    }
}

int spectrum::column_of(double hz) noexcept
{
    const double pos = columns * std::log(hz / low_hz) / std::log(high_hz / low_hz);
    return std::clamp(static_cast<int>(std::floor(pos)), 0, columns - 1);
}

void spectrum::set_sample_rate(double sample_rate)
{
    if (sample_rate == sample_rate_ || sample_rate <= 0)
    {
        return;
    }
    sample_rate_ = sample_rate;
    // About a sixth of a second: bins 5 to 6 Hz apart, enough to tell the bass columns apart.
    std::size_t size = 4096;
    while (static_cast<double>(size) < sample_rate / 6.0 && size < 65536)
    {
        size <<= 1;
    }
    if (size != size_)
    {
        size_ = size;
        rebuild();
    }
    std::fill(recent_.begin(), recent_.end(), 0.0f);
    std::fill(level_db_.begin(), level_db_.end(), -200.0);
    std::fill(shown_.begin(), shown_.end(), 0.0f);
}

void spectrum::rebuild()
{
    if (setup_)
    {
        pffft_destroy_setup(setup_);
        pffft_aligned_free(in_);
        pffft_aligned_free(out_);
        pffft_aligned_free(work_);
    }
    setup_ = pffft_new_setup(static_cast<int>(size_), PFFFT_REAL);
    in_ = static_cast<float*>(pffft_aligned_malloc(size_ * sizeof(float)));
    out_ = static_cast<float*>(pffft_aligned_malloc(size_ * sizeof(float)));
    work_ = static_cast<float*>(pffft_aligned_malloc(size_ * sizeof(float)));
    window_.resize(size_);
    window_sum_ = 0;
    for (std::size_t i = 0; i < size_; ++i)
    {
        // Hann: without a window a steady tone smears across the whole display.
        window_[i] = static_cast<float>(0.5 - 0.5 * std::cos(2.0 * std::numbers::pi * static_cast<double>(i) / static_cast<double>(size_)));
        window_sum_ += window_[i];
    }
    recent_.assign(size_, 0.0f);
    write_ = 0;
}

void spectrum::feed(std::span<const float> samples)
{
    for (const float v : samples)
    {
        recent_[write_] = v;
        write_ = write_ + 1 == size_ ? 0 : write_ + 1;
    }
}

void spectrum::update(double elapsed_s)
{
    for (std::size_t i = 0; i < size_; ++i)
    {
        in_[i] = recent_[(write_ + i) % size_] * window_[i];
    }
    pffft_transform_ordered(setup_, in_, out_, work_, PFFFT_FORWARD);

    // Power per bin, scaled so that a sine of amplitude 1 sums to 1 over the few bins the window
    // spreads it across (the Hann window's noise bandwidth is 1.5 bins).
    const double scale = 4.0 / (window_sum_ * window_sum_) / 1.5;
    const auto power = [&](std::size_t k) {
        const double re = out_[2 * k], im = out_[2 * k + 1];
        return (re * re + im * im) * scale;
    };
    const double bin_hz = sample_rate_ / static_cast<double>(size_);
    const std::size_t last_bin = size_ / 2 - 1;

    for (int c = 0; c < columns; ++c)
    {
        const double lo = column_edge(c) / bin_hz, hi = column_edge(c + 1) / bin_hz; // in bins
        double sum = 0;
        const auto first = static_cast<std::size_t>(std::ceil(lo));
        const auto end = static_cast<std::size_t>(std::ceil(hi)); // one past the last whole bin in the band
        if (first >= end)
        {
            // The band is narrower than a bin (the bass): the band's share of the power around it,
            // read between the two neighbouring bins.
            const double centre = 0.5 * (lo + hi);
            const auto k = std::min(static_cast<std::size_t>(centre), last_bin - 1);
            const double t = centre - static_cast<double>(k);
            sum = (power(std::max<std::size_t>(k, 1)) * (1.0 - t) + power(k + 1) * t) * (hi - lo);
        }
        else
        {
            for (std::size_t k = std::max<std::size_t>(first, 1); k < end && k <= last_bin; ++k)
            {
                sum += power(k);
            }
        }
        level_db_[static_cast<std::size_t>(c)] = 10.0 * std::log10(sum + 1e-20);
    }

    const auto fall = static_cast<float>(fall_db_per_s * elapsed_s / (top_db - floor_db));
    for (int c = 0; c < columns; ++c)
    {
        const auto i = static_cast<std::size_t>(c);
        const auto target = static_cast<float>(std::clamp((level_db_[i] - floor_db) / (top_db - floor_db), 0.0, 1.0));
        shown_[i] = std::max(target, shown_[i] - fall);
    }
}

void spectrum::decay(double elapsed_s)
{
    std::fill(recent_.begin(), recent_.end(), 0.0f);
    const auto fall = static_cast<float>(fall_db_per_s * elapsed_s / (top_db - floor_db));
    for (float& v : shown_)
    {
        v = std::max(0.0f, v - fall);
    }
}

} // namespace korre
