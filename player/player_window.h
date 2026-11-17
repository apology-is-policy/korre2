#pragma once

#include <string>

#include "korre/playback.h"
#include "spectrum.h"
#include "tape_shelf.h"

namespace korre
{

/// The main window: the track's details, the tape controls, transport, position and the spectrum.
class player_window
{
public:
    player_window(playback& player, spectrum& display, tape_shelf& shelf);

    /// Draws the window. `message` is shown on its bottom line. Returns a problem met while acting on
    /// a click (a profile that would not load, a device that would not open), or an empty string.
    std::string draw(const std::string& message);

private:
    void content();
    void track_details();
    void tape_panel();
    void transport();
    void spectrum_box();

    playback& player_;
    spectrum& display_;
    tape_shelf& shelf_;
    const std::string* message_ = nullptr;
    std::string problem_;
    float peak_db_ = -120.0f;       ///< the level meter: jumps up, falls slowly
    std::uint64_t clipped_seen_ = 0;
    float clip_lamp_s_ = 0.0f;      ///< how much longer the CLIP lamp stays lit
    int width_ = 81;
    int height_ = 35;
};

} // namespace korre
