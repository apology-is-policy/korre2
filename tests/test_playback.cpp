// The playback core, without a sound card: manual_output plays the part of the audio device and the
// test pulls the audio the way a callback would.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <thread>
#include <vector>

#include "check.h"
#include "korre/audio_file.h"
#include "korre/audio_output.h"
#include "korre/playback.h"

namespace
{

using namespace korre;
using namespace std::chrono_literals;

const std::filesystem::path fixtures = KORRE_FIXTURES;
const std::filesystem::path profiles = KORRE_PROFILES;

/// Plays the sound card: pulls until `frames` frames of real audio have come out (the player hands
/// out silence while its decoder has nothing ready), the track ends, or two seconds pass.
std::vector<float> collect(playback& p, manual_output& out, std::size_t frames)
{
    std::vector<float> got;
    const auto deadline = std::chrono::steady_clock::now() + 2s;
    while (got.size() < 2 * frames && std::chrono::steady_clock::now() < deadline)
    {
        const std::size_t want = std::min<std::size_t>(256, frames - got.size() / 2);
        const std::uint64_t before = p.position();
        const auto block = out.pull(want);
        const auto real = static_cast<std::size_t>(p.position() - before); // real audio comes first in a block
        got.insert(got.end(), block.begin(), block.begin() + static_cast<std::ptrdiff_t>(2 * real));
        if (real == 0)
        {
            if (!p.playing())
            {
                break;
            }
            std::this_thread::sleep_for(1ms);
        }
    }
    return got;
}

bool same(std::span<const float> a, std::span<const float> b) { return a.size() == b.size() && std::equal(a.begin(), a.end(), b.begin()); }

bool silent(std::span<const float> a)
{
    return std::all_of(a.begin(), a.end(), [](float v) { return v == 0.0f; });
}

void test_plain()
{
    const auto clip = load_audio(fixtures / "tone_s16.flac");
    CHECK(clip.has_value());
    if (!clip)
    {
        return;
    }
    const std::span<const float> all(clip->samples);
    const std::size_t frames = clip->frames();

    manual_output out;
    playback p(out);

    // ---- nothing loaded
    CHECK(!p.has_track() && !p.playing() && p.position() == 0);
    CHECK(!p.play().has_value());
    CHECK(silent(out.pull(100)));
    CHECK(!p.load(fixtures / "not_audio.wav").has_value());
    CHECK(!p.has_track());

    // ---- loaded: paused at the start, the output not yet opened
    CHECK(p.load(fixtures / "tone_s16.flac").has_value());
    CHECK(p.has_track() && !p.playing() && p.position() == 0);
    CHECK(p.info().sample_rate == 44100 && p.info().frames == frames && p.info().container == "FLAC");
    CHECK(!out.is_open());

    // ---- played through: sample for sample the file, then finished exactly once
    CHECK(p.play().has_value());
    CHECK(out.is_open() && out.sample_rate() == 44100 && p.playing());
    const auto whole = collect(p, out, frames + 1000);
    CHECK_MSG(same(whole, all), "the whole track, sample for sample (" + std::to_string(whole.size() / 2) + " frames)");
    CHECK(p.position() == frames);
    CHECK(!p.playing());
    CHECK(p.take_finished());
    CHECK(!p.take_finished());
    CHECK(silent(out.pull(300)));

    // ---- levels and the tap for the spectrum display
    const auto levels = p.take_levels();
    CHECK_NEAR(levels.peak[0], 0.5, 0.001);
    CHECK_NEAR(levels.peak[1], 0.25, 0.001);
    CHECK(levels.clipped == 0); // (underruns are expected here: this "sound card" pulls faster than real time)
    std::vector<float> mono(4000);
    CHECK(p.read_played(mono) == 4000);
    bool tap_ok = true;
    for (std::size_t i = 0; i < 4000; ++i)
    {
        tap_ok = tap_ok && mono[i] == 0.5f * (all[2 * i] + all[2 * i + 1]);
    }
    CHECK_MSG(tap_ok, "the played samples, mixed to mono");

    // ---- play again starts over
    CHECK(p.play().has_value());
    CHECK(same(collect(p, out, 1000), all.first(2000)));

    // ---- seek: the position is right at once, the audio continues from there
    p.seek(10000);
    CHECK(p.position() == 10000);
    CHECK(same(collect(p, out, 2000), all.subspan(2 * 10000, 4000)));
    CHECK(p.position() == 12000);

    // ---- pause holds, resume loses nothing and repeats nothing
    p.pause();
    CHECK(!p.playing());
    CHECK(silent(out.pull(700)));
    CHECK(p.position() == 12000);
    p.seek(300); // a seek while paused
    CHECK(p.position() == 300);
    CHECK(silent(out.pull(700)));
    CHECK(p.play().has_value());
    CHECK(same(collect(p, out, 1500), all.subspan(2 * 300, 3000)));
    p.pause();
    CHECK(p.play().has_value());
    CHECK(same(collect(p, out, 500), all.subspan(2 * 1800, 1000)));

    // ---- a seek past the end is the end
    p.seek(frames + 5000);
    CHECK(collect(p, out, 100).empty());
    CHECK(p.take_finished() && p.position() == frames);

    // ---- another file at another sample rate: the output follows
    const auto hires = load_audio(fixtures / "tone_s24_96k.flac");
    CHECK(hires.has_value());
    CHECK(p.load(fixtures / "tone_s24_96k.flac").has_value());
    CHECK(!p.playing() && p.position() == 0);
    CHECK(p.play().has_value());
    CHECK(out.sample_rate() == 96000);
    if (hires)
    {
        CHECK(same(collect(p, out, 5000), std::span<const float>(hires->samples).first(10000)));
    }

    // ---- MP3 and mono WAV take the same path
    for (const char* name : {"tone.mp3", "tone_s16_mono.wav"})
    {
        const auto want = load_audio(fixtures / name);
        CHECK(p.load(fixtures / name).has_value());
        CHECK(p.play().has_value());
        if (want)
        {
            CHECK_MSG(same(collect(p, out, want->frames() + 10), want->samples), name);
        }
    }

    // ---- unload
    p.unload();
    CHECK(!p.has_track() && !p.playing() && !out.is_open());
    CHECK(silent(out.pull(100)));
}

void test_clipping()
{
    // A file that goes over full scale: the output is held at full scale and the overs are counted.
    const auto path = std::filesystem::temp_directory_path() / "korre_test_loud.wav";
    std::vector<float> loud(2 * 2000);
    for (std::size_t i = 0; i < 2000; ++i)
    {
        loud[2 * i] = 1.5f * static_cast<float>(std::sin(0.05 * static_cast<double>(i)));
        loud[2 * i + 1] = 0.5f;
    }
    CHECK(save_wav(path, loud, 44100, sample_format::float32).has_value());

    manual_output out;
    playback p(out);
    CHECK(p.load(path).has_value());
    CHECK(p.play().has_value());
    const auto got = collect(p, out, 2000);
    CHECK(got.size() == loud.size());
    bool held = true;
    for (std::size_t i = 0; i < got.size(); ++i)
    {
        held = held && got[i] == std::clamp(loud[i], -1.0f, 1.0f);
    }
    CHECK_MSG(held, "samples over full scale are held at full scale");
    const auto levels = p.take_levels();
    CHECK(levels.clipped > 100);
    CHECK_NEAR(levels.peak[0], 1.5, 0.01);
    std::filesystem::remove(path);
}

void test_tape()
{
    const auto clip = load_audio(fixtures / "tone_s16.flac");
    CHECK(clip.has_value());
    if (!clip)
    {
        return;
    }
    const std::span<const float> all(clip->samples);
    const std::size_t frames = clip->frames();
    const float headroom = static_cast<float>(std::pow(10.0, -6.0 / 20.0));

    manual_output out;
    playback p(out);
    CHECK(!p.set_profile(profiles / "no_such_profile.json").has_value());
    CHECK(!p.has_profile());
    CHECK(p.set_profile(profiles / "wmd6c_xlii_sideB.json").has_value());
    CHECK(p.has_profile() && p.profile_name() == "wmd6c_xlii_sideB");
    CHECK_NEAR(p.headroom_db(), 6.0, 0);

    // ---- bypassed: the file itself, in time (the engine's delay is taken out), lowered by the headroom
    p.set_bypass(true);
    CHECK(p.load(fixtures / "tone_s16.flac").has_value());
    CHECK(p.play().has_value());
    const auto dry = collect(p, out, frames + 1000);
    CHECK_MSG(dry.size() == all.size(), "bypassed: the whole length (" + std::to_string(dry.size() / 2) + " frames)");
    bool exact = dry.size() == all.size();
    for (std::size_t i = 0; exact && i < dry.size(); ++i)
    {
        exact = dry[i] == all[i] * headroom;
    }
    CHECK_MSG(exact, "bypassed: the file sample for sample, 6 dB down");
    CHECK(p.take_finished());

    // ---- through the tape: the same length and position, a different but sane signal
    p.set_bypass(false);
    CHECK(p.play().has_value());
    const auto wet = collect(p, out, frames + 1000);
    CHECK_MSG(wet.size() == all.size(), "through the tape: the whole length (" + std::to_string(wet.size() / 2) + " frames)");
    CHECK(p.position() == frames && p.take_finished());
    if (wet.size() == all.size())
    {
        double sum_wet = 0, sum_dry = 0, sum_diff = 0;
        bool finite = true;
        for (std::size_t i = 2 * 4000; i < wet.size(); ++i)
        {
            finite = finite && std::isfinite(wet[i]);
            sum_wet += static_cast<double>(wet[i]) * wet[i];
            sum_dry += static_cast<double>(dry[i]) * dry[i];
            sum_diff += static_cast<double>(wet[i] - dry[i]) * (wet[i] - dry[i]);
        }
        CHECK(finite);
        // The make-up gain brings the tape back to the level of the file ...
        CHECK_MSG(std::fabs(10 * std::log10(sum_wet / sum_dry)) < 1.5, "level through the tape: " + std::to_string(10 * std::log10(sum_wet / sum_dry)) + " dB");
        // ... but it is not the file: this profile turns the waveform upside down, for one.
        CHECK(sum_diff > sum_dry);
    }

    // ---- seek with the engine in the path: the position is the file's
    p.set_bypass(true);
    CHECK(p.play().has_value());
    collect(p, out, 3000); // the switch to bypass has faded in
    p.seek(7000);
    const auto after = collect(p, out, 2000);
    bool ok = after.size() == 4000;
    for (std::size_t i = 0; ok && i < after.size(); ++i)
    {
        ok = after[i] == all[2 * 7000 + i] * headroom;
    }
    CHECK_MSG(ok, "after a seek through the engine: the right place in the file");

    // ---- taking the profile away mid-track: plain playback from where it was
    p.clear_profile();
    CHECK(!p.has_profile());
    const std::uint64_t here = p.position();
    CHECK(here == 9000);
    CHECK(same(collect(p, out, 1000), all.subspan(2 * 9000, 2000)));
}

void test_threads()
{
    // A real second thread plays the sound card while this one does everything a user can do, fast.
    // Nothing is checked but survival: the point is to run it under the thread sanitizer.
    manual_output out;
    playback p(out);
    std::atomic<bool> stop{false};
    std::atomic<std::uint64_t> pulled{0};
    std::thread card([&] {
        while (!stop.load())
        {
            out.pull(256);
            pulled.fetch_add(256);
            std::this_thread::sleep_for(200us);
        }
    });

    const std::filesystem::path files[] = {fixtures / "tone_s16.flac", fixtures / "tone_s24_96k.flac", fixtures / "tone.mp3",
                                           fixtures / "tone_s16_mono.wav"};
    std::uint64_t r = 12345;
    const auto next = [&r] {
        r = r * 6364136223846793005ull + 1442695040888963407ull;
        return static_cast<std::uint32_t>(r >> 33);
    };
    bool ok = true;
    for (int i = 0; i < 400; ++i)
    {
        switch (next() % 12)
        {
        case 0:
            ok = ok && p.load(files[next() % 4]).has_value();
            break;
        case 1:
        case 2:
            if (p.has_track())
            {
                ok = ok && p.play().has_value();
            }
            break;
        case 3:
            p.pause();
            break;
        case 4:
        case 5:
        case 6:
            p.seek(next() % 30000);
            break;
        case 7:
            p.set_bypass(next() % 2 == 0);
            break;
        case 8:
            p.set_ingredients(next() & 0xFF);
            break;
        case 9:
            if (next() % 3 == 0)
            {
                ok = ok && p.set_profile(profiles / "wmd6c_xlii_sideB.json").has_value();
            }
            else if (next() % 3 == 0)
            {
                p.clear_profile();
            }
            break;
        case 10:
            p.take_levels();
            p.take_finished();
            (void)p.position();
            break;
        default:
        {
            float mono[512];
            p.read_played(mono);
            break;
        }
        }
        std::this_thread::sleep_for(300us);
    }
    CHECK(ok);
    stop.store(true);
    card.join();
    CHECK(pulled.load() > 0);
}

} // namespace

int main()
{
    test_plain();
    test_clipping();
    test_tape();
    test_threads();
    return check::result();
}
