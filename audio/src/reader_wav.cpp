#include <algorithm>
#include <cstring>
#include <fstream>

#include "readers.h"

// RIFF/WAVE: integer PCM of 8, 16, 24 or 32 bits and IEEE float of 32 or 64 bits, mono or stereo,
// including the "extensible" header that 24-bit files usually carry. The chunks are walked properly,
// so files with metadata in front of the audio (LIST, bext, ...) are read correctly.

namespace korre::detail
{
namespace
{

constexpr std::uint16_t format_pcm = 1;
constexpr std::uint16_t format_float = 3;
constexpr std::uint16_t format_extensible = 0xFFFE;

std::uint16_t le16(const unsigned char* p) { return static_cast<std::uint16_t>(p[0] | (p[1] << 8)); }

std::uint32_t le32(const unsigned char* p)
{
    return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1]) << 8) |
           (static_cast<std::uint32_t>(p[2]) << 16) | (static_cast<std::uint32_t>(p[3]) << 24);
}

class wav_reader final : public audio_reader
{
public:
    wav_reader(std::ifstream file, audio_info info, std::uint16_t format, std::uint64_t data_offset)
        : file_(std::move(file)), info_(std::move(info)), format_(format), data_offset_(data_offset),
          bytes_per_sample_(info_.bits_per_sample / 8u), bytes_per_frame_(bytes_per_sample_ * info_.channels)
    {
    }

    const audio_info& info() const noexcept override { return info_; }

    std::size_t read(std::span<float> out) override
    {
        const std::uint64_t left = info_.frames - position_;
        const auto frames = static_cast<std::size_t>(std::min<std::uint64_t>(out.size() / 2, left));
        if (frames == 0)
        {
            return 0;
        }

        raw_.resize(frames * bytes_per_frame_);
        file_.read(reinterpret_cast<char*>(raw_.data()), static_cast<std::streamsize>(raw_.size()));
        const auto got = static_cast<std::size_t>(file_.gcount()) / bytes_per_frame_;
        if (got < frames)
        {
            // The header promised more than the file holds: play what is there.
            file_.clear();
            info_.frames = position_ + got;
            warning_ = "the file is shorter than its header says";
        }

        const unsigned char* p = raw_.data();
        float* o = out.data();
        for (std::size_t i = 0; i < got; ++i)
        {
            const float left_sample = sample(p);
            const float right_sample = info_.channels == 2 ? sample(p + bytes_per_sample_) : left_sample;
            *o++ = left_sample;
            *o++ = right_sample;
            p += bytes_per_frame_;
        }
        position_ += got;
        return got;
    }

    bool seek(std::uint64_t frame) override
    {
        position_ = std::min(frame, info_.frames);
        file_.clear();
        file_.seekg(static_cast<std::streamoff>(data_offset_ + position_ * bytes_per_frame_));
        return static_cast<bool>(file_);
    }

    std::string_view warning() const noexcept override { return warning_; }

private:
    float sample(const unsigned char* p) const
    {
        if (format_ == format_float)
        {
            if (bytes_per_sample_ == 4)
            {
                float v;
                std::memcpy(&v, p, 4);
                return v;
            }
            double v;
            std::memcpy(&v, p, 8);
            return static_cast<float>(v);
        }
        switch (bytes_per_sample_)
        {
        case 1: // the one unsigned format
            return static_cast<float>(p[0] - 128) / 128.0f;
        case 2:
            return static_cast<float>(static_cast<std::int16_t>(le16(p))) / 32768.0f;
        case 3:
        {
            // Put the three bytes at the top of a 32-bit word so that the sign comes along.
            const std::uint32_t top = (static_cast<std::uint32_t>(p[0]) << 8) | (static_cast<std::uint32_t>(p[1]) << 16) |
                                      (static_cast<std::uint32_t>(p[2]) << 24);
            return static_cast<float>(static_cast<std::int32_t>(top)) / 2147483648.0f;
        }
        default:
            return static_cast<float>(static_cast<double>(static_cast<std::int32_t>(le32(p))) / 2147483648.0);
        }
    }

    std::ifstream file_;
    audio_info info_;
    std::uint16_t format_;
    std::uint64_t data_offset_;
    std::size_t bytes_per_sample_;
    std::size_t bytes_per_frame_;
    std::uint64_t position_ = 0;
    std::vector<unsigned char> raw_;
    std::string warning_;
};

} // namespace

reader_result open_wav(const std::filesystem::path& path)
{
    const auto fail = [&](const std::string& what) { return std::unexpected(path.filename().string() + ": " + what); };

    std::error_code ec;
    const std::uint64_t file_size = std::filesystem::file_size(path, ec);
    std::ifstream file(path, std::ios::binary);
    if (ec || !file)
    {
        return std::unexpected("cannot open " + path.string());
    }

    unsigned char head[12];
    if (!file.read(reinterpret_cast<char*>(head), 12))
    {
        return fail("too short to be a WAV file");
    }
    if (std::memcmp(head, "RF64", 4) == 0)
    {
        return fail("RF64 (WAV over 4 GB) is not supported");
    }
    if (std::memcmp(head, "RIFF", 4) != 0 || std::memcmp(head + 8, "WAVE", 4) != 0)
    {
        return fail("not a WAV file");
    }

    bool have_format = false;
    std::uint16_t format = 0;
    std::uint16_t block_align = 0;
    audio_info info;
    info.container = "WAV";

    std::uint64_t pos = 12;
    while (pos + 8 <= file_size)
    {
        unsigned char chunk[8];
        file.seekg(static_cast<std::streamoff>(pos));
        if (!file.read(reinterpret_cast<char*>(chunk), 8))
        {
            break;
        }
        const std::uint32_t size = le32(chunk + 4);
        const std::uint64_t body = pos + 8;

        if (std::memcmp(chunk, "fmt ", 4) == 0)
        {
            unsigned char f[40] = {};
            const std::size_t n = std::min<std::size_t>(size, sizeof f);
            if (n < 16 || !file.read(reinterpret_cast<char*>(f), static_cast<std::streamsize>(n)))
            {
                return fail("damaged format chunk");
            }
            format = le16(f);
            info.channels = le16(f + 2);
            info.sample_rate = le32(f + 4);
            block_align = le16(f + 12);
            info.bits_per_sample = le16(f + 14);
            if (format == format_extensible && n >= 26)
            {
                format = le16(f + 24); // the real format is the first field of the sub-format id
            }
            have_format = true;
        }
        else if (std::memcmp(chunk, "data", 4) == 0)
        {
            if (!have_format)
            {
                return fail("audio data comes before the format description");
            }
            if (format != format_pcm && format != format_float)
            {
                return fail("compressed WAV (format tag " + std::to_string(format) + ") is not supported");
            }
            if (info.channels < 1 || info.channels > 2)
            {
                return fail(std::to_string(info.channels) + " channels: only mono and stereo are supported");
            }
            const unsigned bits = info.bits_per_sample;
            const bool bits_ok = format == format_float ? (bits == 32 || bits == 64)
                                                        : (bits == 8 || bits == 16 || bits == 24 || bits == 32);
            if (!bits_ok)
            {
                return fail(std::to_string(bits) + "-bit samples are not supported");
            }
            if (info.sample_rate == 0 || block_align != info.channels * (bits / 8))
            {
                return fail("inconsistent format description");
            }

            // Programs that write to a pipe leave the size at zero or at its maximum; a cut-off file
            // claims more than it has. In each case the audio runs to the end of the file.
            std::uint64_t bytes = size;
            if (bytes == 0 || bytes == 0xFFFFFFFFu || body + bytes > file_size)
            {
                bytes = file_size - body;
            }
            info.frames = bytes / block_align;
            info.encoding = format == format_float ? "float" : "PCM";

            auto reader = std::make_unique<wav_reader>(std::move(file), info, format, body);
            reader->seek(0);
            return reader;
        }

        pos = body + size + (size & 1u); // chunks are padded to an even length
    }

    return fail(have_format ? "no audio data in the file" : "no format description in the file");
}

} // namespace korre::detail
