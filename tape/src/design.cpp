#include "design.h"

#include <algorithm>
#include <cmath>
#include <numbers>

#include "fft.h"

namespace tape::detail
{
namespace
{

/// Index i such that xs[i] <= x < xs[i + 1], for x inside the table.
std::size_t bracket(const std::vector<double>& xs, double x) noexcept
{
    const auto it = std::upper_bound(xs.begin(), xs.end(), x);
    const auto i = static_cast<std::size_t>(it - xs.begin());
    return std::min(std::max<std::size_t>(i, 1), xs.size() - 1) - 1;
}

} // namespace

double interp(const std::vector<double>& xs, const std::vector<double>& ys, double x) noexcept
{
    if (x <= xs.front())
    {
        return ys.front();
    }
    if (x >= xs.back())
    {
        return ys.back();
    }
    const std::size_t i = bracket(xs, x);
    const double t = (x - xs[i]) / (xs[i + 1] - xs[i]);
    return ys[i] + t * (ys[i + 1] - ys[i]);
}

double psd_linear(const std::vector<double>& freqs, const std::vector<double>& psd, double f) noexcept
{
    if (f < freqs.front() || f > freqs.back())
    {
        return 0.0;
    }
    return interp(freqs, psd, f);
}

double psd_log(const std::vector<double>& freqs, const std::vector<double>& psd, double f) noexcept
{
    if (f < freqs.front() || f > freqs.back())
    {
        return 0.0;
    }
    const std::size_t i = bracket(freqs, f);
    const double t = (std::log(f) - std::log(freqs[i])) / (std::log(freqs[i + 1]) - std::log(freqs[i]));
    const double a = std::log(std::max(psd[i], 1e-30));
    const double b = std::log(std::max(psd[i + 1], 1e-30));
    return std::exp(a + t * (b - a));
}

response_curve::response_curve(const profile::response& eq, int channel)
    : freqs_(eq.freqs), db_(eq.db[static_cast<std::size_t>(channel)]), phase_(eq.phase[static_cast<std::size_t>(channel)])
{
    log_freqs_.reserve(freqs_.size());
    for (const double f : freqs_)
    {
        log_freqs_.push_back(std::log(f));
    }
    const std::size_t n = freqs_.size();
    const double octaves = std::log2(freqs_[12] / freqs_[0]);
    low_db_slope_ = (db_[12] - db_[0]) / octaves;
    low_phase_slope_ = (phase_[12] - phase_[0]) / octaves;
    high_phase_slope_ = (phase_[n - 1] - phase_[n - 7]) / (freqs_[n - 1] - freqs_[n - 7]);
}

std::complex<double> response_curve::operator()(double f) const noexcept
{
    const double floor_f = std::max(f, 1e-3);
    const double lf = std::log(floor_f);
    double db = interp(log_freqs_, db_, lf);
    double phase = interp(log_freqs_, phase_, lf);
    if (f < freqs_.front())
    {
        const double octaves_below = std::log2(freqs_.front() / floor_f);
        db = db_.front() - low_db_slope_ * octaves_below;
        phase = phase_.front() - low_phase_slope_ * octaves_below;
    }
    else if (f > freqs_.back())
    {
        phase = phase_.back() + high_phase_slope_ * (f - freqs_.back());
    }
    const double magnitude = std::pow(10.0, db / 20.0);
    if (f == 0)
    {
        return {magnitude, 0.0}; // a real filter: no phase at DC
    }
    return std::polar(magnitude, phase);
}

double flicker_depth(const std::vector<double>& freqs, const std::vector<double>& rms, double f) noexcept
{
    const double floor_f = std::max(f, 1.0);
    const auto depth = [&](std::size_t i) { return std::max(rms[i], 1e-6); };
    if (f < freqs.front())
    {
        const double slope = std::log(depth(1) / depth(0)) / std::log(freqs[1] / freqs[0]);
        return depth(0) * std::pow(floor_f / freqs.front(), std::max(slope, 0.0));
    }
    if (floor_f >= freqs.back())
    {
        return depth(freqs.size() - 1);
    }
    const std::size_t i = bracket(freqs, floor_f);
    const double t = (std::log(floor_f) - std::log(freqs[i])) / (std::log(freqs[i + 1]) - std::log(freqs[i]));
    return std::exp(std::log(depth(i)) + t * (std::log(depth(i + 1)) - std::log(depth(i))));
}

double held_depth(const std::vector<double>& freqs, const std::vector<double>& rms, double f) noexcept
{
    const double floor_f = std::max(f, 1.0);
    const auto depth = [&](std::size_t i) { return std::max(rms[i], 1e-6); };
    if (floor_f <= freqs.front())
    {
        return depth(0);
    }
    if (floor_f >= freqs.back())
    {
        return depth(freqs.size() - 1);
    }
    const std::size_t i = bracket(freqs, floor_f);
    const double t = (std::log(floor_f) - std::log(freqs[i])) / (std::log(freqs[i + 1]) - std::log(freqs[i]));
    return std::exp(std::log(depth(i)) + t * (std::log(depth(i + 1)) - std::log(depth(i))));
}

sizes sizes_for(double sample_rate) noexcept
{
    sizes s;
    // A third of a second: enough to follow the response down to the lowest bass, where it changes
    // fastest. Split in 16 partitions for the convolver.
    s.response_taps = pow2_ceil(static_cast<std::size_t>(std::lround(0.33 * sample_rate)));
    s.response_block = s.response_taps / 16;
    // 11.6 ms before time zero. The chain is causal, so what the measured table holds before that is
    // measurement ripple; this much keeps the ringing that band-limiting a sub-sample delay needs.
    s.response_pre = static_cast<std::size_t>(std::lround(0.0116 * sample_rate));
    s.flicker_half = static_cast<std::size_t>(std::lround(0.0029 * sample_rate));
    s.control_step = std::max<std::size_t>(1, static_cast<std::size_t>(std::lround(sample_rate / 187.5)));
    return s;
}

std::vector<double> response_filter(const profile& p, int channel, double sample_rate)
{
    const sizes s = sizes_for(sample_rate);
    const std::size_t taps = s.response_taps;
    const std::size_t pre = s.response_pre;
    const std::size_t n = 8 * taps; // design grid: fine enough for the table's own resolution in the bass
    const double mean_delay_s = (p.delay_us[0] + p.delay_us[1]) / 2.0 * 1e-6;

    const response_curve curve(p.eq, channel);
    std::vector<std::complex<double>> x(n);
    for (std::size_t k = 0; k <= n / 2; ++k)
    {
        const double f = static_cast<double>(k) * sample_rate / static_cast<double>(n);
        std::complex<double> h = curve(f);
        if (k > 0)
        {
            // The measured phase holds each channel's delay; take out the part common to both, so
            // that the output stays in time with the input.
            h *= std::polar(1.0, 2.0 * std::numbers::pi * f * mean_delay_s);
        }
        x[k] = h;
    }
    x[n / 2] = x[n / 2].real();
    for (std::size_t k = 1; k < n / 2; ++k)
    {
        x[n - k] = std::conj(x[k]);
    }
    fft(n).inverse(x.data());

    std::vector<double> out(taps);
    const std::size_t fall = taps / 4;
    for (std::size_t i = 0; i < taps; ++i)
    {
        double w = 1.0;
        if (i < pre)
        {
            const double v = std::sin(0.5 * std::numbers::pi * (static_cast<double>(i) + 0.5) / static_cast<double>(pre));
            w = v * v;
        }
        if (i >= taps - fall)
        {
            const double v = std::cos(0.5 * std::numbers::pi * (static_cast<double>(i - (taps - fall)) + 0.5) / static_cast<double>(fall));
            w *= v * v;
        }
        const std::size_t at = (i + n - pre) % n; // time i - pre, wrapped
        out[i] = x[at].real() / static_cast<double>(n) * w;
    }
    return out;
}

std::vector<double> flicker_filter(const std::vector<double>& freqs, const std::vector<double>& rms, double sample_rate, bool held)
{
    const std::size_t half = sizes_for(sample_rate).flicker_half;
    const std::size_t n = pow2_ceil(32 * half);

    std::vector<std::complex<double>> x(n);
    for (std::size_t k = 0; k <= n / 2; ++k)
    {
        const double f = static_cast<double>(k) * sample_rate / static_cast<double>(n);
        x[k] = held ? held_depth(freqs, rms, f) : flicker_depth(freqs, rms, f);
    }
    for (std::size_t k = 1; k < n / 2; ++k)
    {
        x[n - k] = x[k];
    }
    fft(n).inverse(x.data());

    std::vector<double> out(2 * half + 1);
    for (std::size_t i = 0; i < out.size(); ++i)
    {
        const double v = std::sin(std::numbers::pi * (static_cast<double>(i) + 1.0) / static_cast<double>(2 * half + 2));
        const std::size_t at = (i + n - half) % n;
        out[i] = x[at].real() / static_cast<double>(n) * v * v;
    }
    return out;
}

shelf high_shelf(double tau, double gain_db, double sample_rate) noexcept
{
    const double tau2 = tau / std::pow(10.0, gain_db / 20.0);
    const double k = 2.0 * sample_rate;
    const double norm = tau2 * k + 1.0;
    return {(tau * k + 1.0) / norm, (1.0 - tau * k) / norm, (1.0 - tau2 * k) / norm};
}

} // namespace tape::detail
