// The audio file readers and writers.
//
// The fixtures were written by ffmpeg (tests/fixtures/make_fixtures.sh) and hold a known signal, so the
// decoders are checked against a formula and an independent encoder, not against korre's own writers.

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <numbers>
#include <vector>

#include "check.h"
#include "korre/audio_file.h"

namespace
{

const std::filesystem::path fixtures = KORRE_FIXTURES;

double expected_left(double t) { return 0.5 * std::sin(2 * std::numbers::pi * 441 * t); }
double expected_right(double t) { return 0.25 * std::cos(2 * std::numbers::pi * 1000 * t); }

/// Largest and RMS deviation of a clip from the known signal, over frames [from, to).
struct deviation
{
    double max = 0;
    double rms = 0;
};

deviation compare(std::span<const float> samples, std::uint32_t sample_rate, bool mono, std::size_t from, std::size_t to,
                  std::size_t first_frame = 0)
{
    deviation d;
    double sum = 0;
    for (std::size_t i = from; i < to; ++i)
    {
        const double t = static_cast<double>(first_frame + i) / sample_rate;
        const double el = samples[2 * i] - expected_left(t);
        const double er = samples[2 * i + 1] - (mono ? expected_left(t) : expected_right(t));
        d.max = std::max({d.max, std::fabs(el), std::fabs(er)});
        sum += el * el + er * er;
    }
    d.rms = std::sqrt(sum / (2.0 * static_cast<double>(to - from)));
    return d;
}

/// MP3 encoders turn the level down a little (LAME by about 3% at these bit rates), so a lossy file is
/// compared after fitting one gain: what is left is coding noise plus any error in timing. A shift of
/// one sample would leave an RMS of 0.02.
struct lossy_fit
{
    double gain = 0;
    double residual_rms = 0;
};

lossy_fit fit(std::span<const float> samples, std::uint32_t sample_rate, bool mono, std::size_t from, std::size_t to,
              std::size_t first_frame = 0)
{
    double xe = 0, ee = 0;
    for (std::size_t i = from; i < to; ++i)
    {
        const double t = static_cast<double>(first_frame + i) / sample_rate;
        const double el = expected_left(t), er = mono ? expected_left(t) : expected_right(t);
        xe += samples[2 * i] * el + samples[2 * i + 1] * er;
        ee += el * el + er * er;
    }
    lossy_fit f;
    f.gain = xe / ee;
    double sum = 0;
    for (std::size_t i = from; i < to; ++i)
    {
        const double t = static_cast<double>(first_frame + i) / sample_rate;
        const double dl = samples[2 * i] - f.gain * expected_left(t);
        const double dr = samples[2 * i + 1] - f.gain * (mono ? expected_left(t) : expected_right(t));
        sum += dl * dl + dr * dr;
    }
    f.residual_rms = std::sqrt(sum / (2.0 * static_cast<double>(to - from)));
    return f;
}

struct lossless_case
{
    const char* file;
    std::uint32_t sample_rate;
    std::uint16_t channels;
    std::uint16_t bits;
    const char* container;
    const char* encoding;
    std::uint64_t frames;
    double tolerance; ///< one quantisation step of the format (plus float rounding)
};

void test_lossless(const lossless_case& c)
{
    const auto clip = korre::load_audio(fixtures / c.file);
    CHECK_MSG(clip.has_value(), c.file);
    if (!clip)
    {
        return;
    }
    CHECK_MSG(clip->info.sample_rate == c.sample_rate, c.file);
    CHECK_MSG(clip->info.channels == c.channels, c.file);
    CHECK_MSG(clip->info.bits_per_sample == c.bits, c.file);
    CHECK_MSG(clip->info.container == c.container, c.file);
    CHECK_MSG(clip->info.encoding == c.encoding, c.file);
    CHECK_MSG(clip->frames() == c.frames, std::string(c.file) + ": " + std::to_string(clip->frames()) + " frames");
    CHECK_MSG(clip->warning.empty(), c.file);
    if (clip->frames() != c.frames)
    {
        return;
    }
    const auto d = compare(clip->samples, c.sample_rate, c.channels == 1, 0, clip->frames());
    CHECK_MSG(d.max <= c.tolerance, std::string(c.file) + ": largest error " + std::to_string(d.max));

    // Seeking: the stream continues exactly where a straight read would be.
    auto reader = korre::open_audio(fixtures / c.file);
    CHECK(reader.has_value());
    if (!reader)
    {
        return;
    }
    for (const std::uint64_t target : {c.frames / 2 + 17, std::uint64_t{3}, c.frames - 5, std::uint64_t{0}})
    {
        CHECK_MSG((*reader)->seek(target), c.file);
        std::vector<float> got(2 * 300);
        const std::size_t n = (*reader)->read(got);
        const auto want = static_cast<std::size_t>(std::min<std::uint64_t>(300, c.frames - target));
        CHECK_MSG(n == want, std::string(c.file) + ": read after seek");
        bool same = n == want;
        for (std::size_t i = 0; same && i < 2 * n; ++i)
        {
            same = got[i] == clip->samples[2 * target + i];
        }
        CHECK_MSG(same, std::string(c.file) + ": samples after seeking to " + std::to_string(target));
    }
    CHECK((*reader)->seek(c.frames + 1000)); // past the end is the end
    std::vector<float> none(64);
    CHECK((*reader)->read(none) == 0);

    // Reading in odd-sized pieces gives the same stream as one big read.
    CHECK((*reader)->seek(0));
    std::vector<float> pieces;
    std::vector<float> buf(2 * 777);
    for (std::size_t want = 1; const std::size_t n = (*reader)->read(std::span(buf).first(2 * want)); want = (want * 7 + 13) % 777 + 1)
    {
        pieces.insert(pieces.end(), buf.begin(), buf.begin() + static_cast<std::ptrdiff_t>(2 * n));
    }
    CHECK_MSG(pieces == clip->samples, std::string(c.file) + ": piecewise read");
}

void test_mp3(const char* file, bool mono, int bitrate)
{
    const auto clip = korre::load_audio(fixtures / file);
    CHECK_MSG(clip.has_value(), file);
    if (!clip)
    {
        return;
    }
    CHECK(clip->info.sample_rate == 44100);
    CHECK(clip->info.channels == (mono ? 1 : 2));
    CHECK(clip->info.container == "MP3");
    CHECK(clip->info.encoding == "Layer III");
    CHECK_MSG(clip->info.bitrate_kbps == bitrate, std::to_string(clip->info.bitrate_kbps));
    // Exactly one second: the encoder's padding at both ends is removed, so the stream is not
    // shifted either.
    CHECK_MSG(clip->frames() == 44100, std::string(file) + ": " + std::to_string(clip->frames()) + " frames");
    if (clip->frames() != 44100)
    {
        return;
    }
    const auto f = fit(clip->samples, 44100, mono, 4410, 39690);
    CHECK_MSG(f.gain > 0.93 && f.gain < 1.0, std::string(file) + ": gain " + std::to_string(f.gain));
    CHECK_MSG(f.residual_rms < 0.001, std::string(file) + ": residual " + std::to_string(f.residual_rms));

    auto reader = korre::open_audio(fixtures / file);
    CHECK(reader.has_value());
    if (!reader)
    {
        return;
    }
    CHECK((*reader)->seek(20000));
    std::vector<float> got(2 * 4000);
    CHECK((*reader)->read(got) == 4000);
    const auto fs = fit(got, 44100, mono, 0, 4000, 20000);
    CHECK_MSG(std::fabs(fs.gain - f.gain) < 0.002, std::string(file) + ": gain after seek " + std::to_string(fs.gain));
    CHECK_MSG(fs.residual_rms < 0.001, std::string(file) + ": residual after seek " + std::to_string(fs.residual_rms));
}

void test_rejects()
{
    const auto missing = korre::open_audio(fixtures / "no_such_file.wav");
    CHECK(!missing.has_value());
    const auto text = korre::open_audio(fixtures / "not_audio.wav");
    CHECK(!text.has_value());
    const auto stub = korre::open_audio(fixtures / "header_only.wav");
    CHECK(!stub.has_value());

    // A file cut off in the middle plays as far as it goes.
    const auto cut = korre::load_audio(fixtures / "cut_short.wav");
    CHECK(cut.has_value());
    if (cut)
    {
        CHECK(cut->frames() > 400 && cut->frames() < 500);
        const auto d = compare(cut->samples, 44100, false, 0, cut->frames());
        CHECK(d.max <= 1.0 / 32768);
    }
}

void test_writers()
{
    const auto dir = std::filesystem::temp_directory_path() / "korre_test_audio";
    std::filesystem::create_directories(dir);

    const std::uint32_t sr = 48000;
    std::vector<float> signal(2 * 5001); // odd length: the WAV writer has to pad
    for (std::size_t i = 0; i < signal.size() / 2; ++i)
    {
        const double t = static_cast<double>(i) / sr;
        signal[2 * i] = static_cast<float>(expected_left(t));
        signal[2 * i + 1] = static_cast<float>(expected_right(t));
    }
    signal[10] = 1.5f; // over full scale: integer formats must clip, not wrap around
    signal[11] = -1.5f;

    struct format_case
    {
        const char* name;
        korre::sample_format format;
        bool flac;
        double step;
    };
    for (const format_case& c : {format_case{"w16.wav", korre::sample_format::pcm16, false, 1.0 / 32768},
                                 format_case{"w24.wav", korre::sample_format::pcm24, false, 1.0 / 8388608},
                                 format_case{"w32f.wav", korre::sample_format::float32, false, 0.0},
                                 format_case{"f16.flac", korre::sample_format::pcm16, true, 1.0 / 32768},
                                 format_case{"f24.flac", korre::sample_format::pcm24, true, 1.0 / 8388608}})
    {
        const auto path = dir / c.name;
        const auto saved = c.flac ? korre::save_flac(path, signal, sr, c.format) : korre::save_wav(path, signal, sr, c.format);
        CHECK_MSG(saved.has_value(), c.name);
        const auto back = korre::load_audio(path);
        CHECK_MSG(back.has_value(), c.name);
        if (!back)
        {
            continue;
        }
        CHECK_MSG(back->info.sample_rate == sr && back->frames() == signal.size() / 2, c.name);
        double worst = 0;
        for (std::size_t i = 0; i < signal.size() && i < back->samples.size(); ++i)
        {
            const bool integer = c.step > 0;
            const double want = integer ? std::clamp(static_cast<double>(signal[i]), -1.0, 1.0 - c.step) : signal[i];
            worst = std::max(worst, std::fabs(back->samples[i] - want));
        }
        CHECK_MSG(worst <= c.step * 0.5 + 1e-9, std::string(c.name) + ": largest error " + std::to_string(worst));
    }
    CHECK(!korre::save_flac(dir / "x.flac", signal, sr, korre::sample_format::float32).has_value());
    CHECK(!korre::save_wav(dir / "no_such_dir" / "x.wav", signal, sr).has_value());

    std::filesystem::remove_all(dir);
}

} // namespace

int main()
{
    const double q16 = 1.0 / 32768, q24 = 1.0 / 8388608;
    for (const lossless_case& c : {
             lossless_case{"tone_s16.wav", 44100, 2, 16, "WAV", "PCM", 8820, q16},
             lossless_case{"tone_s24.wav", 44100, 2, 24, "WAV", "PCM", 8820, q24 * 1.5},
             lossless_case{"tone_s32_96k.wav", 96000, 2, 32, "WAV", "PCM", 4800, 1e-7},
             lossless_case{"tone_f32_48k.wav", 48000, 2, 32, "WAV", "float", 4800, 1e-7},
             lossless_case{"tone_u8_mono.wav", 44100, 1, 8, "WAV", "PCM", 8820, 1.0 / 128},
             lossless_case{"tone_s16_mono.wav", 44100, 1, 16, "WAV", "PCM", 8820, q16},
             lossless_case{"tone_s16.flac", 44100, 2, 16, "FLAC", "PCM", 22050, q16},
             lossless_case{"tone_s24_96k.flac", 96000, 2, 24, "FLAC", "PCM", 24000, q24 * 1.5},
             lossless_case{"tone_s16_mono.flac", 44100, 1, 16, "FLAC", "PCM", 22050, q16},
         })
    {
        test_lossless(c);
    }
    test_mp3("tone.mp3", false, 192);
    test_mp3("tone_mono.mp3", true, 96);
    test_rejects();
    test_writers();
    return check::result();
}
