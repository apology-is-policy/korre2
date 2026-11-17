#pragma once

#include "play_queue.h"

namespace korre
{

/// What the user did in the queue window during a frame, for the application to act on.
enum class queue_action
{
    none,
    play_current, ///< another track became current: load it and play
    unload,       ///< nothing is current any more
};

class queue_window
{
public:
    explicit queue_window(play_queue& queue) : queue_(queue) {}

    queue_action draw();

private:
    void content();

    play_queue& queue_;
    queue_action action_ = queue_action::none;
    int width_ = 41;
    int height_ = 13;
};

} // namespace korre
