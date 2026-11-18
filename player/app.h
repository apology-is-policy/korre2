#pragma once

// The application: the terminal interface around one playback object.

#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "file_window.h"
#include "korre/playback.h"
#include "korre/portaudio_output.h"
#include "level_meter.h"
#include "meter_window.h"
#include "play_queue.h"
#include "player_window.h"
#include "queue_window.h"
#include "spectrum.h"
#include "tape_shelf.h"

namespace ImTui
{
struct TScreen;
}

namespace korre
{

/// What the command line asked for.
struct options
{
    std::vector<std::filesystem::path> files; ///< tracks and playlists to queue at the start
    std::filesystem::path workspace;          ///< the folder the file selector opens in
    std::filesystem::path profiles;           ///< the folder of tape profiles
    std::optional<std::string> profile;       ///< the tape to start with
    std::optional<std::string> device;        ///< output device: a number, part of its name, or "none"
    bool play = false;                        ///< start playing the first track at once
};

class app
{
public:
    explicit app(options opt);
    ~app();

    /// Runs the interface until the user quits. Returns the process exit code.
    int run();

    /// The output devices, for --list-devices.
    static std::vector<output_device> list_devices();

private:
    void frame();
    void menu_bar();
    void after_frame();

    void enqueue(const std::filesystem::path& path);
    /// Loads the queue's current track, moving on past files that will not open.
    void load_current(bool then_play);
    void unload();
    void say(std::string message, bool is_error = false);
    void choose_device(int index);

    options options_;
    std::unique_ptr<audio_output> output_;
    portaudio_output* sound_card_ = nullptr; ///< output_ if it is a real sound card, for the device menu
    playback player_;
    spectrum spectrum_;
    play_queue queue_;
    tape_shelf shelf_;
    queue_window queue_window_;
    file_window file_window_;
    player_window player_window_;
    level_meter meter_;
    meter_window meter_window_;

    std::vector<output_device> devices_;
    std::string message_;
    bool message_is_error_ = false;
    double message_age_s_ = 0; ///< a message is shown for a while, then goes
    std::string warned_for_; ///< the track whose decoder warning has been shown
    ImTui::TScreen* screen_ = nullptr;
    bool quit_ = false;
};

} // namespace korre
