#pragma once

// The order of play: what is on now, what comes next, what has been played. No interface code in
// here, so it can be tested on its own; queue_window draws it.

#include <cstdint>
#include <deque>
#include <filesystem>

namespace korre
{

class play_queue
{
public:
    struct entry
    {
        std::filesystem::path path;
        std::uint64_t order = 0; ///< the order it was added in: what switching shuffle off goes back to
    };

    /// Adds a track at the end; a .txt file is a playlist, one path per line (a relative path is taken
    /// from the playlist's own folder). Returns how many tracks were added.
    std::size_t add(const std::filesystem::path& path);

    /// The track that is on, then the ones to come.
    const std::deque<entry>& upcoming() const noexcept { return upcoming_; }
    /// The tracks already played, the latest first.
    const std::deque<entry>& history() const noexcept { return history_; }
    const std::filesystem::path* current() const noexcept { return upcoming_.empty() ? nullptr : &upcoming_.front().path; }

    /// The current track goes to the history. Returns whether another one is now current.
    bool next();
    /// The latest track of the history becomes current again. Returns whether there was one.
    bool previous();
    /// What happens when the current track has played to its end: as next(), unless it repeats.
    bool finished();

    /// Empties the queue; the history stays.
    void clear() { upcoming_.clear(); }
    /// Takes away the track added last.
    void remove_last();

    /// Shuffle reorders the tracks to come, not the one that is on. Switching it off puts those that
    /// are left back in the order they were added.
    void set_shuffle(bool on);
    bool shuffle() const noexcept { return shuffle_; }

    bool repeat_one = false; ///< the current track starts over when it ends

private:
    std::deque<entry> upcoming_;
    std::deque<entry> history_;
    std::uint64_t added_ = 0;
    bool shuffle_ = false;
};

} // namespace korre
