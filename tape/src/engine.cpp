#include "tape/engine.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <numbers>
#include <stdexcept>

#include "convolver.h"
#include "design.h"
#include "noise.h"
#include "random.h"

namespace tape
{
namespace
{

using namespace detail;

constexpr std::size_t chunk = 256; ///< frames worked on at a time

// The moving delay reads the signal between samples with a Kaiser-windowed sinc: the same kernel as
// analysis/align.py's warp(), tabulated at 2048 fractions and interpolated between them.
constexpr std::size_t warp_taps = 48;
constexpr std::size_t warp_half = warp_taps / 2;
constexpr std::size_t warp_phases = 2048;
constexpr double warp_beta = 9.0;
constexpr double warp_cutoff = 0.95;

/// Each random process draws from its own sequence, so none depends on how much another has used.
enum stream : std::uint64_t
{
    stream_transport = 1,
    stream_differential,
    stream_jitter_common,
    stream_jitter_left,
    stream_jitter_right,
    stream_flicker_common,
    stream_flicker_left,
    stream_flicker_right,
    stream_hiss_left,
    stream_hiss_right,
    stream_dropouts,
    stream_tones,
};

double from_db(double db) noexcept { return std::pow(10.0, db / 20.0); }

double bessel_i0(double x) noexcept
{
    double sum = 1, term = 1;
    for (int k = 1; k < 80; ++k)
    {
        term *= (x / (2.0 * k)) * (x / (2.0 * k));
        sum += term;
    }
    return sum;
}

/// Sum of a[i] * b[i]. Four running sums let the compiler use vector instructions, which a single
/// running sum would forbid (it fixes the order of the additions).
double dot(const double* a, const double* b, std::size_t n) noexcept
{
    double s0 = 0, s1 = 0, s2 = 0, s3 = 0;
    std::size_t i = 0;
    for (; i + 4 <= n; i += 4)
    {
        s0 += a[i] * b[i];
        s1 += a[i + 1] * b[i + 1];
        s2 += a[i + 2] * b[i + 2];
        s3 += a[i + 3] * b[i + 3];
    }
    for (; i < n; ++i)
    {
        s0 += a[i] * b[i];
    }
    return (s0 + s1) + (s2 + s3);
}

/// A gain between 0 and 1 that moves to its target in a straight line, so switching never clicks.
class fade
{
public:
    void configure(double step, bool on) noexcept
    {
        step_ = step;
        value_ = target_ = on ? 1.0 : 0.0;
    }
    void aim(bool on) noexcept { target_ = on ? 1.0 : 0.0; }
    double next() noexcept
    {
        if (value_ < target_)
        {
            value_ = std::min(target_, value_ + step_);
        }
        else if (value_ > target_)
        {
            value_ = std::max(target_, value_ - step_);
        }
        return value_;
    }

private:
    double value_ = 1, target_ = 1, step_ = 1;
};

/// A delay of a whole number of samples.
class delay_line
{
public:
    explicit delay_line(std::size_t length = 0) : buffer_(std::max<std::size_t>(length, 1), 0.0), length_(length) {}

    double step(double in) noexcept
    {
        if (length_ == 0)
        {
            return in;
        }
        const double out = buffer_[pos_];
        buffer_[pos_] = in;
        pos_ = pos_ + 1 == length_ ? 0 : pos_ + 1;
        return out;
    }
    void reset() noexcept { std::fill(buffer_.begin(), buffer_.end(), 0.0); }

private:
    std::vector<double> buffer_;
    std::size_t length_;
    std::size_t pos_ = 0;
};

/// One first-order section, y[n] = b0 x[n] + b1 x[n-1] - a1 y[n-1].
struct one_pole
{
    double b0 = 1, b1 = 0, a1 = 0, z = 0;
    double step(double x) noexcept
    {
        const double y = b0 * x + z;
        z = b1 * x - a1 * y;
        return y;
    }
};

/// The moving delay of one channel: a ring of recent samples read at a fractional position.
class warp_line
{
public:
    warp_line(std::size_t rest_delay, const std::vector<double>& kernel)
        : kernel_(kernel), rest_(static_cast<double>(rest_delay)), mask_(pow2_ceil(2 * rest_delay + 2 * warp_taps) - 1),
          ring_(mask_ + 1 + warp_taps, 0.0)
    {
    }

    /// Takes the next sample in and returns the signal `rest_delay + shift` samples ago. The caller
    /// keeps `shift` within +-(rest_delay - warp_half - 1).
    double step(double in, double shift) noexcept
    {
        // The first warp_taps samples are repeated after the end of the ring, so the taps of one read
        // are always next to each other in memory.
        const std::size_t at = write_ & mask_;
        ring_[at] = in;
        if (at < warp_taps)
        {
            ring_[at + mask_ + 1] = in;
        }

        if (shift == 0.0)
        {
            // No timing at all (every timing ingredient switched off): the sample itself, untouched.
            // The interpolation kernel would shave off the top twentieth of the band.
            const double out = ring_[(write_ - static_cast<std::uint64_t>(rest_)) & mask_];
            ++write_;
            return out;
        }

        const double pos = static_cast<double>(write_) - rest_ - shift;
        const double whole = std::floor(pos);
        const double scaled = (pos - whole) * static_cast<double>(warp_phases);
        const auto row = std::min(static_cast<std::size_t>(scaled), warp_phases - 1);
        const double blend = scaled - static_cast<double>(row);
        const std::size_t first = (static_cast<std::size_t>(static_cast<std::int64_t>(whole)) - (warp_half - 1)) & mask_;

        const double* x = ring_.data() + first;
        const double* k0 = kernel_.data() + row * warp_taps;
        const double a = dot(x, k0, warp_taps);
        const double b = dot(x, k0 + warp_taps, warp_taps);
        ++write_;
        return a + blend * (b - a);
    }

    void reset() noexcept { std::fill(ring_.begin(), ring_.end(), 0.0); }

private:
    const std::vector<double>& kernel_;
    double rest_;
    std::size_t mask_;
    std::vector<double> ring_;
    std::uint64_t write_ = std::uint64_t{1} << 20; ///< starts well above zero so positions never go negative
};

std::vector<double> make_warp_kernel()
{
    std::vector<double> kernel((warp_phases + 1) * warp_taps);
    const double i0_beta = bessel_i0(warp_beta);
    for (std::size_t row = 0; row <= warp_phases; ++row)
    {
        const double frac = static_cast<double>(row) / static_cast<double>(warp_phases);
        double* h = kernel.data() + row * warp_taps;
        double sum = 0;
        for (std::size_t j = 0; j < warp_taps; ++j)
        {
            // Tap j is the sample (j - 23) places from the one just below the read position.
            const double dist = frac - (static_cast<double>(j) - static_cast<double>(warp_half - 1));
            const double r = dist / static_cast<double>(warp_half);
            const double window = bessel_i0(warp_beta * std::sqrt(std::max(0.0, 1.0 - r * r))) / i0_beta;
            const double x = std::numbers::pi * warp_cutoff * dist;
            const double sinc = std::fabs(x) < 1e-12 ? 1.0 : std::sin(x) / x;
            h[j] = warp_cutoff * sinc * window;
            sum += h[j];
        }
        for (std::size_t j = 0; j < warp_taps; ++j)
        {
            h[j] /= sum;
        }
    }
    return kernel;
}

/// The two flicker filters of one channel, fed from one history of the signal.
class flicker_filters
{
public:
    flicker_filters(const std::vector<double>& common, const std::vector<double>& own)
        : common_(common), own_(own), taps_(common.size()), history_(2 * common.size(), 0.0)
    {
    }

    /// Takes the next sample in; returns the signal delayed by half the filter length, and through
    /// each filter.
    void step(double in, double& delayed, double& via_common, double& via_own) noexcept
    {
        // Each sample is stored twice, taps_ apart, so the last taps_ samples are always contiguous.
        history_[pos_] = in;
        history_[pos_ + taps_] = in;
        pos_ = pos_ + 1 == taps_ ? 0 : pos_ + 1;
        const double* recent = history_.data() + pos_; // oldest first
        delayed = recent[taps_ / 2];
        via_common = dot(recent, common_.data(), taps_); // the filters are symmetric: direction does not matter
        via_own = dot(recent, own_.data(), taps_);
    }

    void reset() noexcept { std::fill(history_.begin(), history_.end(), 0.0); }

private:
    const std::vector<double>& common_;
    const std::vector<double>& own_;
    std::size_t taps_;
    std::vector<double> history_;
    std::size_t pos_ = 0;
};

/// Short dips in level, drawn at random from the measured ones.
class dropout_source
{
public:
    dropout_source(const profile::dropout_set& set, double sample_rate, rng random)
        : events_(set.events), sample_rate_(sample_rate), random_(random)
    {
        rate_per_sample_ = events_.empty() ? 0.0 : set.rate_per_min / 60.0 / sample_rate;
        schedule();
    }

    /// Gain of the two channels for the next sample.
    void step(double& left, double& right) noexcept
    {
        left = right = 1.0;
        if (rate_per_sample_ > 0 && countdown_-- == 0)
        {
            start();
            schedule();
        }
        for (auto& a : active_)
        {
            if (a.length == 0)
            {
                continue;
            }
            const double s = std::sin(std::numbers::pi * static_cast<double>(a.pos) / static_cast<double>(a.length));
            const double g = 1.0 - a.depth * s * s;
            if (a.channels & 1)
            {
                left *= g;
            }
            if (a.channels & 2)
            {
                right *= g;
            }
            if (++a.pos == a.length)
            {
                a.length = 0;
            }
        }
    }

private:
    struct running
    {
        std::size_t pos = 0, length = 0; ///< length 0: free slot
        double depth = 0;
        int channels = 0;
    };

    void schedule() noexcept
    {
        if (rate_per_sample_ <= 0)
        {
            return;
        }
        // Time to the next event of a Poisson process.
        const double wait = -std::log(1.0 - random_.uniform()) / rate_per_sample_;
        countdown_ = static_cast<std::uint64_t>(std::min(wait, 1e15));
    }

    void start() noexcept
    {
        const auto& e = events_[static_cast<std::size_t>(random_.uniform() * static_cast<double>(events_.size())) % events_.size()];
        const int channels = e.both ? 3 : (random_.uniform() < 0.5 ? 1 : 2);
        for (auto& a : active_)
        {
            if (a.length == 0)
            {
                a.pos = 0;
                a.length = std::max<std::size_t>(static_cast<std::size_t>(e.dur_ms / 1e3 * sample_rate_), 64);
                a.depth = 1.0 - from_db(e.depth_db);
                a.channels = channels;
                return;
            }
        }
    }

    std::vector<profile::dropout_event> events_;
    double sample_rate_;
    rng random_;
    double rate_per_sample_ = 0;
    std::uint64_t countdown_ = 0;
    running active_[8];
};

/// One of the deck's steady tones.
struct tone_source
{
    double step = 0;  ///< radians per sample
    double angle = 0; ///< running phase, kept within one turn
    stereo amplitude{};
    double left_lead = 0; ///< phase of the left channel relative to the right
};

} // namespace

struct engine::impl
{
    impl(const profile& p, const settings& s);

    void run(const float* in, float* out, std::size_t frames, trace* record);
    void work(const float* in, float* out, std::size_t n, trace* record);
    void reset() noexcept;

    double sample_rate;
    sizes size;
    latency lag;

    stereo record_gain{};
    double output_gain = 1;
    double cubic = 0;           ///< coefficient of the flat cubic, 0 if the profile has none
    bool treble_saturation = false;
    double treble_cubic = 0;
    double timing_scale = 0;    ///< samples per microsecond
    double timing_limit = 0;    ///< the largest shift the delay line allows, in samples

    std::vector<double> response_taps[2];
    std::vector<double> flicker_common_taps, flicker_own_taps;
    std::vector<double> warp_kernel;

    std::vector<one_pole> emphasis, deemphasis; // per channel
    std::vector<partitioned_convolver> response;
    std::vector<delay_line> response_dry;
    std::vector<warp_line> warp;
    std::vector<flicker_filters> flicker;
    std::vector<delay_line> bypass_dry;

    std::vector<slow_noise> slow;        // transport, differential
    std::vector<spectral_noise> fast;    // jitter common, left, right; flicker common, left, right; hiss left, right
    dropout_source dropouts;
    std::vector<tone_source> tones;

    fade g_eq, g_transport, g_differential, g_jitter, g_flicker, g_dropouts, g_hiss, g_saturation, g_wet;
    std::atomic<std::uint32_t> ingredient_mask;
    std::atomic<bool> bypassed{false};

    double left[chunk], right[chunk]; // the block being worked on
};

engine::impl::impl(const profile& p, const settings& s)
    : sample_rate(s.sample_rate), size(sizes_for(s.sample_rate)),
      dropouts(p.dropouts, s.sample_rate, rng(s.seed, stream_dropouts)), ingredient_mask(s.ingredients)
{
    if (!(sample_rate >= 8000.0 && sample_rate <= 384000.0))
    {
        throw std::invalid_argument("the tape engine works at sample rates from 8 to 384 kHz");
    }

    // ---- levels
    const stereo gain_db = s.record_gain_db.value_or(p.gain_db);
    const int polarity = s.polarity != 0 ? s.polarity : p.polarity;
    record_gain = {from_db(gain_db[0]), from_db(gain_db[1])};
    output_gain = from_db(s.output_gain_db) * (polarity < 0 ? -1.0 : 1.0);

    // ---- saturation
    if (p.saturation.ref_rms_dbfs)
    {
        // The cubic that puts the third harmonic of a signal at the reference level `cubic_rel_db`
        // below it.
        const double sigma = from_db(*p.saturation.ref_rms_dbfs);
        cubic = from_db(p.saturation.cubic_rel_db) / (std::sqrt(15.0) * sigma * sigma);
    }
    emphasis.resize(2);
    deemphasis.resize(2);
    if (p.saturation.hf)
    {
        treble_saturation = true;
        treble_cubic = p.saturation.hf->c;
        const shelf sh = high_shelf(p.saturation.hf->tau_s, p.saturation.hf->shelf_db, sample_rate);
        for (int c = 0; c < 2; ++c)
        {
            emphasis[c] = {sh.b0, sh.b1, sh.a1, 0.0};
            deemphasis[c] = {1.0 / sh.b0, sh.a1 / sh.b0, sh.b1 / sh.b0, 0.0}; // the exact inverse
        }
    }

    // ---- static response
    for (int c = 0; c < 2; ++c)
    {
        response_taps[c] = response_filter(p, c, sample_rate);
        response.emplace_back(response_taps[c], size.response_block);
        response_dry.emplace_back(size.response_block + size.response_pre);
    }
    lag.response = size.response_block + size.response_pre;

    // ---- the random signals. Slow ones run at a low control rate with blocks of 8192 samples
    // (0.023 Hz apart, the resolution of the profile's tables); fast ones at the audio rate with
    // blocks of about 1.4 s.
    const std::size_t slow_block = 8192;
    const std::size_t fast_block = pow2_ceil(static_cast<std::size_t>(1.3 * sample_rate));
    const auto stagger = [&](std::size_t i) { return i * (fast_block / 2 / 8); };

    const auto transport_psd = [&p](double f) {
        // The transport hands over to the jitter with a 10 Hz wide fade around the crossover.
        const double fade_out = std::clamp((p.transport.crossover_hz + 5.0 - f) / 10.0, 0.0, 1.0);
        return psd_linear(p.transport.freqs, p.transport.psd_us2_per_hz, f) * fade_out;
    };
    const auto differential_psd = [&p](double f) { return psd_linear(p.differential.freqs, p.differential.psd_us2_per_hz, f); };
    slow.reserve(2);
    slow.emplace_back(transport_psd, sample_rate, size.control_step, slow_block, rng(s.seed, stream_transport));
    slow.emplace_back(differential_psd, sample_rate, size.control_step, slow_block, rng(s.seed, stream_differential));

    const auto jitter_common = [&p](double f) { return psd_log(p.jitter.freqs, p.jitter.psd_common_us2_per_hz, f); };
    const auto jitter_own = [&p](double f) { return psd_log(p.jitter.freqs, p.jitter.psd_indep_us2_per_hz, f); };
    const auto flicker_rate = [&p](double f) { return psd_log(p.flicker.rate_freqs, p.flicker.rate_psd, f); };
    const auto hiss_left = [&p](double f) { return psd_linear(p.hiss.freqs, p.hiss.psd[0], f); };
    const auto hiss_right = [&p](double f) { return psd_linear(p.hiss.freqs, p.hiss.psd[1], f); };
    fast.reserve(8);
    fast.emplace_back(jitter_common, sample_rate, fast_block, rng(s.seed, stream_jitter_common), false, stagger(0));
    fast.emplace_back(jitter_own, sample_rate, fast_block, rng(s.seed, stream_jitter_left), false, stagger(1));
    fast.emplace_back(jitter_own, sample_rate, fast_block, rng(s.seed, stream_jitter_right), false, stagger(2));
    fast.emplace_back(flicker_rate, sample_rate, fast_block, rng(s.seed, stream_flicker_common), true, stagger(3));
    fast.emplace_back(flicker_rate, sample_rate, fast_block, rng(s.seed, stream_flicker_left), true, stagger(4));
    fast.emplace_back(flicker_rate, sample_rate, fast_block, rng(s.seed, stream_flicker_right), true, stagger(5));
    fast.emplace_back(hiss_left, sample_rate, fast_block, rng(s.seed, stream_hiss_left), false, stagger(6));
    fast.emplace_back(hiss_right, sample_rate, fast_block, rng(s.seed, stream_hiss_right), false, stagger(7));

    // ---- timing: room in the delay line for eight standard deviations of the wobble
    timing_scale = 1e-6 * sample_rate;
    const double sigma_us = std::sqrt(slow[0].sigma() * slow[0].sigma() + 0.25 * slow[1].sigma() * slow[1].sigma() +
                                      fast[0].sigma() * fast[0].sigma() + fast[1].sigma() * fast[1].sigma());
    timing_limit = std::max(8.0, std::ceil(8.0 * sigma_us * timing_scale));
    const auto rest = static_cast<std::size_t>(timing_limit) + warp_half + 1;
    warp_kernel = make_warp_kernel();
    warp.reserve(2);
    warp.emplace_back(rest, warp_kernel);
    warp.emplace_back(rest, warp_kernel);
    lag.timing = rest;

    // ---- flicker
    flicker_common_taps = flicker_filter(p.flicker.depth_freqs, p.flicker.depth_common, sample_rate);
    flicker_own_taps = flicker_filter(p.flicker.depth_freqs, p.flicker.depth_indep, sample_rate);
    flicker.reserve(2);
    flicker.emplace_back(flicker_common_taps, flicker_own_taps);
    flicker.emplace_back(flicker_common_taps, flicker_own_taps);
    lag.flicker = size.flicker_half;

    lag.total = lag.response + lag.timing + lag.flicker;
    bypass_dry.emplace_back(lag.total);
    bypass_dry.emplace_back(lag.total);

    // ---- steady tones, each starting at a random phase
    rng tone_random(s.seed, stream_tones);
    for (const auto& t : p.tones)
    {
        tone_source src;
        src.step = 2.0 * std::numbers::pi * t.hz / sample_rate;
        src.angle = tone_random.uniform() * 2.0 * std::numbers::pi;
        src.amplitude = {std::numbers::sqrt2 * from_db(t.dbfs[0]), std::numbers::sqrt2 * from_db(t.dbfs[1])};
        src.left_lead = t.phase_deg * std::numbers::pi / 180.0;
        tones.push_back(src);
    }

    // ---- switches
    const double step = 1.0 / (0.02 * sample_rate); // 20 ms from off to on
    const auto on = [&](ingredient i) { return (s.ingredients & static_cast<std::uint32_t>(i)) != 0; };
    g_eq.configure(step, on(ingredient::eq));
    g_transport.configure(step, on(ingredient::transport));
    g_differential.configure(step, on(ingredient::differential));
    g_jitter.configure(step, on(ingredient::jitter));
    g_flicker.configure(step, on(ingredient::flicker));
    g_dropouts.configure(step, on(ingredient::dropouts));
    g_hiss.configure(step, on(ingredient::hiss));
    g_saturation.configure(step, on(ingredient::saturation));
    g_wet.configure(step, true);
}

void engine::impl::reset() noexcept
{
    for (int c = 0; c < 2; ++c)
    {
        emphasis[c].z = deemphasis[c].z = 0;
        response[c].reset();
        response_dry[c].reset();
        warp[c].reset();
        flicker[c].reset();
        bypass_dry[c].reset();
    }
}

void engine::impl::run(const float* in, float* out, std::size_t frames, trace* record)
{
    const std::uint32_t mask = ingredient_mask.load(std::memory_order_relaxed);
    const auto on = [mask](ingredient i) { return (mask & static_cast<std::uint32_t>(i)) != 0; };
    g_eq.aim(on(ingredient::eq));
    g_transport.aim(on(ingredient::transport));
    g_differential.aim(on(ingredient::differential));
    g_jitter.aim(on(ingredient::jitter));
    g_flicker.aim(on(ingredient::flicker));
    g_dropouts.aim(on(ingredient::dropouts));
    g_hiss.aim(on(ingredient::hiss));
    g_saturation.aim(on(ingredient::saturation));
    g_wet.aim(!bypassed.load(std::memory_order_relaxed));

    while (frames > 0)
    {
        const std::size_t n = std::min(frames, chunk);
        work(in, out, n, record);
        in += 2 * n;
        out += 2 * n;
        frames -= n;
    }
}

void engine::impl::work(const float* in, float* out, std::size_t n, trace* record)
{
    double* x[2] = {left, right};

    // ---- record gain and saturation
    for (std::size_t i = 0; i < n; ++i)
    {
        const double g = g_saturation.next();
        for (int c = 0; c < 2; ++c)
        {
            double y = static_cast<double>(in[2 * i + c]) * record_gain[c];
            y -= g * cubic * y * y * y;
            if (treble_saturation)
            {
                // Tape saturates on what is recorded, and the recorded signal has its treble boosted:
                // boost, bend, and undo the boost exactly, so that quiet sound passes unchanged.
                double u = emphasis[c].step(y);
                u -= g * treble_cubic * u * u * u;
                y = deemphasis[c].step(u);
            }
            x[c][i] = y;
        }
    }

    // ---- static response. The unfiltered signal is kept alongside, equally late, for switching.
    double dry[2][chunk];
    for (int c = 0; c < 2; ++c)
    {
        for (std::size_t i = 0; i < n; ++i)
        {
            dry[c][i] = response_dry[c].step(x[c][i]);
        }
        response[c].process(x[c], n);
    }
    for (std::size_t i = 0; i < n; ++i)
    {
        const double g = g_eq.next();
        x[0][i] = dry[0][i] + g * (x[0][i] - dry[0][i]);
        x[1][i] = dry[1][i] + g * (x[1][i] - dry[1][i]);
    }

    // ---- timing
    for (std::size_t i = 0; i < n; ++i)
    {
        const double transport = slow[0].next();
        const double differential = slow[1].next();
        const double jitter_common = fast[0].next();
        const double jitter_own[2] = {fast[1].next(), fast[2].next()};
        const double gt = g_transport.next(), gd = g_differential.next(), gj = g_jitter.next();
        const double common = gt * transport + gj * jitter_common;
        for (int c = 0; c < 2; ++c)
        {
            const double us = common + (c == 0 ? 0.5 : -0.5) * gd * differential + gj * jitter_own[c];
            const double shift = std::clamp(us * timing_scale, -timing_limit, timing_limit);
            x[c][i] = warp[c].step(x[c][i], shift);
        }
        if (record)
        {
            record->transport.push_back(transport);
            record->differential.push_back(differential);
            record->jitter_common.push_back(jitter_common);
            record->jitter_own[0].push_back(jitter_own[0]);
            record->jitter_own[1].push_back(jitter_own[1]);
        }
    }

    // ---- amplitude flicker, dropouts, background, output
    for (std::size_t i = 0; i < n; ++i)
    {
        const double flicker_common = fast[3].next();
        const double flicker_own[2] = {fast[4].next(), fast[5].next()};
        const double hiss[2] = {fast[6].next(), fast[7].next()};
        double gain[2];
        dropouts.step(gain[0], gain[1]);

        double background[2] = {hiss[0], hiss[1]};
        for (auto& t : tones)
        {
            background[0] += t.amplitude[0] * std::cos(t.angle + t.left_lead);
            background[1] += t.amplitude[1] * std::cos(t.angle);
            t.angle += t.step;
            if (t.angle > 2.0 * std::numbers::pi)
            {
                t.angle -= 2.0 * std::numbers::pi;
            }
        }

        const double gf = g_flicker.next(), gdr = g_dropouts.next(), gh = g_hiss.next(), gw = g_wet.next();
        for (int c = 0; c < 2; ++c)
        {
            double delayed, via_common, via_own;
            flicker[c].step(x[c][i], delayed, via_common, via_own);
            double y = delayed - gf * (flicker_common * via_common + flicker_own[c] * via_own);
            y *= 1.0 + gdr * (gain[c] - 1.0);
            y += gh * background[c];
            y *= output_gain;

            const double original = bypass_dry[c].step(static_cast<double>(in[2 * i + c]));
            out[2 * i + c] = static_cast<float>(original + gw * (y - original));
        }
        if (record)
        {
            record->flicker_common.push_back(flicker_common);
            for (int c = 0; c < 2; ++c)
            {
                record->flicker_own[c].push_back(flicker_own[c]);
                record->dropout_gain[c].push_back(gain[c]);
                record->background[c].push_back(background[c]);
            }
        }
    }
}

engine::engine(const profile& p, const settings& s) : impl_(std::make_unique<impl>(p, s)) {}
engine::~engine() = default;
engine::engine(engine&&) noexcept = default;
engine& engine::operator=(engine&&) noexcept = default;

void engine::process(std::span<const float> in, std::span<float> out) noexcept
{
    impl_->run(in.data(), out.data(), std::min(in.size(), out.size()) / 2, nullptr);
}

void engine::process(std::span<const float> in, std::span<float> out, trace& record)
{
    if (record.response_filter[0].empty())
    {
        record.response_filter = {impl_->response_taps[0], impl_->response_taps[1]};
        record.response_pre = impl_->size.response_pre;
        record.flicker_filter_common = impl_->flicker_common_taps;
        record.flicker_filter_own = impl_->flicker_own_taps;
    }
    impl_->run(in.data(), out.data(), std::min(in.size(), out.size()) / 2, &record);
}

latency engine::delay() const noexcept { return impl_->lag; }

void engine::set_ingredients(std::uint32_t mask) noexcept { impl_->ingredient_mask.store(mask, std::memory_order_relaxed); }
std::uint32_t engine::ingredients() const noexcept { return impl_->ingredient_mask.load(std::memory_order_relaxed); }
void engine::set_bypass(bool on) noexcept { impl_->bypassed.store(on, std::memory_order_relaxed); }
bool engine::bypass() const noexcept { return impl_->bypassed.load(std::memory_order_relaxed); }
void engine::reset() noexcept { impl_->reset(); }

} // namespace tape
