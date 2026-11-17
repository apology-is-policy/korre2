#include <algorithm>
#include <cmath>
#include <fstream>

#include <FLAC/stream_encoder.h>

#include "korre/audio_file.h"

namespace korre
{
namespace
{

/// Rounds to an integer of the given word length, clipping at full scale.
std::int32_t quantise(float v, int bits)
{
    const double full = static_cast<double>(1u << (bits - 1));
    const double scaled = std::nearbyint(static_cast<double>(v) * full);
    return static_cast<std::int32_t>(std::clamp(scaled, -full, full - 1.0));
}

void put16(std::vector<unsigned char>& b, std::uint32_t v)
{
    b.push_back(static_cast<unsigned char>(v));
    b.push_back(static_cast<unsigned char>(v >> 8));
}

void put32(std::vector<unsigned char>& b, std::uint32_t v)
{
    put16(b, v);
    put16(b, v >> 16);
}

void put_tag(std::vector<unsigned char>& b, const char* tag) { b.insert(b.end(), tag, tag + 4); }

} // namespace

std::expected<void, std::string> save_wav(const std::filesystem::path& path, std::span<const float> samples,
                                          std::uint32_t sample_rate, sample_format format)
{
    const std::uint32_t bytes_per_sample = format == sample_format::pcm16 ? 2 : format == sample_format::pcm24 ? 3 : 4;
    const std::uint64_t data_bytes = static_cast<std::uint64_t>(samples.size()) * bytes_per_sample;
    if (data_bytes > 0xFFFFFFFFu - 44)
    {
        return std::unexpected("too long for a WAV file (4 GB limit): write FLAC instead");
    }
    const std::uint32_t block_align = 2 * bytes_per_sample;

    std::vector<unsigned char> out;
    out.reserve(static_cast<std::size_t>(data_bytes) + 44);
    put_tag(out, "RIFF");
    put32(out, static_cast<std::uint32_t>(36 + data_bytes + (data_bytes & 1u)));
    put_tag(out, "WAVE");
    put_tag(out, "fmt ");
    put32(out, 16);
    put16(out, format == sample_format::float32 ? 3 : 1);
    put16(out, 2);
    put32(out, sample_rate);
    put32(out, sample_rate * block_align);
    put16(out, block_align);
    put16(out, bytes_per_sample * 8);
    put_tag(out, "data");
    put32(out, static_cast<std::uint32_t>(data_bytes));

    for (const float v : samples)
    {
        if (format == sample_format::float32)
        {
            unsigned char raw[4];
            std::memcpy(raw, &v, 4);
            out.insert(out.end(), raw, raw + 4);
            continue;
        }
        const auto q = static_cast<std::uint32_t>(quantise(v, static_cast<int>(bytes_per_sample * 8)));
        for (std::uint32_t k = 0; k < bytes_per_sample; ++k)
        {
            out.push_back(static_cast<unsigned char>(q >> (8 * k)));
        }
    }
    if (data_bytes & 1u)
    {
        out.push_back(0);
    }

    std::ofstream f(path, std::ios::binary | std::ios::trunc);
    f.write(reinterpret_cast<const char*>(out.data()), static_cast<std::streamsize>(out.size()));
    f.close();
    if (!f)
    {
        return std::unexpected("cannot write " + path.string());
    }
    return {};
}

std::expected<void, std::string> save_flac(const std::filesystem::path& path, std::span<const float> samples,
                                           std::uint32_t sample_rate, sample_format format)
{
    if (format == sample_format::float32)
    {
        return std::unexpected("FLAC holds integer samples: choose 16 or 24 bits");
    }
    const int bits = format == sample_format::pcm16 ? 16 : 24;
    const std::size_t frames = samples.size() / 2;

    FLAC__StreamEncoder* encoder = FLAC__stream_encoder_new();
    if (!encoder)
    {
        return std::unexpected("out of memory");
    }
    FLAC__stream_encoder_set_channels(encoder, 2);
    FLAC__stream_encoder_set_bits_per_sample(encoder, static_cast<unsigned>(bits));
    FLAC__stream_encoder_set_sample_rate(encoder, sample_rate);
    FLAC__stream_encoder_set_compression_level(encoder, 5);
    FLAC__stream_encoder_set_total_samples_estimate(encoder, frames);

    std::string error;
    const auto status = FLAC__stream_encoder_init_file(encoder, path.c_str(), nullptr, nullptr);
    if (status != FLAC__STREAM_ENCODER_INIT_STATUS_OK)
    {
        error = std::string("cannot write ") + path.string() + " (" + FLAC__StreamEncoderInitStatusString[status] + ")";
    }
    else
    {
        constexpr std::size_t chunk = 4096;
        std::vector<FLAC__int32> block(chunk * 2);
        for (std::size_t at = 0; at < frames && error.empty(); at += chunk)
        {
            const std::size_t n = std::min(chunk, frames - at);
            for (std::size_t i = 0; i < n * 2; ++i)
            {
                block[i] = quantise(samples[at * 2 + i], bits);
            }
            if (!FLAC__stream_encoder_process_interleaved(encoder, block.data(), static_cast<unsigned>(n)))
            {
                error = "FLAC encoding failed";
            }
        }
        if (!FLAC__stream_encoder_finish(encoder) && error.empty())
        {
            error = "FLAC encoding failed at the end of the file";
        }
    }
    FLAC__stream_encoder_delete(encoder);

    if (!error.empty())
    {
        return std::unexpected(error);
    }
    return {};
}

} // namespace korre
