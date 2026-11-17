#include <algorithm>

// minimp3 is a single-header decoder; this file holds its implementation. Float output keeps the
// decoder's full precision instead of rounding to 16 bits.
#define MINIMP3_FLOAT_OUTPUT
#define MINIMP3_IMPLEMENTATION
#include <minimp3_ex.h>

#include "readers.h"

namespace korre::detail
{
namespace
{

class mp3_reader final : public audio_reader
{
public:
    mp3_reader() = default;

    ~mp3_reader() override
    {
        if (open_)
        {
            mp3dec_ex_close(&decoder_);
        }
    }

    mp3_reader(const mp3_reader&) = delete;
    mp3_reader& operator=(const mp3_reader&) = delete;

    std::expected<void, std::string> open(const std::filesystem::path& path)
    {
        // MP3D_SEEK_TO_SAMPLE scans the file once: that gives the exact length and an index for
        // sample-accurate seeking, and removes the encoder's padding at both ends.
        if (mp3dec_ex_open(&decoder_, path.c_str(), MP3D_SEEK_TO_SAMPLE) != 0)
        {
            return std::unexpected("cannot open as MP3");
        }
        open_ = true;
        const int channels = decoder_.info.channels;
        if (decoder_.samples == 0 || decoder_.info.hz <= 0 || channels < 1 || channels > 2)
        {
            return std::unexpected("no MP3 audio found in the file");
        }
        info_.sample_rate = static_cast<std::uint32_t>(decoder_.info.hz);
        info_.channels = static_cast<std::uint16_t>(channels);
        info_.bits_per_sample = 0;
        info_.container = "MP3";
        info_.encoding = "Layer " + std::string(static_cast<std::size_t>(std::clamp(decoder_.info.layer, 1, 3)), 'I');
        info_.bitrate_kbps = decoder_.info.bitrate_kbps;
        info_.frames = decoder_.samples / static_cast<std::uint64_t>(channels);
        return {};
    }

    const audio_info& info() const noexcept override { return info_; }

    std::size_t read(std::span<float> out) override
    {
        const std::size_t wanted = out.size() / 2;
        if (info_.channels == 2)
        {
            return mp3dec_ex_read(&decoder_, out.data(), wanted * 2) / 2;
        }
        // Mono: decode into the front half, then spread to both sides from the back.
        const std::size_t got = mp3dec_ex_read(&decoder_, out.data(), wanted);
        for (std::size_t i = got; i-- > 0;)
        {
            out[2 * i] = out[2 * i + 1] = out[i];
        }
        return got;
    }

    bool seek(std::uint64_t frame) override
    {
        frame = std::min(frame, info_.frames);
        return mp3dec_ex_seek(&decoder_, frame * info_.channels) == 0;
    }

private:
    mp3dec_ex_t decoder_{};
    bool open_ = false;
    audio_info info_;
};

} // namespace

reader_result open_mp3(const std::filesystem::path& path)
{
    auto reader = std::make_unique<mp3_reader>();
    if (auto ok = reader->open(path); !ok)
    {
        return std::unexpected(path.filename().string() + ": " + ok.error());
    }
    return reader;
}

} // namespace korre::detail
