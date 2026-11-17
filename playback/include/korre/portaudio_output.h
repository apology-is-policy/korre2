#pragma once

// Sound through PortAudio: the system's audio devices.

#include <string>
#include <vector>

#include "korre/audio_output.h"

namespace korre
{

struct output_device
{
    int index = -1; ///< PortAudio's device number
    std::string name;
    double default_sample_rate = 0;
};

class portaudio_output final : public audio_output
{
public:
    portaudio_output();
    ~portaudio_output() override;

    portaudio_output(const portaudio_output&) = delete;
    portaudio_output& operator=(const portaudio_output&) = delete;

    /// The devices that can play sound. Asks the system again each time, so a device plugged in since
    /// shows up; only possible while no stream is open (otherwise the last list is returned).
    std::vector<output_device> devices();

    /// Which device open() uses: a PortAudio device number, or -1 for the system's default.
    void select(int device_index) noexcept { selected_ = device_index; }
    int selected() const noexcept { return selected_; }

    std::expected<void, std::string> open(double sample_rate, render_fn render) override;
    void close() override;
    bool is_open() const noexcept override { return stream_ != nullptr; }

    /// Called by PortAudio's callback (which lives in the .cpp, so this header needs no PortAudio).
    void fill(std::span<float> out) { render_(out); }

private:
    bool initialised_ = false;
    int selected_ = -1;
    void* stream_ = nullptr; ///< PaStream*
    render_fn render_;
    std::vector<output_device> devices_;
};

} // namespace korre
