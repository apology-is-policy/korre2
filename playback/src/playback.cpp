#include "korre/playback.h"

#include <algorithm>
#include <chrono>
#include <cmath>

namespace korre
{
namespace
{

constexpr double ahead_seconds = 0.15; ///< how much decoded audio waits in the queue

} // namespace

playback::playback(audio_output& output) : output_(output)
{
    decoder_ = std::jthread([this](const std::stop_token& stop) { decode_loop(stop); });
}

playback::~playback()
{
    playing_.store(false);
    output_.close(); // the audio thread is gone after this
    decoder_.request_stop();
    wake_.notify_all();
    // decoder_ joins as it is destroyed, before the members it uses
}

// ------------------------------------------------------------------------------------ the track

std::expected<void, std::string> playback::load(const std::filesystem::path& path)
{
    auto reader = open_audio(path);
    if (!reader)
    {
        return std::unexpected(reader.error());
    }
    const audio_info info = (*reader)->info();
    const auto rate = static_cast<double>(info.sample_rate);

    // The engine is designed for one sample rate. Keep it across tracks of the same rate: its wobble
    // then runs on from song to song, as a tape's does.
    std::unique_ptr<tape::engine> engine;
    if (profile_ && engine_rate_ != rate)
    {
        try
        {
            engine = make_engine(rate);
        }
        catch (const std::exception& e)
        {
            return std::unexpected(path.filename().string() + ": " + e.what());
        }
    }

    playing_.store(false);
    if (output_.is_open() && open_rate_ != rate)
    {
        output_.close(); // reopened at the new rate by play()
    }
    {
        const std::lock_guard lock(source_mutex_);
        reader_ = std::move(*reader);
        if (engine)
        {
            engine_ = std::move(engine);
            engine_rate_ = rate;
        }
        target_chunks_ = std::clamp<std::size_t>(static_cast<std::size_t>(std::ceil(ahead_seconds * rate / chunk_frames)), 4,
                                                 queue_.capacity() - 1);
        restart_from(0);
    }
    info_ = info;
    has_track_ = true;
    finished_.store(false);
    wake_.notify_all();
    return {};
}

void playback::unload()
{
    playing_.store(false);
    output_.close();
    {
        const std::lock_guard lock(source_mutex_);
        reader_.reset();
        done_ = true;
        epoch_.fetch_add(1);
    }
    has_track_ = false;
    info_ = {};
    finished_.store(false);
    pending_position_.store(0);
}

std::string playback::warning()
{
    const std::lock_guard lock(source_mutex_);
    return reader_ ? std::string(reader_->warning()) : std::string();
}

// ------------------------------------------------------------------------------------ transport

std::expected<void, std::string> playback::play()
{
    if (!has_track_)
    {
        return std::unexpected("no track loaded");
    }
    bool at_end;
    {
        const std::lock_guard lock(source_mutex_);
        at_end = done_ && queue_.size() == 0;
    }
    if (at_end || finished_.exchange(false))
    {
        seek(0);
    }
    if (auto ok = open_output(); !ok)
    {
        return ok;
    }
    playing_.store(true);
    return {};
}

void playback::pause() { playing_.store(false); }

void playback::seek(std::uint64_t frame)
{
    if (!has_track_)
    {
        return;
    }
    {
        const std::lock_guard lock(source_mutex_);
        if (info_.frames != 0)
        {
            frame = std::min(frame, info_.frames);
        }
        if (!reader_->seek(frame))
        {
            return; // the file cannot be repositioned: carry on where it is
        }
        restart_from(frame);
    }
    finished_.store(false);
    wake_.notify_all();
}

void playback::restart_from(std::uint64_t frame)
{
    // Called with the mutex held. Everything decoded so far belongs to the old position: a new epoch
    // makes the audio thread drop it.
    if (engine_)
    {
        engine_->reset();
        to_skip_ = engine_->delay().total;
    }
    else
    {
        to_skip_ = 0;
    }
    start_position_ = frame;
    fed_ = emitted_ = 0;
    reader_ended_ = false;
    done_ = false;
    pending_position_.store(frame);
    epoch_.fetch_add(1);
    kick_ = true;
    if (!output_.is_open())
    {
        drop_stale_chunks(); // no audio thread to do it
    }
}

std::uint64_t playback::position() const noexcept
{
    // Until the audio after a seek is actually heard, the answer is where the seek went.
    if (heard_epoch_.load() != epoch_.load())
    {
        return pending_position_.load();
    }
    return position_.load();
}

// ------------------------------------------------------------------------------------ the tape

std::unique_ptr<tape::engine> playback::make_engine(double sample_rate) const
{
    tape::settings s;
    s.sample_rate = sample_rate;
    s.ingredients = ingredients_;
    // A capture sits below its source by the record gain; make that up, so that tape and bypass are
    // equally loud.
    s.output_gain_db = -(profile_->gain_db[0] + profile_->gain_db[1]) / 2.0;
    // A different wobble each time the program runs, as on a real deck.
    s.seed = static_cast<std::uint64_t>(std::chrono::steady_clock::now().time_since_epoch().count());
    s.bypass = bypass_;
    return std::make_unique<tape::engine>(*profile_, s);
}

std::expected<void, std::string> playback::set_profile(const std::filesystem::path& path)
{
    auto loaded = tape::load_profile(path);
    if (!loaded)
    {
        return std::unexpected(loaded.error());
    }
    profile_ = std::move(*loaded);
    profile_name_ = profile_->name;

    std::unique_ptr<tape::engine> engine;
    if (has_track_)
    {
        try
        {
            engine = make_engine(static_cast<double>(info_.sample_rate));
        }
        catch (const std::exception& e)
        {
            profile_.reset();
            profile_name_.clear();
            return std::unexpected(std::string(e.what()));
        }
    }
    const std::uint64_t here = position();
    {
        const std::lock_guard lock(source_mutex_);
        engine_ = std::move(engine);
        engine_rate_ = engine_ ? static_cast<double>(info_.sample_rate) : 0.0;
        if (reader_ && reader_->seek(here))
        {
            restart_from(here); // what is queued went through the old path
        }
    }
    update_gain();
    wake_.notify_all();
    return {};
}

void playback::clear_profile()
{
    if (!profile_)
    {
        return;
    }
    profile_.reset();
    profile_name_.clear();
    const std::uint64_t here = position();
    {
        const std::lock_guard lock(source_mutex_);
        engine_.reset();
        engine_rate_ = 0;
        if (reader_ && reader_->seek(here))
        {
            restart_from(here);
        }
    }
    update_gain();
    wake_.notify_all();
}

void playback::set_bypass(bool on)
{
    bypass_ = on;
    const std::lock_guard lock(source_mutex_);
    if (engine_)
    {
        engine_->set_bypass(on);
    }
}

void playback::set_ingredients(std::uint32_t mask)
{
    ingredients_ = mask;
    const std::lock_guard lock(source_mutex_);
    if (engine_)
    {
        engine_->set_ingredients(mask);
    }
}

void playback::set_headroom_db(double db)
{
    headroom_db_ = std::max(db, 0.0);
    update_gain();
}

void playback::update_gain() noexcept
{
    gain_.store(profile_ ? static_cast<float>(std::pow(10.0, -headroom_db_ / 20.0)) : 1.0f);
}

// ------------------------------------------------------------------------------------ the output

std::expected<void, std::string> playback::open_output()
{
    const auto rate = static_cast<double>(info_.sample_rate);
    if (output_.is_open() && open_rate_ == rate)
    {
        return {};
    }
    output_.close();
    cursor_ = 0; // no audio thread is running: safe to touch its state
    drop_stale_chunks();
    auto ok = output_.open(rate, [this](std::span<float> out) { render(out); });
    if (ok)
    {
        open_rate_ = rate;
    }
    return ok;
}

std::expected<void, std::string> playback::restart_output()
{
    if (!output_.is_open())
    {
        return {};
    }
    output_.close();
    return open_output();
}

void playback::drop_stale_chunks() noexcept
{
    // Only while no audio thread is running: this thread then stands in as the queue's consumer.
    const std::uint32_t epoch = epoch_.load();
    while (chunk* c = queue_.front())
    {
        if (c->epoch == epoch)
        {
            break;
        }
        queue_.pop();
    }
}

playback::levels playback::take_levels() noexcept
{
    levels l;
    l.peak[0] = peak_[0].exchange(0.0f);
    l.peak[1] = peak_[1].exchange(0.0f);
    l.clipped = clipped_.load();
    l.underruns = underruns_.load();
    return l;
}

std::size_t playback::read_played(std::span<float> mono) noexcept
{
    std::size_t n = 0;
    while (n < mono.size())
    {
        const float* v = played_.front();
        if (!v)
        {
            break;
        }
        mono[n++] = *v;
        played_.pop();
    }
    return n;
}

// ------------------------------------------------------------------------------------ the audio thread

void playback::render(std::span<float> out) noexcept
{
    const std::size_t frames = out.size() / 2;
    const std::uint32_t epoch = epoch_.load(std::memory_order_acquire);
    const bool on = playing_.load(std::memory_order_relaxed);
    const float gain = gain_.load(std::memory_order_relaxed);

    std::size_t done = 0;
    float peak[2] = {0.0f, 0.0f};
    std::uint64_t clipped = 0;
    bool ran_dry = false;

    while (true)
    {
        chunk* c = queue_.front();
        if (c && c->epoch != epoch)
        {
            queue_.pop(); // from before the last seek
            cursor_ = 0;
            continue;
        }
        if (!on || done == frames)
        {
            break;
        }
        if (!c)
        {
            ran_dry = true;
            break;
        }

        const std::size_t n = std::min(frames - done, static_cast<std::size_t>(c->frames) - cursor_);
        const float* in = c->samples + 2 * cursor_;
        float* o = out.data() + 2 * done;
        for (std::size_t i = 0; i < n; ++i)
        {
            float l = in[2 * i] * gain;
            float r = in[2 * i + 1] * gain;
            peak[0] = std::max(peak[0], std::fabs(l));
            peak[1] = std::max(peak[1], std::fabs(r));
            if (std::fabs(l) > 1.0f)
            {
                l = std::copysign(1.0f, l);
                ++clipped;
            }
            if (std::fabs(r) > 1.0f)
            {
                r = std::copysign(1.0f, r);
                ++clipped;
            }
            o[2 * i] = l;
            o[2 * i + 1] = r;
            if (float* slot = played_.back()) // dropped if the interface is not reading
            {
                *slot = 0.5f * (l + r);
                played_.push();
            }
        }
        cursor_ += n;
        done += n;
        position_.store(c->position + cursor_, std::memory_order_relaxed);
        heard_epoch_.store(epoch, std::memory_order_relaxed);

        if (cursor_ == c->frames)
        {
            const bool last = c->last;
            queue_.pop();
            cursor_ = 0;
            if (last)
            {
                playing_.store(false);
                finished_.store(true);
                break;
            }
        }
    }

    std::fill(out.begin() + static_cast<std::ptrdiff_t>(2 * done), out.end(), 0.0f);

    for (int ch = 0; ch < 2; ++ch)
    {
        if (peak[ch] > peak_[ch].load(std::memory_order_relaxed))
        {
            peak_[ch].store(peak[ch], std::memory_order_relaxed);
        }
    }
    if (clipped != 0)
    {
        clipped_.fetch_add(clipped, std::memory_order_relaxed);
    }
    if (ran_dry && heard_epoch_.load(std::memory_order_relaxed) == epoch)
    {
        // Out of audio in the middle of playing. (Right after a seek the queue is empty by design.)
        underruns_.fetch_add(1, std::memory_order_relaxed);
    }
}

// ------------------------------------------------------------------------------------ the decoder thread

void playback::decode_loop(const std::stop_token& stop)
{
    std::unique_lock lock(source_mutex_);
    while (!stop.stop_requested())
    {
        bool produced = false;
        kick_ = false;
        if (reader_ && !done_ && queue_.size() < target_chunks_)
        {
            if (chunk* c = queue_.back())
            {
                if (decode_chunk(*c))
                {
                    queue_.push();
                }
                produced = true;
            }
        }
        if (!produced)
        {
            // Nothing to do: the queue is full enough or there is no track. Sleep until a load or a
            // seek wakes this thread, or a couple of milliseconds pass and the queue has drained a bit.
            wake_.wait_for(lock, stop, std::chrono::milliseconds(2), [this] { return kick_; });
        }
    }
}

bool playback::decode_chunk(chunk& c)
{
    // One block of the file through the engine. With the engine in the path the output is its delay
    // behind the input, so after a restart that much is dropped, and at the end of the file silence
    // is fed in until the engine has given back the whole track.
    float block[2 * chunk_frames];
    std::size_t got = 0;
    if (!reader_ended_)
    {
        got = reader_->read(std::span<float>(block, 2 * chunk_frames));
        fed_ += got;
        if (got < chunk_frames)
        {
            reader_ended_ = true;
        }
    }
    std::fill(block + 2 * got, block + 2 * chunk_frames, 0.0f);

    std::size_t available = got;
    if (engine_)
    {
        engine_->process(std::span<const float>(block, 2 * chunk_frames), std::span<float>(block, 2 * chunk_frames));
        available = chunk_frames;
    }
    const std::size_t skip = std::min(to_skip_, available);
    to_skip_ -= skip;
    const auto frames = static_cast<std::size_t>(std::min<std::uint64_t>(available - skip, fed_ - emitted_));

    c.position = start_position_ + emitted_;
    c.epoch = epoch_.load();
    c.frames = static_cast<std::uint16_t>(frames);
    std::copy_n(block + 2 * skip, 2 * frames, c.samples);
    emitted_ += frames;
    c.last = reader_ended_ && emitted_ == fed_;
    if (c.last)
    {
        done_ = true;
    }
    return frames > 0 || c.last; // an empty chunk is only worth sending as the end marker
}

} // namespace korre
