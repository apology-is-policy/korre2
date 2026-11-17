#include "korre/portaudio_output.h"

#include <portaudio.h>

namespace korre
{
namespace
{

int stream_callback(const void*, void* output, unsigned long frames, const PaStreamCallbackTimeInfo*, PaStreamCallbackFlags, void* self)
{
    static_cast<portaudio_output*>(self)->fill(std::span<float>(static_cast<float*>(output), frames * 2));
    return paContinue;
}

} // namespace

portaudio_output::portaudio_output() { initialised_ = Pa_Initialize() == paNoError; }

portaudio_output::~portaudio_output()
{
    close();
    if (initialised_)
    {
        Pa_Terminate();
    }
}

std::vector<output_device> portaudio_output::devices()
{
    if (stream_ != nullptr)
    {
        return devices_;
    }
    // PortAudio reads the device list when it starts, so start it again to see what is there now.
    if (initialised_)
    {
        Pa_Terminate();
    }
    initialised_ = Pa_Initialize() == paNoError;
    devices_.clear();
    if (initialised_)
    {
        const int count = Pa_GetDeviceCount();
        for (int i = 0; i < count; ++i)
        {
            const PaDeviceInfo* d = Pa_GetDeviceInfo(i);
            if (d && d->maxOutputChannels >= 2)
            {
                devices_.push_back({i, d->name ? d->name : "", d->defaultSampleRate});
            }
        }
    }
    return devices_;
}

std::expected<void, std::string> portaudio_output::open(double sample_rate, render_fn render)
{
    close();
    if (!initialised_)
    {
        return std::unexpected("the audio system (PortAudio) did not start");
    }

    const int device = selected_ >= 0 ? selected_ : Pa_GetDefaultOutputDevice();
    const PaDeviceInfo* info = device == paNoDevice ? nullptr : Pa_GetDeviceInfo(device);
    if (!info)
    {
        return std::unexpected("no output device");
    }

    PaStreamParameters out{};
    out.device = device;
    out.channelCount = 2;
    out.sampleFormat = paFloat32;
    out.suggestedLatency = info->defaultHighOutputLatency; // a music player has no use for low latency

    render_ = std::move(render);
    PaStream* stream = nullptr;
    PaError err = Pa_OpenStream(&stream, nullptr, &out, sample_rate, paFramesPerBufferUnspecified, paNoFlag, stream_callback, this);
    if (err == paNoError)
    {
        err = Pa_StartStream(stream);
        if (err != paNoError)
        {
            Pa_CloseStream(stream);
        }
    }
    if (err != paNoError)
    {
        render_ = nullptr;
        return std::unexpected(std::string("cannot open \"") + info->name + "\" at " + std::to_string(static_cast<int>(sample_rate)) +
                               " Hz: " + Pa_GetErrorText(err));
    }
    stream_ = stream;
    return {};
}

void portaudio_output::close()
{
    if (stream_ != nullptr)
    {
        Pa_StopStream(static_cast<PaStream*>(stream_)); // returns once the callback has finished
        Pa_CloseStream(static_cast<PaStream*>(stream_));
        stream_ = nullptr;
        render_ = nullptr;
    }
}

} // namespace korre
