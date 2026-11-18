#pragma once

// Playback of one track at a time, with the tape engine in the path.
//
// Three threads meet here, and each does one kind of work:
//   - the caller's thread (the interface) loads, plays, pauses, seeks and reads the state;
//   - a decoder thread reads the file in small pieces, runs them through the tape engine and puts
//     them in a queue, about 150 ms ahead of what is heard;
//   - the audio thread (the sound card's callback) only copies from that queue. It never decodes,
//     waits for a lock or allocates memory, so a slow disk or a busy interface cannot make it stutter.
// The caller's thread and the decoder thread share the file and the engine under a mutex; the audio
// thread is reached only through atomics and lock-free queues.
//
// Every method is for the caller's thread. Nothing here knows about the user interface.

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <expected>
#include <filesystem>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <string>
#include <thread>

#include "korre/audio_file.h"
#include "korre/audio_output.h"
#include "korre/spsc_queue.h"
#include "tape/engine.h"
#include "tape/profile.h"

namespace korre
{

class playback
{
public:
    /// The output must outlive the player.
    explicit playback(audio_output& output);
    ~playback();

    playback(const playback&) = delete;
    playback& operator=(const playback&) = delete;

    // ---- the track

    /// Opens a file and makes it the current track, paused at its start. On failure the current
    /// track stays as it was. `gain` scales the file before anything else (for "normalize").
    std::expected<void, std::string> load(const std::filesystem::path& path, double gain = 1.0);
    void unload();
    bool has_track() const noexcept { return has_track_; }
    const audio_info& info() const noexcept { return info_; }
    /// Trouble the decoder met that did not stop it (damaged data). Empty if none.
    std::string warning();

    // ---- transport

    /// Starts or resumes. At the end of the track it starts over.
    std::expected<void, std::string> play();
    void pause();
    bool playing() const noexcept { return playing_.load(std::memory_order_relaxed); }
    /// Continues from the given frame.
    void seek(std::uint64_t frame);
    /// The frame being heard now.
    std::uint64_t position() const noexcept;
    /// True once after the track has played to its end.
    bool take_finished() noexcept { return finished_.exchange(false); }

    // ---- the tape

    /// Plays through this profile from now on.
    std::expected<void, std::string> set_profile(const std::filesystem::path& path);
    /// Plays the file as it is.
    void clear_profile();
    bool has_profile() const noexcept { return profile_.has_value(); }
    const std::string& profile_name() const noexcept { return profile_name_; }

    /// With a profile loaded: hear the file as it is, at the same level and delay, to compare.
    void set_bypass(bool on);
    bool bypass() const noexcept { return bypass_; }
    /// Which parts of the tape model are on: a set of tape::ingredient bits.
    void set_ingredients(std::uint32_t mask);
    std::uint32_t ingredients() const noexcept { return ingredients_; }

    /// Level taken off while a profile is loaded, tape and bypass alike (dB, default 6). The tape's
    /// phase rotation raises the peaks of loud modern masters by about 5 dB at the same loudness; this
    /// keeps them below full scale.
    void set_headroom_db(double db);
    double headroom_db() const noexcept { return headroom_db_; }

    // ---- what is being played, for the meters

    struct levels
    {
        float peak[2] = {0, 0};      ///< largest sample since the last call, per channel
        double energy[2] = {0, 0};   ///< sum of the squared samples since the last call, per channel
        std::uint64_t frames = 0;    ///< how many frames those are (none while nothing plays)
        std::uint64_t clipped = 0;   ///< samples that reached full scale, in total
        std::uint64_t underruns = 0; ///< times the audio thread found the queue empty, in total
    };
    /// What was played since the last call. For one caller: the interface takes it once per frame
    /// and hands it to whatever shows levels.
    levels take_levels() noexcept;

    /// The samples just played, both channels mixed to one, oldest first. Returns how many were
    /// written. For the spectrum display.
    std::size_t read_played(std::span<float> mono) noexcept;

    /// The output device was changed: reopen the stream if it is open.
    std::expected<void, std::string> restart_output();

    static constexpr std::size_t chunk_frames = 256;

private:
    struct chunk
    {
        std::uint64_t position = 0; ///< frame in the track of the first frame in here
        std::uint32_t epoch = 0;    ///< which seek this audio belongs to
        std::uint16_t frames = 0;
        bool last = false;          ///< the track ends with this chunk
        float samples[2 * chunk_frames];
    };

    void render(std::span<float> out) noexcept;        // audio thread
    void decode_loop(const std::stop_token& stop);     // decoder thread
    bool decode_chunk(chunk& c);                       // decoder thread, with the mutex held
    void restart_from(std::uint64_t frame);            // caller's thread, with the mutex held
    std::unique_ptr<tape::engine> make_engine(double sample_rate) const;
    std::expected<void, std::string> open_output();
    void update_gain() noexcept;
    void drop_stale_chunks() noexcept;

    audio_output& output_;

    // ---- the caller's thread only
    bool has_track_ = false;
    audio_info info_;
    std::optional<tape::profile> profile_;
    std::string profile_name_;
    bool bypass_ = false;
    std::uint32_t ingredients_ = tape::all_ingredients;
    double headroom_db_ = 6.0;
    double open_rate_ = 0; ///< sample rate the output was opened at

    // ---- shared by the caller's thread and the decoder thread, under the mutex
    std::mutex source_mutex_;
    std::unique_ptr<audio_reader> reader_;
    float track_gain_ = 1.0f;
    std::unique_ptr<tape::engine> engine_;
    double engine_rate_ = 0;
    std::uint64_t start_position_ = 0; ///< frame the current run of decoding started at (the last seek)
    std::uint64_t fed_ = 0;            ///< frames read from the file since then
    std::uint64_t emitted_ = 0;        ///< frames put in the queue since then
    std::size_t to_skip_ = 0;          ///< engine output still to drop: its delay, after a restart
    bool reader_ended_ = false;
    bool done_ = true;                 ///< nothing more to decode until the next load or seek
    std::size_t target_chunks_ = 0;    ///< how far ahead to decode
    bool kick_ = false;                ///< set by a load or a seek: decode at once
    std::condition_variable_any wake_;

    // ---- to and from the audio thread
    spsc_queue<chunk> queue_{128};
    spsc_queue<float> played_{1 << 15};
    std::atomic<std::uint32_t> epoch_{0};
    std::atomic<std::uint32_t> heard_epoch_{0}; ///< epoch of the audio last played
    std::atomic<bool> playing_{false};
    std::atomic<bool> finished_{false};
    std::atomic<bool> has_warning_{false}; ///< the decoder has something to say (see warning())
    std::atomic<std::uint64_t> position_{0};
    std::atomic<std::uint64_t> pending_position_{0}; ///< where a seek went, until its audio is heard
    std::atomic<float> gain_{1.0f};
    std::atomic<float> peak_[2] = {0.0f, 0.0f};
    // Running totals, written by the audio thread only; take_levels() reports what was added since
    // it last looked. (A sum that is reset from another thread could lose an addition.)
    std::atomic<double> energy_total_[2] = {0.0, 0.0};
    std::atomic<std::uint64_t> frames_total_{0};
    double energy_seen_[2] = {0.0, 0.0};
    std::uint64_t frames_seen_ = 0;
    std::atomic<std::uint64_t> clipped_{0};
    std::atomic<std::uint64_t> underruns_{0};
    std::size_t cursor_ = 0; ///< audio thread only: frames already played from the front chunk

    std::jthread decoder_; // last member: it stops and joins before anything above goes away
};

} // namespace korre
