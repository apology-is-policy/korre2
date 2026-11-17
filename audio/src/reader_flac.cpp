#include <algorithm>

#include <FLAC/stream_decoder.h>

#include "readers.h"

// FLAC through libFLAC's C interface, one frame at a time.

namespace korre::detail
{
namespace
{

class flac_reader final : public audio_reader
{
public:
    flac_reader() : decoder_(FLAC__stream_decoder_new()) {}

    ~flac_reader() override
    {
        if (decoder_)
        {
            FLAC__stream_decoder_delete(decoder_); // finishes the decoder and closes the file
        }
    }

    flac_reader(const flac_reader&) = delete;
    flac_reader& operator=(const flac_reader&) = delete;

    std::expected<void, std::string> open(const std::filesystem::path& path)
    {
        if (!decoder_)
        {
            return std::unexpected("out of memory");
        }
        const auto status = FLAC__stream_decoder_init_file(decoder_, path.c_str(), on_write, on_metadata, on_error, this);
        if (status != FLAC__STREAM_DECODER_INIT_STATUS_OK)
        {
            return std::unexpected(std::string("cannot open as FLAC (") + FLAC__StreamDecoderInitStatusString[status] + ")");
        }
        if (!FLAC__stream_decoder_process_until_end_of_metadata(decoder_) || info_.sample_rate == 0)
        {
            return std::unexpected("not a FLAC file, or its header is damaged");
        }
        if (info_.channels < 1 || info_.channels > 2)
        {
            return std::unexpected(std::to_string(info_.channels) + " channels: only mono and stereo are supported");
        }
        return {};
    }

    const audio_info& info() const noexcept override { return info_; }

    std::size_t read(std::span<float> out) override
    {
        const std::size_t wanted = out.size() / 2;
        std::size_t done = 0;
        while (done < wanted)
        {
            if (pending_pos_ == pending_.size())
            {
                pending_.clear();
                pending_pos_ = 0;
                if (ended_ || !decode_one_frame())
                {
                    break;
                }
                continue;
            }
            const std::size_t n = std::min(wanted - done, (pending_.size() - pending_pos_) / 2);
            std::copy_n(pending_.begin() + static_cast<std::ptrdiff_t>(pending_pos_), n * 2, out.begin() + static_cast<std::ptrdiff_t>(done * 2));
            pending_pos_ += n * 2;
            done += n;
        }
        return done;
    }

    bool seek(std::uint64_t frame) override
    {
        pending_.clear();
        pending_pos_ = 0;
        if (info_.frames != 0 && frame >= info_.frames)
        {
            ended_ = true;
            return true;
        }
        // libFLAC decodes the frame that holds the target and hands it over starting at the target.
        if (FLAC__stream_decoder_seek_absolute(decoder_, frame))
        {
            ended_ = false;
            return true;
        }
        if (FLAC__stream_decoder_get_state(decoder_) == FLAC__STREAM_DECODER_SEEK_ERROR)
        {
            FLAC__stream_decoder_flush(decoder_); // makes the decoder usable again
        }
        pending_.clear();
        pending_pos_ = 0;
        return false;
    }

    std::string_view warning() const noexcept override { return warning_; }

private:
    /// Fills pending_ with the next frame. False at the end of the stream or on a fatal error.
    bool decode_one_frame()
    {
        while (pending_.empty())
        {
            if (!FLAC__stream_decoder_process_single(decoder_))
            {
                note("decoding stopped: " + std::string(FLAC__stream_decoder_get_resolved_state_string(decoder_)));
                ended_ = true;
                return false;
            }
            const auto state = FLAC__stream_decoder_get_state(decoder_);
            if (state == FLAC__STREAM_DECODER_END_OF_STREAM || state == FLAC__STREAM_DECODER_ABORTED)
            {
                ended_ = true;
                return !pending_.empty();
            }
        }
        return true;
    }

    void note(const std::string& what)
    {
        if (warning_.empty())
        {
            warning_ = what;
        }
    }

    static FLAC__StreamDecoderWriteStatus on_write(const FLAC__StreamDecoder*, const FLAC__Frame* frame,
                                                   const FLAC__int32* const buffer[], void* client)
    {
        auto& self = *static_cast<flac_reader*>(client);
        const std::size_t n = frame->header.blocksize;
        const unsigned channels = frame->header.channels;
        const float scale = 1.0f / static_cast<float>(1u << (frame->header.bits_per_sample - 1));

        const FLAC__int32* left = buffer[0];
        const FLAC__int32* right = channels >= 2 ? buffer[1] : buffer[0];
        const std::size_t at = self.pending_.size();
        self.pending_.resize(at + n * 2);
        float* o = self.pending_.data() + at;
        for (std::size_t i = 0; i < n; ++i)
        {
            *o++ = static_cast<float>(left[i]) * scale;
            *o++ = static_cast<float>(right[i]) * scale;
        }
        return FLAC__STREAM_DECODER_WRITE_STATUS_CONTINUE;
    }

    static void on_metadata(const FLAC__StreamDecoder*, const FLAC__StreamMetadata* metadata, void* client)
    {
        if (metadata->type != FLAC__METADATA_TYPE_STREAMINFO)
        {
            return;
        }
        auto& info = static_cast<flac_reader*>(client)->info_;
        const auto& si = metadata->data.stream_info;
        info.sample_rate = si.sample_rate;
        info.channels = static_cast<std::uint16_t>(si.channels);
        info.bits_per_sample = static_cast<std::uint16_t>(si.bits_per_sample);
        info.frames = si.total_samples;
        info.container = "FLAC";
        info.encoding = "PCM";
    }

    static void on_error(const FLAC__StreamDecoder*, FLAC__StreamDecoderErrorStatus status, void* client)
    {
        // A damaged stretch: libFLAC looks for the next good frame and carries on.
        static_cast<flac_reader*>(client)->note(std::string("damaged audio data (") + FLAC__StreamDecoderErrorStatusString[status] + ")");
    }

    FLAC__StreamDecoder* decoder_;
    audio_info info_;
    std::vector<float> pending_; ///< decoded, not yet handed out
    std::size_t pending_pos_ = 0;
    bool ended_ = false;
    std::string warning_;
};

} // namespace

reader_result open_flac(const std::filesystem::path& path)
{
    auto reader = std::make_unique<flac_reader>();
    if (auto ok = reader->open(path); !ok)
    {
        return std::unexpected(path.filename().string() + ": " + ok.error());
    }
    return reader;
}

} // namespace korre::detail
