#pragma once

// Where the sound goes. The player talks to this small interface, so the whole playback path can run
// in a test with no sound card: `manual_output` hands the audio to whoever asks for it.

#include <atomic>
#include <chrono>
#include <cstddef>
#include <expected>
#include <functional>
#include <mutex>
#include <span>
#include <string>
#include <thread>
#include <vector>

namespace korre
{

class audio_output
{
public:
    /// Fills `out` (interleaved stereo float) with the next audio. Called on the audio thread: it must
    /// not block, lock or allocate.
    using render_fn = std::function<void(std::span<float> out)>;

    virtual ~audio_output() = default;

    /// Starts asking `render` for audio at the given sample rate. Closes a stream that is already open.
    virtual std::expected<void, std::string> open(double sample_rate, render_fn render) = 0;
    /// Stops; `render` is not called again once this returns.
    virtual void close() = 0;
    virtual bool is_open() const noexcept = 0;
};

/// An output that plays nothing: the caller pulls the audio. For tests and offline use.
/// pull() may be called from another thread than open() and close(); like a sound card, close() does
/// not return while a pull is in progress.
class manual_output final : public audio_output
{
public:
    std::expected<void, std::string> open(double sample_rate, render_fn render) override
    {
        const std::lock_guard lock(mutex_);
        sample_rate_ = sample_rate;
        render_ = std::move(render);
        open_.store(true);
        return {};
    }
    void close() override
    {
        const std::lock_guard lock(mutex_);
        render_ = nullptr;
        open_.store(false);
    }
    bool is_open() const noexcept override { return open_.load(); }

    double sample_rate() const noexcept { return sample_rate_; }

    /// What the sound card would have been given for the next `frames` frames (silence if closed).
    std::vector<float> pull(std::size_t frames)
    {
        std::vector<float> out(frames * 2, 0.0f);
        const std::lock_guard lock(mutex_);
        if (render_)
        {
            render_(out);
        }
        return out;
    }

private:
    std::mutex mutex_;
    std::atomic<bool> open_{false};
    double sample_rate_ = 0;
    render_fn render_;
};

/// An output that plays to nowhere at the real pace: a thread of its own asks for audio the way a
/// sound card would. For running the player without a sound device (kora --device none).
class silent_output final : public audio_output
{
public:
    ~silent_output() override { close(); }

    std::expected<void, std::string> open(double sample_rate, render_fn render) override
    {
        close();
        open_.store(true);
        thread_ = std::jthread([render = std::move(render), sample_rate](const std::stop_token& stop) {
            constexpr std::size_t frames = 256;
            std::vector<float> buffer(2 * frames);
            const auto period = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                std::chrono::duration<double>(static_cast<double>(frames) / sample_rate));
            auto due = std::chrono::steady_clock::now();
            while (!stop.stop_requested())
            {
                render(buffer);
                due += period;
                std::this_thread::sleep_until(due);
            }
        });
        return {};
    }
    void close() override
    {
        if (thread_.joinable())
        {
            thread_.request_stop();
            thread_.join();
        }
        open_.store(false);
    }
    bool is_open() const noexcept override { return open_.load(); }

private:
    std::atomic<bool> open_{false};
    std::jthread thread_;
};

} // namespace korre
