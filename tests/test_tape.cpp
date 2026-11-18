// The tape engine and its parts.
//
// These tests cover what can be checked without the Python model: the building blocks against
// straightforward reference computations, and the engine's own guarantees (delay, switching, bypass,
// reproducibility, independence of how the audio is cut into blocks). That the engine reproduces the
// model itself is checked by analysis/verify_engine.py.

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <numbers>
#include <sstream>
#include <string>
#include <vector>

#include "check.h"
#include "convolver.h"
#include "design.h"
#include "fft.h"
#include "noise.h"
#include "random.h"
#include "tape/engine.h"
#include "tape/profile.h"

namespace
{

using namespace tape;
using namespace tape::detail;

const std::filesystem::path profiles = KORRE_PROFILES;

std::vector<double> random_signal(std::size_t n, std::uint64_t seed, double scale = 1.0)
{
    rng r(seed);
    std::vector<double> x(n);
    for (auto& v : x)
    {
        v = scale * r.normal();
    }
    return x;
}

/// A second of something like music: a few tones and some noise, different in the two channels.
std::vector<float> test_audio(std::size_t frames, double sample_rate)
{
    rng r(7);
    std::vector<float> x(frames * 2);
    for (std::size_t i = 0; i < frames; ++i)
    {
        const double t = static_cast<double>(i) / sample_rate;
        const double tones = 0.2 * std::sin(2 * std::numbers::pi * 220 * t) + 0.1 * std::sin(2 * std::numbers::pi * 3300 * t) +
                             0.05 * std::sin(2 * std::numbers::pi * 9000 * t);
        x[2 * i] = static_cast<float>(tones + 0.02 * r.normal());
        x[2 * i + 1] = static_cast<float>(0.8 * tones + 0.02 * r.normal());
    }
    return x;
}

double rms(std::span<const float> x)
{
    double sum = 0;
    for (const float v : x)
    {
        sum += static_cast<double>(v) * v;
    }
    return std::sqrt(sum / static_cast<double>(x.size()));
}

void test_fft()
{
    const std::size_t n = 64;
    const auto re = random_signal(n, 1), im = random_signal(n, 2);
    std::vector<std::complex<double>> x(n), direct(n);
    for (std::size_t i = 0; i < n; ++i)
    {
        x[i] = {re[i], im[i]};
    }
    for (std::size_t k = 0; k < n; ++k)
    {
        for (std::size_t i = 0; i < n; ++i)
        {
            direct[k] += x[i] * std::polar(1.0, -2 * std::numbers::pi * static_cast<double>(k * i) / static_cast<double>(n));
        }
    }
    auto y = x;
    const fft f(n);
    f.forward(y.data());
    double worst = 0;
    for (std::size_t k = 0; k < n; ++k)
    {
        worst = std::max(worst, std::abs(y[k] - direct[k]));
    }
    CHECK_MSG(worst < 1e-12, "forward transform against the definition: " + std::to_string(worst));

    f.inverse(y.data());
    worst = 0;
    for (std::size_t i = 0; i < n; ++i)
    {
        worst = std::max(worst, std::abs(y[i] / static_cast<double>(n) - x[i]));
    }
    CHECK_MSG(worst < 1e-13, "inverse of forward: " + std::to_string(worst));

    CHECK(pow2_ceil(1) == 1 && pow2_ceil(1024) == 1024 && pow2_ceil(1025) == 2048);
    bool threw = false;
    try
    {
        fft bad(48);
    }
    catch (const std::invalid_argument&)
    {
        threw = true;
    }
    CHECK(threw);
}

void test_convolver()
{
    const std::size_t block = 16, taps = 64, n = 1000;
    const auto h = random_signal(taps, 3);
    const auto x = random_signal(n, 4);

    std::vector<double> direct(n, 0.0);
    for (std::size_t i = 0; i < n; ++i)
    {
        for (std::size_t j = 0; j < taps && j <= i; ++j)
        {
            direct[i] += h[j] * x[i - j];
        }
    }

    // In one go, and in pieces of awkward sizes: the same output, one block late.
    for (const std::size_t piece : {n, std::size_t{1}, std::size_t{7}, std::size_t{16}, std::size_t{33}})
    {
        partitioned_convolver conv(h, block);
        auto y = x;
        for (std::size_t at = 0; at < n; at += piece)
        {
            conv.process(y.data() + at, std::min(piece, n - at));
        }
        double worst = 0;
        for (std::size_t i = block; i < n; ++i)
        {
            worst = std::max(worst, std::fabs(y[i] - direct[i - block]));
        }
        CHECK_MSG(worst < 1e-12, "convolver in pieces of " + std::to_string(piece) + ": " + std::to_string(worst));
        bool silent_start = true;
        for (std::size_t i = 0; i < block; ++i)
        {
            silent_start = silent_start && y[i] == 0.0;
        }
        CHECK(silent_start);

        conv.reset();
        std::vector<double> zeros(200, 0.0);
        conv.process(zeros.data(), zeros.size());
        bool silent = true;
        for (const double v : zeros)
        {
            silent = silent && v == 0.0;
        }
        CHECK_MSG(silent, "nothing left in the convolver after reset()");
    }
}

void test_noise()
{
    // White noise of density 0.5 per Hz up to 100 Hz at a rate of 1000 Hz: variance 50.
    const auto psd = [](double f) { return f <= 100.0 ? 0.5 : 0.0; };
    spectral_noise noise(psd, 1000.0, 4096, rng(11));
    CHECK_NEAR(noise.sigma() * noise.sigma(), 50.0, 0.5);
    double sum = 0, sum2 = 0;
    const std::size_t n = 400000;
    for (std::size_t i = 0; i < n; ++i)
    {
        const double v = noise.next();
        sum += v;
        sum2 += v * v;
    }
    CHECK_NEAR(sum / static_cast<double>(n), 0.0, 0.1);
    CHECK_NEAR(sum2 / static_cast<double>(n), 50.0, 2.5);

    spectral_noise unit(psd, 1000.0, 4096, rng(12), true);
    CHECK_NEAR(unit.sigma(), 1.0, 1e-12);

    // The same seed gives the same signal; another stream of the same seed a different one.
    spectral_noise a(psd, 1000.0, 1024, rng(5, 1)), b(psd, 1000.0, 1024, rng(5, 1)), c(psd, 1000.0, 1024, rng(5, 2));
    bool same = true, different = false;
    for (int i = 0; i < 3000; ++i)
    {
        const double va = a.next();
        same = same && va == b.next();
        different = different || va != c.next();
    }
    CHECK(same);
    CHECK(different);

    // The interpolated slow signal keeps the variance of what it interpolates.
    const auto slow_psd = [](double f) { return f <= 40.0 ? 1.0 : 0.0; };
    slow_noise slow(slow_psd, 48000.0, 256, 1024, rng(13));
    sum2 = 0;
    const std::size_t m = 4000000;
    for (std::size_t i = 0; i < m; ++i)
    {
        const double v = slow.next();
        sum2 += v * v;
    }
    CHECK_NEAR(sum2 / static_cast<double>(m), slow.sigma() * slow.sigma(), 0.2 * slow.sigma() * slow.sigma());
}

void test_design()
{
    // interp follows numpy.interp: linear inside, held outside.
    const std::vector<double> xs{1, 2, 4}, ys{10, 20, 0};
    CHECK_NEAR(interp(xs, ys, 0.0), 10, 0);
    CHECK_NEAR(interp(xs, ys, 1.5), 15, 1e-12);
    CHECK_NEAR(interp(xs, ys, 3.0), 10, 1e-12);
    CHECK_NEAR(interp(xs, ys, 9.0), 0, 0);
    CHECK_NEAR(psd_linear(xs, ys, 0.5), 0, 0);
    CHECK_NEAR(psd_linear(xs, ys, 5.0), 0, 0);
    CHECK_NEAR(psd_log({10, 1000}, {1.0, 100.0}, 100.0), 10.0, 1e-9);

    // The shelf: unity at DC, the full gain at the top.
    const shelf s = high_shelf(70e-6, 18.0, 48000.0);
    CHECK_NEAR((s.b0 + s.b1) / (1 + s.a1), 1.0, 1e-12);
    CHECK_NEAR(20 * std::log10((s.b0 - s.b1) / (1 - s.a1)), 18.0, 1e-9);

    const sizes at44 = sizes_for(44100), at96 = sizes_for(96000);
    CHECK(at44.response_taps == 16384 && at44.response_block == 1024 && at44.response_pre == 512);
    CHECK(at44.flicker_half == 128 && at44.control_step == 235);
    CHECK(at96.response_taps == 32768 && at96.control_step == 512);
}

void test_profile()
{
    for (const char* name : {"wmd6c_xlii_sideA.json", "wmd6c_xlii_sideB.json", "wmd6c_metalxr.json"})
    {
        const auto p = load_profile(profiles / name);
        CHECK_MSG(p.has_value(), std::string(name) + (p ? "" : ": " + p.error()));
        if (p)
        {
            CHECK(p->version == 2);
            CHECK(p->eq.freqs.size() == 240);
            CHECK(!p->hiss.psd[0].empty() && !p->transport.psd_us2_per_hz.empty());
        }
    }
    const auto chrome = load_profile(profiles / "wmd6c_xlii_sideB.json");
    const auto metal = load_profile(profiles / "wmd6c_metalxr.json");
    if (chrome && metal)
    {
        CHECK(chrome->saturation.hf.has_value());
        CHECK(!metal->saturation.hf.has_value()); // none was found on the metal tape
        CHECK(chrome->tones.size() == 3);
        CHECK(metal->dropouts.events.size() == 1);
    }

    // Gain noise is an optional section: read when present, checked like the others.
    {
        std::ifstream file(profiles / "wmd6c_xlii_sideB.json");
        std::stringstream text;
        text << file.rdbuf();
        const std::string base = text.str();
        const auto at = base.find("\"dropouts\":");
        CHECK(at != std::string::npos);
        const auto with = [&](const std::string& section) { return base.substr(0, at) + section + base.substr(at); };
        const auto good = parse_profile(with(R"("gain_noise":{"rate_freqs":[1,150,4000],"rate_psd":[1,1,0.04],)"
                                             R"("depth_freqs":[1000,2000,4000],"depth_L":[0.02,0.02,0.015],"depth_R":[0.01,0.01,0.01]},)"));
        CHECK_MSG(good.has_value(), good ? std::string() : good.error());
        if (good)
        {
            CHECK(good->gain_noise.has_value());
            CHECK(good->gain_noise->depth[0].size() == 3 && good->gain_noise->depth[0][2] == 0.015);
            CHECK(good->gain_noise->depth[1][0] == 0.01 && good->gain_noise->rate_freqs.back() == 4000);
        }
        const auto bad = parse_profile(with(R"("gain_noise":{"rate_freqs":[1,150,4000],"rate_psd":[1,1,0.04],)"
                                            R"("depth_freqs":[1000,2000,4000],"depth_L":[0.02,0.02],"depth_R":[0.01,0.01,0.01]},)"));
        CHECK(!bad.has_value() && bad.error().find("gain noise") != std::string::npos);
        const auto none = parse_profile(base);
        CHECK(none.has_value() && !none->gain_noise.has_value());
    }

    CHECK(!load_profile(profiles / "no_such_profile.json").has_value());
    CHECK(!parse_profile("this is not json").has_value());
    const auto v1 = parse_profile(R"({"version": 1})");
    CHECK(!v1.has_value() && v1.error().find("version") != std::string::npos);
    const auto missing = parse_profile(R"({"version": 2, "gain_db": {"L": 0, "R": 0}})");
    CHECK(!missing.has_value() && missing.error().find("delay_us") != std::string::npos);
}

/// Runs frames through an engine in pieces of the given size (0: all at once).
std::vector<float> run(engine& e, const std::vector<float>& in, std::size_t piece = 0)
{
    std::vector<float> out(in.size());
    const std::size_t frames = in.size() / 2;
    if (piece == 0)
    {
        piece = frames;
    }
    for (std::size_t at = 0; at < frames; at += piece)
    {
        const std::size_t n = std::min(piece, frames - at);
        e.process(std::span(in).subspan(2 * at, 2 * n), std::span(out).subspan(2 * at, 2 * n));
    }
    return out;
}

bool delayed_copy(const std::vector<float>& in, const std::vector<float>& out, std::size_t delay)
{
    for (std::size_t i = 0; i < in.size() / 2; ++i)
    {
        for (int c = 0; c < 2; ++c)
        {
            const float want = i >= delay ? in[2 * (i - delay) + c] : 0.0f;
            if (out[2 * i + c] != want)
            {
                return false;
            }
        }
    }
    return true;
}

void test_engine()
{
    const auto loaded = load_profile(profiles / "wmd6c_xlii_sideB.json");
    CHECK(loaded.has_value());
    if (!loaded)
    {
        return;
    }
    const profile& p = *loaded;
    const double sr = 44100;
    const std::size_t frames = 30000;
    const auto audio = test_audio(frames, sr);

    settings plain;
    plain.sample_rate = sr;
    plain.record_gain_db = stereo{0.0, 0.0};
    plain.polarity = 1;

    // ---- the delay is what the engine says it is
    {
        settings s = plain;
        s.ingredients = 0;
        engine e(p, s);
        const latency lag = e.delay();
        CHECK(lag.total == lag.response + lag.timing + lag.flicker);
        CHECK(lag.response == 1024 + 512 && lag.flicker == 128);
        CHECK_MSG(lag.timing >= 33 && lag.timing < 300, std::to_string(lag.timing));
        CHECK_MSG(delayed_copy(audio, run(e, audio), lag.total), "nothing switched on: the input, delayed, sample for sample");
    }

    // ---- bypass passes the input through, equally late
    {
        engine e(p, plain);
        e.set_bypass(true);
        CHECK(e.bypass());
        const auto first = run(e, audio); // the switch is faded in: let it settle
        const auto out = run(e, audio);
        std::vector<float> both(audio);
        both.insert(both.end(), audio.begin(), audio.end());
        std::vector<float> got(first);
        got.insert(got.end(), out.begin(), out.end());
        bool same = true;
        const std::size_t lag = e.delay().total;
        for (std::size_t i = frames; i < 2 * frames; ++i)
        {
            same = same && got[2 * i] == both[2 * (i - lag)] && got[2 * i + 1] == both[2 * (i - lag) + 1];
        }
        CHECK_MSG(same, "bypass: the input, delayed, sample for sample");
    }

    // ---- everything on: a sane signal, the same however the audio is cut into blocks
    std::vector<float> reference;
    {
        engine e(p, plain);
        reference = run(e, audio);
        bool finite = true;
        for (const float v : reference)
        {
            finite = finite && std::isfinite(v);
        }
        CHECK(finite);
        const std::size_t skip = 2 * e.delay().total;
        const double ratio = rms(std::span(reference).subspan(skip)) / rms(std::span(audio).first(audio.size() - skip));
        CHECK_MSG(ratio > 0.7 && ratio < 1.3, "level through the tape: " + std::to_string(ratio));
    }
    for (const std::size_t piece : {std::size_t{1}, std::size_t{7}, std::size_t{255}, std::size_t{256}, std::size_t{257}, std::size_t{4096}})
    {
        engine e(p, plain);
        CHECK_MSG(run(e, audio, piece) == reference, "pieces of " + std::to_string(piece) + " frames");
    }
    {
        engine e(p, plain); // in and out in the same memory
        std::vector<float> buffer(audio);
        e.process(buffer, buffer);
        CHECK(buffer == reference);
    }

    // ---- the seed decides the random signals; the switches do not
    {
        settings other = plain;
        other.seed = 2;
        engine e(p, other);
        CHECK(run(e, audio) != reference);

        settings none = plain;
        none.ingredients = 0;
        engine with(p, plain), without(p, none);
        trace a, b;
        std::vector<float> out(audio.size());
        with.process(audio, out, a);
        without.process(audio, out, b);
        CHECK(a.transport == b.transport && a.differential == b.differential);
        CHECK(a.jitter_common == b.jitter_common && a.jitter_own == b.jitter_own);
        CHECK(a.flicker_common == b.flicker_common && a.flicker_own == b.flicker_own);
        CHECK(a.background == b.background && a.dropout_gain == b.dropout_gain);
        CHECK(a.transport.size() == frames && a.background[1].size() == frames);
        CHECK(a.response_filter[0].size() == 16384 && a.response_pre == 512 && a.flicker_filter_own.size() == 257);
    }

    // ---- polarity and output gain act on the whole output
    {
        settings flipped = plain;
        flipped.polarity = -1;
        flipped.output_gain_db = 20 * std::log10(2.0);
        engine e(p, flipped);
        const auto out = run(e, audio);
        double worst = 0;
        for (std::size_t i = 0; i < out.size(); ++i)
        {
            worst = std::max(worst, std::fabs(static_cast<double>(out[i]) + 2.0 * reference[i]));
        }
        CHECK_MSG(worst < 1e-6, "inverted and doubled: " + std::to_string(worst));
    }

    // ---- silence in: the tape's own background comes out, and reset() forgets the audio
    {
        engine e(p, plain);
        const std::vector<float> silence(2 * 44100, 0.0f);
        const auto out = run(e, silence);
        const double level = 20 * std::log10(rms(out));
        CHECK_MSG(level > -75 && level < -50, "background level " + std::to_string(level) + " dBFS");

        e.set_ingredients(0);
        run(e, audio);
        e.reset();
        const auto after = run(e, silence);
        // The switch to "nothing" is complete by now, so only a cleared engine gives exact silence.
        bool silent = true;
        for (const float v : after)
        {
            silent = silent && v == 0.0f;
        }
        CHECK_MSG(silent, "silence after reset() with everything switched off");
    }

    // ---- switching while running does not click: no jump larger than the signal's own
    {
        engine e(p, plain);
        std::vector<float> out(audio.size());
        const std::size_t half = frames / 2;
        e.process(std::span(audio).first(2 * half), std::span(out).first(2 * half));
        e.set_ingredients(0);
        e.process(std::span(audio).subspan(2 * half), std::span(out).subspan(2 * half));
        // Largest step between neighbouring samples: before the switch, around it, and after it.
        double biggest[3] = {0, 0, 0};
        for (std::size_t i = 2000; i < frames - 1; ++i)
        {
            const double jump = std::fabs(static_cast<double>(out[2 * (i + 1)]) - out[2 * i]);
            const int where = i < half - 10 ? 0 : i < half + 1500 ? 1 : 2;
            biggest[where] = std::max(biggest[where], jump);
        }
        CHECK_MSG(biggest[1] < 1.5 * std::max(biggest[0], biggest[2]),
                  "largest step " + std::to_string(biggest[1]) + " against " + std::to_string(std::max(biggest[0], biggest[2])));
    }

    // ---- gain noise: an amplitude noise of the depth the profile gives each channel
    {
        profile noisy = p;
        std::fill(noisy.flicker.depth_common.begin(), noisy.flicker.depth_common.end(), 0.0);
        std::fill(noisy.flicker.depth_indep.begin(), noisy.flicker.depth_indep.end(), 0.0);
        profile::gain_noise_set mn;
        mn.rate_freqs = {1.0, 200.0}; // slow enough to read off the envelope below
        mn.rate_psd = {1.0, 1.0};
        mn.depth_freqs = {1000.0, 4000.0};
        mn.depth = {std::vector<double>{0.03, 0.03}, std::vector<double>{0.0, 0.0}}; // 3% on the left, none on the right
        noisy.gain_noise = mn;

        settings s = plain;
        s.ingredients = static_cast<std::uint32_t>(ingredient::flicker);
        engine e(noisy, s);
        const std::size_t n = 44100 * 4;
        std::vector<float> tone(2 * n);
        for (std::size_t i = 0; i < n; ++i)
        {
            tone[2 * i] = tone[2 * i + 1] = static_cast<float>(0.5 * std::sin(2 * std::numbers::pi * 1000.0 * static_cast<double>(i) / sr));
        }
        const auto out = run(e, tone);
        // The tone's level in 2 ms pieces (two periods each): how much it wanders, relative to its mean.
        double wander[2];
        for (int c = 0; c < 2; ++c)
        {
            std::vector<double> level;
            const std::size_t piece = 88;
            for (std::size_t at = 4000; at + piece <= n; at += piece)
            {
                double sum = 0;
                for (std::size_t i = 0; i < piece; ++i)
                {
                    const double v = out[2 * (at + i) + static_cast<std::size_t>(c)];
                    sum += v * v;
                }
                level.push_back(std::sqrt(sum / static_cast<double>(piece)));
            }
            double mean = 0, var = 0;
            for (const double v : level)
            {
                mean += v;
            }
            mean /= static_cast<double>(level.size());
            for (const double v : level)
            {
                var += (v - mean) * (v - mean);
            }
            wander[c] = std::sqrt(var / static_cast<double>(level.size())) / mean;
        }
        CHECK_MSG(wander[0] > 0.022 && wander[0] < 0.033, "left: " + std::to_string(100 * wander[0]) + "% for a depth of 3%");
        CHECK_MSG(wander[1] < 0.002, "right: " + std::to_string(100 * wander[1]) + "% for a depth of 0");

        // Switched off with the flicker, and the same seed still gives the same other signals.
        e.set_ingredients(0);
        run(e, tone);
        const auto quiet = run(e, tone);
        bool steady = true;
        for (std::size_t i = 2 * 4000; i + 2 * 441 < quiet.size(); i += 2 * 441) // ten periods apart: equal samples
        {
            steady = steady && std::fabs(quiet[i] - quiet[i + 2 * 441]) < 1e-6f;
        }
        CHECK_MSG(steady, "no modulation left with the flicker switched off");
        settings both = plain;
        engine with_noise(noisy, both), without_noise(p, both);
        trace a, b;
        std::vector<float> scratch(audio.size());
        with_noise.process(audio, scratch, a);
        without_noise.process(audio, scratch, b);
        CHECK(a.transport == b.transport && a.jitter_own == b.jitter_own && a.flicker_own == b.flicker_own && a.background == b.background);
        CHECK(a.gain_noise[0] != b.gain_noise[0]);
    }

    // ---- other sample rates, and the other profiles
    for (const double rate : {22050.0, 48000.0, 88200.0, 96000.0, 192000.0})
    {
        settings s = plain;
        s.sample_rate = rate;
        engine e(p, s);
        const auto in = test_audio(6000, rate);
        const auto out = run(e, in);
        bool finite = true;
        for (const float v : out)
        {
            finite = finite && std::isfinite(v);
        }
        CHECK_MSG(finite, std::to_string(rate) + " Hz");
        CHECK_NEAR(static_cast<double>(e.delay().total) / rate, 1712.0 / 44100.0, 0.004);
    }
    for (const char* name : {"wmd6c_xlii_sideA.json", "wmd6c_metalxr.json"})
    {
        const auto other = load_profile(profiles / name);
        if (other)
        {
            engine e(*other, plain);
            const auto out = run(e, audio);
            CHECK_MSG(std::isfinite(rms(out)) && rms(out) > 0.01, name);
        }
    }
    bool threw = false;
    try
    {
        settings s = plain;
        s.sample_rate = 1000;
        engine e(p, s);
    }
    catch (const std::invalid_argument&)
    {
        threw = true;
    }
    CHECK(threw);
}

// The wobble's steady lines: sines of constant level, where the table's noise would fade in and out.
void test_lines()
{
    const auto loaded = load_profile(profiles / "wmd6c_xlii_sideB.json");
    CHECK(loaded.has_value());
    if (!loaded)
    {
        return;
    }
    CHECK(loaded->transport.lines.empty() && loaded->differential.lines.empty()); // an older profile has none
    // The first profile with lines: Shallow's stretch of the metal tape, the capstan's 7.53 Hz among them.
    {
        const auto shallow = load_profile(profiles / "wmd6c_metalxr_v2_MB2.json");
        CHECK_MSG(shallow.has_value(), shallow ? std::string() : shallow.error());
        if (shallow)
        {
            CHECK(shallow->transport.lines.size() == 17 && shallow->gain_noise.has_value());
            bool capstan = false;
            for (const auto& l : shallow->transport.lines)
            {
                capstan = capstan || (std::fabs(l.hz - 7.53) < 0.02 && l.us > 5.0 && l.us < 20.0);
            }
            CHECK(capstan);
        }
    }

    // Read from the profile's text, and refused when a line makes no sense.
    {
        std::ifstream file(profiles / "wmd6c_xlii_sideB.json");
        std::stringstream text;
        text << file.rdbuf();
        const std::string base = text.str();
        const auto at = base.find("\"crossover_hz\":");
        CHECK(at != std::string::npos);
        const auto with = [&](const std::string& section) { return base.substr(0, at) + section + base.substr(at); };
        const auto good = parse_profile(with(R"("lines":[{"hz":7.52,"us":6.5},{"hz":15.04,"us":1.5}],)"));
        CHECK_MSG(good.has_value(), good ? std::string() : good.error());
        if (good)
        {
            CHECK(good->transport.lines.size() == 2 && good->transport.lines[1].hz == 15.04 && good->transport.lines[0].us == 6.5);
        }
        const auto bad = parse_profile(with(R"("lines":[{"hz":0,"us":6.5}],)"));
        CHECK(!bad.has_value() && bad.error().find("lines") != std::string::npos);
        const auto incomplete = parse_profile(with(R"("lines":[{"hz":7.5}],)"));
        CHECK(!incomplete.has_value());
    }

    profile p = *loaded;
    std::fill(p.transport.psd_us2_per_hz.begin(), p.transport.psd_us2_per_hz.end(), 0.0);
    std::fill(p.differential.psd_us2_per_hz.begin(), p.differential.psd_us2_per_hz.end(), 0.0);
    const double crossover = p.transport.crossover_hz; // 45 Hz: the fade runs from 40 to 50
    p.transport.lines = {{7.5, 6.0}, {crossover + 2.0, 4.0}, {crossover + 15.0, 3.0}};
    p.differential.lines = {{1.5, 2.0}};

    const double sr = 44100;
    const std::size_t frames = 4 * 44100; // whole periods of every line but the faded one
    settings s;
    s.sample_rate = sr;
    const std::vector<float> silence(frames * 2, 0.0f);
    std::vector<float> out(silence.size());
    const auto traced = [&](std::uint64_t seed) {
        settings t = s;
        t.seed = seed;
        engine e(p, t);
        trace r;
        e.process(silence, out, r);
        return r;
    };
    const trace a = traced(1);

    // Level of one frequency in a stretch of a signal (peak), by projection.
    const auto level_at = [&](const std::vector<double>& x, double hz, std::size_t from, std::size_t n) {
        double re = 0, im = 0;
        for (std::size_t i = 0; i < n; ++i)
        {
            const double w = 2 * std::numbers::pi * hz * static_cast<double>(from + i) / sr;
            re += x[from + i] * std::cos(w);
            im += x[from + i] * std::sin(w);
        }
        return 2.0 * std::sqrt(re * re + im * im) / static_cast<double>(n);
    };
    const auto rms = [](const std::vector<double>& x) {
        double sum = 0;
        for (const double v : x)
        {
            sum += v * v;
        }
        return std::sqrt(sum / static_cast<double>(x.size()));
    };

    // The 7.5 Hz line has its level, and the same level in every second of the run.
    CHECK(a.transport.size() == frames);
    for (std::size_t second = 0; second < 4; ++second)
    {
        const double peak = level_at(a.transport, 7.5, second * 44100, 44100);
        CHECK_MSG(std::fabs(peak / (std::numbers::sqrt2 * 6.0) - 1.0) < 0.02, "7.5 Hz line in second " + std::to_string(second) + ": " + std::to_string(peak));
    }
    // The line 2 Hz above the crossover is 30% of the way down the fade (in power); the one 15 Hz above is gone.
    const double faded = 4.0 * std::sqrt(0.3);
    CHECK_NEAR(level_at(a.transport, crossover + 2.0, 0, frames), std::numbers::sqrt2 * faded, 0.05);
    CHECK(level_at(a.transport, crossover + 15.0, 0, frames) < 1e-6);
    CHECK_NEAR(rms(a.transport), std::sqrt(6.0 * 6.0 + faded * faded), 0.08);
    // The left-minus-right wobble has its own line.
    CHECK_NEAR(rms(a.differential), 2.0, 0.02);
    CHECK_NEAR(level_at(a.differential, 1.5, 0, frames), std::numbers::sqrt2 * 2.0, 0.02);

    // Another seed: other phases, the same levels. The same seed: the same signal.
    const trace b = traced(2), again = traced(1);
    CHECK(b.transport != a.transport);
    CHECK_NEAR(level_at(b.transport, 7.5, 0, frames), std::numbers::sqrt2 * 6.0, 0.05);
    CHECK(again.transport == a.transport && again.differential == a.differential);

    // The lines move the sound: a 1 kHz tone through the engine with only the transport on comes out
    // shifted in time by up to the lines' peak.
    {
        profile only = *loaded;
        std::fill(only.transport.psd_us2_per_hz.begin(), only.transport.psd_us2_per_hz.end(), 0.0);
        only.transport.lines = {{7.5, 20.0}};
        settings t = s;
        t.ingredients = static_cast<std::uint32_t>(ingredient::transport);
        t.record_gain_db = stereo{0.0, 0.0};
        t.polarity = 1;
        engine e(only, t);
        const std::size_t lag = e.delay().total;
        std::vector<float> in(frames * 2), result(frames * 2);
        for (std::size_t i = 0; i < frames; ++i)
        {
            in[2 * i] = in[2 * i + 1] = static_cast<float>(0.5 * std::sin(2 * std::numbers::pi * 1000.0 * static_cast<double>(i) / sr));
        }
        e.process(in, result);
        // The phase of the 1 kHz tone in 20 ms pieces, as a time shift in microseconds.
        const std::size_t piece = 882;
        double lowest = 1e9, highest = -1e9;
        for (std::size_t start = lag + 4410; start + piece + lag < frames; start += piece)
        {
            double re = 0, im = 0;
            for (std::size_t i = 0; i < piece; ++i)
            {
                const double w = 2 * std::numbers::pi * 1000.0 * static_cast<double>(start + i - lag) / sr;
                re += static_cast<double>(result[2 * (start + i)]) * std::sin(w);
                im += static_cast<double>(result[2 * (start + i)]) * std::cos(w);
            }
            const double shift_us = std::atan2(im, re) / (2 * std::numbers::pi * 1000.0) * 1e6;
            lowest = std::min(lowest, shift_us);
            highest = std::max(highest, shift_us);
        }
        // +-28.3 us peak; a 20 ms piece averages a 7.5 Hz swing down by about 4%
        CHECK_MSG(highest - lowest > 2 * 28.3 * 0.9 && highest - lowest < 2 * 28.3 * 1.02, "swing of the tone: " + std::to_string(highest - lowest) + " us");
    }
}

// The flat cubic: one level for both channels or one each, and the distortion it makes.
void test_cubic()
{
    std::ifstream file(profiles / "wmd6c_xlii_sideB.json");
    std::stringstream text;
    text << file.rdbuf();
    const std::string base = text.str();
    const auto at = base.find("\"cubic_rel_db\":");
    CHECK(at != std::string::npos);
    const auto value_end = base.find(',', at);
    const auto with = [&](const std::string& value) { return base.substr(0, at) + "\"cubic_rel_db\":" + value + base.substr(value_end); };

    const auto both = parse_profile(with("-41.5"));
    CHECK_MSG(both.has_value(), both ? std::string() : both.error());
    CHECK(both && both->saturation.cubic_rel_db[0] == -41.5 && both->saturation.cubic_rel_db[1] == -41.5);
    const auto each = parse_profile(with(R"({"L":-36.5,"R":-40.0})"));
    CHECK_MSG(each.has_value(), each ? std::string() : each.error());
    CHECK(each && each->saturation.cubic_rel_db[0] == -36.5 && each->saturation.cubic_rel_db[1] == -40.0);
    CHECK(!parse_profile(with(R"({"L":-36.5})")).has_value());
    CHECK(!parse_profile(with(R"("loud")")).has_value());
    if (!each)
    {
        return;
    }

    // A 1 kHz sine at the reference level through the saturation alone: its third harmonic.
    profile p = *each;
    p.saturation.hf.reset();
    p.saturation.ref_rms_dbfs = -20.0;
    p.saturation.cubic_rel_db = {-30.0, -40.0};
    settings s;
    s.sample_rate = 48000;
    s.ingredients = static_cast<std::uint32_t>(ingredient::saturation);
    s.record_gain_db = stereo{0.0, 0.0};
    s.polarity = 1;
    engine e(p, s);
    const std::size_t lag = e.delay().total, frames = lag + 9600;
    const double amplitude = 0.1 * std::numbers::sqrt2; // RMS 0.1 = -20 dBFS
    std::vector<float> in(frames * 2), out(frames * 2);
    for (std::size_t i = 0; i < frames; ++i)
    {
        in[2 * i] = in[2 * i + 1] = static_cast<float>(amplitude * std::sin(2 * std::numbers::pi * 1000.0 * static_cast<double>(i) / 48000.0));
    }
    e.process(in, out);
    const auto level_db = [&](int channel, double hz) {
        double re = 0, im = 0;
        const std::size_t from = lag + 480, n = 4800; // whole periods of 1 and 3 kHz
        for (std::size_t i = 0; i < n; ++i)
        {
            const double w = 2 * std::numbers::pi * hz * static_cast<double>(from + i) / 48000.0;
            re += static_cast<double>(out[2 * (from + i) + static_cast<std::size_t>(channel)]) * std::cos(w);
            im += static_cast<double>(out[2 * (from + i) + static_cast<std::size_t>(channel)]) * std::sin(w);
        }
        return 20 * std::log10(2.0 * std::sqrt(re * re + im * im) / static_cast<double>(n));
    };
    // The level in the profile is for music (a noise-like signal); for a sine at the same RMS the third
    // harmonic is 20 log10(2 / (4 sqrt(15))) = 17.8 dB further down, less 0.1 dB for the fundamental's own loss.
    const double third_left = level_db(0, 3000) - level_db(0, 1000), third_right = level_db(1, 3000) - level_db(1, 1000);
    CHECK_NEAR(third_left, -30.0 - 17.78 + 0.11, 0.05);
    CHECK_NEAR(third_right, -40.0 - 17.78 + 0.03, 0.05);
    CHECK_NEAR(third_left - third_right, 10.0, 0.1); // each channel its own
}

} // namespace

int main()
{
    test_fft();
    test_convolver();
    test_noise();
    test_design();
    test_profile();
    test_engine();
    test_lines();
    test_cubic();
    return check::result();
}
