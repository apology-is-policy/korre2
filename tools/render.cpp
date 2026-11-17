// korre-render: plays an audio file through a tape profile and writes the result, offline.
//
//   korre-render in.flac out.flac --profile profiles/wmd6c_xlii_sideB.json
//
// The output has the length of the input and is in time with it (the engine's delay is taken out).

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "korre/audio_file.h"
#include "tape/engine.h"

namespace
{

const char* const usage = R"(usage: korre-render <input> <output> --profile <profile.json> [options]

  <input>             WAV, FLAC or MP3
  <output>            .flac or .wav

  --profile FILE      the tape profile to apply (profiles/*.json)
  --seed N            seed of the random wobble, jitter, flicker and noise (default 1)
  --ingredients LIST  parts of the model to apply, comma separated:
                        eq transport differential jitter flicker dropouts hiss saturation
                      or "all" (default) or "none"
  --record-gain L,R   how hard the tape is driven, dB per channel (default: as the profile was fitted)
  --output-gain DB    gain at the end (default 0: the level of a real capture)
  --polarity N        1 or -1 (default: the profile's)
  --bits N            16, 24 (default) or float (WAV only)
  --trace DIR         also write the engine's control signals and filters to DIR as raw 64-bit
                      floats, for analysis/verify_engine.py
)";

[[noreturn]] void fail(const std::string& message)
{
    std::fprintf(stderr, "korre-render: %s\n", message.c_str());
    std::exit(1);
}

std::optional<double> to_number(std::string_view text)
{
    const std::string copy(text);
    char* end = nullptr;
    const double v = std::strtod(copy.c_str(), &end);
    if (copy.empty() || end != copy.c_str() + copy.size())
    {
        return std::nullopt;
    }
    return v;
}

std::uint32_t parse_ingredients(std::string_view list)
{
    if (list == "all")
    {
        return tape::all_ingredients;
    }
    if (list == "none")
    {
        return 0;
    }
    static const std::pair<std::string_view, tape::ingredient> names[] = {
        {"eq", tape::ingredient::eq},           {"transport", tape::ingredient::transport},
        {"differential", tape::ingredient::differential}, {"jitter", tape::ingredient::jitter},
        {"flicker", tape::ingredient::flicker}, {"dropouts", tape::ingredient::dropouts},
        {"hiss", tape::ingredient::hiss},       {"saturation", tape::ingredient::saturation},
    };
    std::uint32_t mask = 0;
    while (!list.empty())
    {
        const std::size_t comma = list.find(',');
        const std::string_view word = list.substr(0, comma);
        list = comma == std::string_view::npos ? std::string_view{} : list.substr(comma + 1);
        bool known = false;
        for (const auto& [name, bit] : names)
        {
            if (word == name)
            {
                mask = mask | bit;
                known = true;
            }
        }
        if (!known)
        {
            fail("unknown ingredient \"" + std::string(word) + "\"");
        }
    }
    return mask;
}

void write_raw(const std::filesystem::path& path, const std::vector<double>& values, std::size_t skip, std::size_t count)
{
    std::ofstream f(path, std::ios::binary | std::ios::trunc);
    if (skip < values.size())
    {
        const std::size_t n = std::min(count, values.size() - skip);
        f.write(reinterpret_cast<const char*>(values.data() + skip), static_cast<std::streamsize>(n * sizeof(double)));
    }
    if (!f)
    {
        fail("cannot write " + path.string());
    }
}

} // namespace

int main(int argc, char** argv)
{
    std::vector<std::string_view> positional;
    std::string profile_path, trace_dir;
    tape::settings settings;
    korre::sample_format format = korre::sample_format::pcm24;

    for (int i = 1; i < argc; ++i)
    {
        const std::string_view arg = argv[i];
        const auto value = [&]() -> std::string_view {
            if (i + 1 >= argc)
            {
                fail("missing value after " + std::string(arg));
            }
            return argv[++i];
        };
        const auto number = [&]() {
            const std::string_view text = value();
            const auto v = to_number(text);
            if (!v)
            {
                fail("not a number: " + std::string(text));
            }
            return *v;
        };

        if (arg == "-h" || arg == "--help")
        {
            std::fputs(usage, stdout);
            return 0;
        }
        else if (arg == "--profile")
        {
            profile_path = value();
        }
        else if (arg == "--seed")
        {
            settings.seed = static_cast<std::uint64_t>(number());
        }
        else if (arg == "--ingredients")
        {
            settings.ingredients = parse_ingredients(value());
        }
        else if (arg == "--record-gain")
        {
            const std::string_view text = value();
            const std::size_t comma = text.find(',');
            const auto l = to_number(text.substr(0, comma));
            const auto r = comma == std::string_view::npos ? l : to_number(text.substr(comma + 1));
            if (!l || !r)
            {
                fail("--record-gain takes one number or L,R");
            }
            settings.record_gain_db = tape::stereo{*l, *r};
        }
        else if (arg == "--output-gain")
        {
            settings.output_gain_db = number();
        }
        else if (arg == "--polarity")
        {
            const double v = number();
            if (v != 1 && v != -1)
            {
                fail("--polarity takes 1 or -1");
            }
            settings.polarity = static_cast<int>(v);
        }
        else if (arg == "--bits")
        {
            const std::string_view text = value();
            if (text == "16")
            {
                format = korre::sample_format::pcm16;
            }
            else if (text == "24")
            {
                format = korre::sample_format::pcm24;
            }
            else if (text == "float")
            {
                format = korre::sample_format::float32;
            }
            else
            {
                fail("--bits takes 16, 24 or float");
            }
        }
        else if (arg == "--trace")
        {
            trace_dir = value();
        }
        else if (arg.starts_with("--"))
        {
            fail("unknown option " + std::string(arg) + "\n\n" + usage);
        }
        else
        {
            positional.push_back(arg);
        }
    }
    if (positional.size() != 2 || profile_path.empty())
    {
        std::fputs(usage, stderr);
        return 2;
    }
    const std::filesystem::path input(positional[0]), output(positional[1]);
    const bool flac = output.extension() == ".flac";
    if (!flac && output.extension() != ".wav")
    {
        fail("the output must be a .flac or a .wav file");
    }

    const auto profile = tape::load_profile(profile_path);
    if (!profile)
    {
        fail(profile.error());
    }
    auto clip = korre::load_audio(input);
    if (!clip)
    {
        fail(clip.error());
    }
    if (!clip->warning.empty())
    {
        std::fprintf(stderr, "korre-render: %s: %s\n", input.filename().c_str(), clip->warning.c_str());
    }

    settings.sample_rate = clip->info.sample_rate;
    tape::engine engine(*profile, settings);
    const tape::latency lag = engine.delay();
    const std::size_t frames = clip->frames();

    // Run the track and then enough silence to push its end through the engine; drop the engine's
    // delay from the front, so the output lines up with the input.
    std::vector<float> in = std::move(clip->samples);
    in.resize((frames + lag.total) * 2, 0.0f);
    std::vector<float> out(in.size());
    tape::trace trace;
    if (trace_dir.empty())
    {
        engine.process(in, out);
    }
    else
    {
        engine.process(in, out, trace);
    }
    const std::span<const float> aligned(out.data() + lag.total * 2, frames * 2);

    const auto saved = flac ? korre::save_flac(output, aligned, clip->info.sample_rate, format)
                            : korre::save_wav(output, aligned, clip->info.sample_rate, format);
    if (!saved)
    {
        fail(saved.error());
    }

    if (!trace_dir.empty())
    {
        const std::filesystem::path dir(trace_dir);
        std::filesystem::create_directories(dir);
        // The timing signals act one stage before the others, so they are `lag.flicker` frames
        // earlier in the engine's own time. Written here, every signal is indexed by output frame.
        const std::size_t timing = lag.total - lag.flicker;
        write_raw(dir / "transport.f64", trace.transport, timing, frames);
        write_raw(dir / "differential.f64", trace.differential, timing, frames);
        write_raw(dir / "jitter_common.f64", trace.jitter_common, timing, frames);
        write_raw(dir / "jitter_left.f64", trace.jitter_own[0], timing, frames);
        write_raw(dir / "jitter_right.f64", trace.jitter_own[1], timing, frames);
        write_raw(dir / "flicker_common.f64", trace.flicker_common, lag.total, frames);
        write_raw(dir / "flicker_left.f64", trace.flicker_own[0], lag.total, frames);
        write_raw(dir / "flicker_right.f64", trace.flicker_own[1], lag.total, frames);
        write_raw(dir / "dropout_left.f64", trace.dropout_gain[0], lag.total, frames);
        write_raw(dir / "dropout_right.f64", trace.dropout_gain[1], lag.total, frames);
        write_raw(dir / "background_left.f64", trace.background[0], lag.total, frames);
        write_raw(dir / "background_right.f64", trace.background[1], lag.total, frames);
        write_raw(dir / "response_left.f64", trace.response_filter[0], 0, trace.response_filter[0].size());
        write_raw(dir / "response_right.f64", trace.response_filter[1], 0, trace.response_filter[1].size());
        write_raw(dir / "flicker_filter_common.f64", trace.flicker_filter_common, 0, trace.flicker_filter_common.size());
        write_raw(dir / "flicker_filter_own.f64", trace.flicker_filter_own, 0, trace.flicker_filter_own.size());

        std::ofstream info(dir / "info.json");
        info << "{\"sample_rate\": " << clip->info.sample_rate << ", \"frames\": " << frames << ", \"seed\": " << settings.seed
             << ", \"delay\": {\"response\": " << lag.response << ", \"timing\": " << lag.timing << ", \"flicker\": " << lag.flicker
             << ", \"total\": " << lag.total << "}, \"response_pre\": " << trace.response_pre << "}\n";
    }

    std::printf("%s: %zu frames at %u Hz through \"%s\" -> %s (engine delay %zu frames, removed)\n", input.filename().c_str(), frames,
                clip->info.sample_rate, profile->name.c_str(), output.filename().c_str(), lag.total);
    return 0;
}
