#include "korre/audio_file.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <fstream>

#include "readers.h"

namespace korre
{

std::expected<std::unique_ptr<audio_reader>, std::string> open_audio(const std::filesystem::path& path)
{
    std::array<char, 12> head{};
    {
        std::ifstream f(path, std::ios::binary);
        if (!f)
        {
            return std::unexpected("cannot open " + path.string());
        }
        f.read(head.data(), static_cast<std::streamsize>(head.size()));
        if (f.gcount() < 4)
        {
            return std::unexpected(path.filename().string() + ": too short to be an audio file");
        }
    }

    const auto starts_with = [&](const char* magic) { return std::memcmp(head.data(), magic, std::strlen(magic)) == 0; };

    if (starts_with("RIFF") || starts_with("RF64"))
    {
        return detail::open_wav(path);
    }
    if (starts_with("fLaC"))
    {
        return detail::open_flac(path);
    }

    // An ID3 tag can sit in front of either a FLAC or an MP3 stream, and a bare MP3 has no signature
    // at all, so the name decides between those two.
    auto ext = path.extension().string();
    for (auto& c : ext)
    {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    if (ext == ".flac")
    {
        return detail::open_flac(path);
    }
    const bool frame_sync = static_cast<unsigned char>(head[0]) == 0xFF && (static_cast<unsigned char>(head[1]) & 0xE0) == 0xE0;
    if (ext == ".mp3" || starts_with("ID3") || frame_sync)
    {
        return detail::open_mp3(path);
    }
    return std::unexpected(path.filename().string() + ": not a WAV, FLAC or MP3 file");
}

std::expected<audio_clip, std::string> load_audio(const std::filesystem::path& path)
{
    auto reader = open_audio(path);
    if (!reader)
    {
        return std::unexpected(reader.error());
    }

    audio_clip clip;
    clip.info = (*reader)->info();
    clip.samples.reserve(static_cast<std::size_t>(clip.info.frames) * 2);

    std::vector<float> block(2 * 16384);
    while (const std::size_t got = (*reader)->read(block))
    {
        clip.samples.insert(clip.samples.end(), block.begin(), block.begin() + static_cast<std::ptrdiff_t>(got * 2));
    }
    clip.info.frames = clip.frames(); // what was really there
    clip.warning = (*reader)->warning();
    return clip;
}

std::expected<float, std::string> measure_peak(const std::filesystem::path& path)
{
    auto reader = open_audio(path);
    if (!reader)
    {
        return std::unexpected(reader.error());
    }
    float peak = 0.0f;
    std::vector<float> block(2 * 16384);
    while (const std::size_t got = (*reader)->read(block))
    {
        for (std::size_t i = 0; i < 2 * got; ++i)
        {
            peak = std::max(peak, std::fabs(block[i]));
        }
    }
    return peak;
}

} // namespace korre
