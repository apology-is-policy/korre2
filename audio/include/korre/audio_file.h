#pragma once

// Reading and writing audio files. No user interface and no audio device in here.
//
// A reader decodes a file piece by piece, so a track starts playing at once and a long file never
// has to fit in memory. Whatever the file holds, a reader hands out stereo, interleaved, 32-bit
// float samples at full scale +-1 (a mono file is played on both sides).

#include <cstddef>
#include <cstdint>
#include <expected>
#include <filesystem>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace korre
{

/// What a file says about itself.
struct audio_info
{
    std::uint32_t sample_rate = 0;
    std::uint16_t channels = 0;        ///< channels stored in the file: 1 or 2
    std::uint16_t bits_per_sample = 0; ///< word length as stored; 0 where there is none (MP3)
    std::string container;             ///< "WAV", "FLAC", "MP3"
    std::string encoding;              ///< "PCM", "float", "Layer III"
    int bitrate_kbps = 0;              ///< MP3 only
    std::uint64_t frames = 0;          ///< length in sample frames; 0 if the file does not say
};

class audio_reader
{
public:
    virtual ~audio_reader() = default;

    virtual const audio_info& info() const noexcept = 0;

    /// Decodes up to out.size() / 2 frames into `out` (L R L R ...). Returns the number of frames
    /// written; 0 means the end of the file.
    virtual std::size_t read(std::span<float> out) = 0;

    /// Continues from the given frame, counted from the start of the file. A position past the end
    /// is the end. Returns false if the file cannot be repositioned (the reader then stays usable).
    virtual bool seek(std::uint64_t frame) = 0;

    /// Trouble met while decoding that did not stop it, such as damaged frames. Empty if none.
    virtual std::string_view warning() const noexcept { return {}; }
};

/// Opens a WAV, FLAC or MP3 file; the type is taken from the content, not from the file name.
/// On failure the string says what is wrong with the file.
std::expected<std::unique_ptr<audio_reader>, std::string> open_audio(const std::filesystem::path& path);

/// A whole file in memory.
struct audio_clip
{
    audio_info info;
    std::vector<float> samples; ///< interleaved stereo
    std::string warning;

    std::size_t frames() const noexcept { return samples.size() / 2; }
};

std::expected<audio_clip, std::string> load_audio(const std::filesystem::path& path);

enum class sample_format { pcm16, pcm24, float32 };

/// Writes interleaved stereo samples. Integer formats are rounded and clipped at full scale, without
/// dither. FLAC takes pcm16 or pcm24.
std::expected<void, std::string> save_wav(const std::filesystem::path& path, std::span<const float> samples,
                                          std::uint32_t sample_rate, sample_format format = sample_format::pcm24);
std::expected<void, std::string> save_flac(const std::filesystem::path& path, std::span<const float> samples,
                                           std::uint32_t sample_rate, sample_format format = sample_format::pcm24);

} // namespace korre
