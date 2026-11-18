#include "spectrum.h"

#include <algorithm>
#include <cmath>
#include <numbers>

#include "pffft/pffft.h"

namespace korre
{
namespace
{

/// A Hann window spreads a steady tone over three bins, and noise reads as if each bin were 1.5 bins
/// wide. A point is never analysed more finely than that.
constexpr double window_width_bins = 1.5;
/// At most this many overlapping windows are averaged per update, for the short ones.
constexpr std::size_t most_hops = 8;

struct aligned_free
{
    void operator()(float* p) const noexcept { pffft_aligned_free(p); }
};
using aligned = std::unique_ptr<float[], aligned_free>;

aligned allocate(std::size_t n) { return aligned(static_cast<float*>(pffft_aligned_malloc(n * sizeof(float)))); }

struct setup_free
{
    void operator()(PFFFT_Setup* s) const noexcept { pffft_destroy_setup(s); }
};

std::size_t pow2_at_least(double x)
{
    std::size_t n = 1;
    while (static_cast<double>(n) < x)
    {
        n <<= 1;
    }
    return n;
}

} // namespace

struct spectrum::analysis
{
    std::size_t size;
    std::unique_ptr<PFFFT_Setup, setup_free> setup;
    aligned in, out, work;
    std::vector<float> window;
    double scale;              ///< squared magnitude -> power, a full-scale sine summing to 1 over its three bins
    std::vector<double> power; ///< per bin, the mean over the windows looked at
    std::vector<double> area;  ///< area[k]: the power from bin 0 to bin k, the bins joined by straight lines

    explicit analysis(std::size_t n)
        : size(n), setup(pffft_new_setup(static_cast<int>(n), PFFFT_REAL)), in(allocate(n)), out(allocate(n)), work(allocate(n)), window(n),
          power(n / 2, 0.0), area(n / 2, 0.0)
    {
        double sum = 0;
        for (std::size_t i = 0; i < n; ++i)
        {
            window[i] = static_cast<float>(0.5 - 0.5 * std::cos(2.0 * std::numbers::pi * static_cast<double>(i) / static_cast<double>(n)));
            sum += window[i];
        }
        scale = 4.0 / (sum * sum) / window_width_bins;
    }

    /// Power between two positions on the bin axis (fractions allowed).
    double between(double lo, double hi) const noexcept
    {
        const auto upto = [this](double x) {
            x = std::clamp(x, 0.0, static_cast<double>(power.size() - 1));
            const auto k = std::min(static_cast<std::size_t>(x), power.size() - 2);
            const double t = x - static_cast<double>(k);
            return area[k] + power[k] * t + (power[k + 1] - power[k]) * t * t / 2.0;
        };
        return upto(hi) - upto(lo);
    }
};

spectrum::spectrum(int columns)
    : columns_(std::max(columns, 2)), level_db_(static_cast<std::size_t>(columns_), -200.0), shown_(static_cast<std::size_t>(columns_), 0.0f)
{
    set_sample_rate(44100);
}

spectrum::~spectrum() = default;

int spectrum::column_of(double hz) const noexcept
{
    const double pos = columns_ * std::log(hz / low_hz) / std::log(high_hz / low_hz);
    return std::clamp(static_cast<int>(std::floor(pos)), 0, columns_ - 1);
}

double spectrum::window_seconds(int column) const noexcept
{
    return static_cast<double>(sizes_[size_of_column_[static_cast<std::size_t>(column)]]->size) / sample_rate_;
}

void spectrum::set_sample_rate(double sample_rate)
{
    if (sample_rate <= 0)
    {
        return;
    }
    if (sample_rate != sample_rate_)
    {
        sample_rate_ = sample_rate;
        rebuild();
    }
    clear();
}

void spectrum::rebuild()
{
    // From about 5 ms (the top of the treble) to about a sixth of a second (bins 5 to 6 Hz apart: the
    // bass cannot be told apart more finely without lagging behind the music).
    const std::size_t shortest = pow2_at_least(sample_rate_ * 0.005);
    const std::size_t longest = std::max(pow2_at_least(sample_rate_ / 6.0), shortest);
    sizes_.clear();
    for (std::size_t n = shortest; n <= longest; n <<= 1)
    {
        sizes_.push_back(std::make_unique<analysis>(n));
    }

    // Each point gets the shortest window whose resolution is no coarser than the point is wide.
    size_of_column_.assign(static_cast<std::size_t>(columns_), sizes_.size() - 1);
    const double ratio = std::pow(high_hz / low_hz, 1.0 / columns_);
    for (int c = 0; c < columns_; ++c)
    {
        const double lo = low_hz * std::pow(ratio, c);
        const double width_hz = lo * (ratio - 1.0);
        for (std::size_t s = 0; s < sizes_.size(); ++s)
        {
            if (window_width_bins * sample_rate_ / static_cast<double>(sizes_[s]->size) <= width_hz)
            {
                size_of_column_[static_cast<std::size_t>(c)] = s;
                break;
            }
        }
    }
    recent_.assign(longest, 0.0f);
    write_ = 0;
}

void spectrum::feed(std::span<const float> samples)
{
    for (const float v : samples)
    {
        recent_[write_] = v;
        write_ = write_ + 1 == recent_.size() ? 0 : write_ + 1;
    }
    fresh_ += samples.size();
}

void spectrum::clear()
{
    std::fill(recent_.begin(), recent_.end(), 0.0f);
    std::fill(level_db_.begin(), level_db_.end(), -200.0);
    std::fill(shown_.begin(), shown_.end(), 0.0f);
    fresh_ = 0;
}

void spectrum::update()
{
    const std::size_t ring = recent_.size();
    for (const auto& a : sizes_)
    {
        const std::size_t n = a->size, hop = n / 2;
        // Enough windows, half overlapping, to cover what was fed since the last update.
        const std::size_t fit = (ring - n) / hop + 1;
        const std::size_t hops = std::clamp((fresh_ + hop - 1) / hop, std::size_t{1}, std::min(most_hops, fit));
        std::fill(a->power.begin(), a->power.end(), 0.0);
        for (std::size_t h = 0; h < hops; ++h)
        {
            const std::size_t start = (write_ + 2 * ring - n - h * hop) % ring; // the window ends h hops before the newest sample
            for (std::size_t i = 0; i < n; ++i)
            {
                a->in[i] = recent_[(start + i) % ring] * a->window[i];
            }
            pffft_transform_ordered(a->setup.get(), a->in.get(), a->out.get(), a->work.get(), PFFFT_FORWARD);
            const double share = a->scale / static_cast<double>(hops);
            for (std::size_t k = 1; k < n / 2; ++k) // bin 0 (what does not move) is left out
            {
                const double re = a->out[2 * k], im = a->out[2 * k + 1];
                a->power[k] += (re * re + im * im) * share;
            }
        }
        a->area[0] = 0.0;
        for (std::size_t k = 1; k < n / 2; ++k)
        {
            a->area[k] = a->area[k - 1] + 0.5 * (a->power[k - 1] + a->power[k]);
        }
    }
    fresh_ = 0;

    const double ratio = std::pow(high_hz / low_hz, 1.0 / columns_);
    for (int c = 0; c < columns_; ++c)
    {
        const auto i = static_cast<std::size_t>(c);
        const analysis& a = *sizes_[size_of_column_[i]];
        const double bin_hz = sample_rate_ / static_cast<double>(a.size);
        const double lo = low_hz * std::pow(ratio, c) / bin_hz, hi = lo * ratio; // the point's band, in bins
        // Where the band is narrower than the window can resolve (the bass), the window's own width
        // is taken, so a tone still reads its full level there, on a few points at once.
        const double centre = 0.5 * (lo + hi), half = 0.5 * std::max(hi - lo, window_width_bins);
        const double sum = a.between(centre - half, centre + half);
        level_db_[i] = 10.0 * std::log10(sum + 1e-20);
        shown_[i] = static_cast<float>(std::clamp((level_db_[i] - floor_db) / (top_db - floor_db), 0.0, 1.0));
    }
}

} // namespace korre
