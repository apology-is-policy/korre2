#pragma once

// The tape engine: plays audio through a measured tape profile, block by block.
//
// The signal chain, in the physical order of a recording and its playback:
//   record gain -> saturation (a faint cubic, then treble saturation on the pre-emphasised signal)
//   -> static response per channel, magnitude and phase
//   -> timing, one moving delay per channel: slow transport wobble, the slow left-right difference,
//      and fast jitter (a part common to both channels and a part of each channel's own)
//   -> amplitude flicker, deeper towards the treble, and gain noise (a fast wobble of each
//      channel's level as a whole, with a depth per channel)
//   -> dropouts -> the background: noise and the deck's faint steady tones -> polarity
//
// The model and its numbers come from analysis/emulator.py; this is its streaming form. Nothing in
// here knows about files, audio devices or the user interface.

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <span>
#include <vector>

#include "tape/profile.h"

namespace tape
{

/// The parts of the model that can be switched on and off while it runs.
enum class ingredient : std::uint32_t
{
    eq = 1u << 0,           ///< static response (magnitude and phase)
    transport = 1u << 1,    ///< slow wobble common to both channels
    differential = 1u << 2, ///< slow left-right timing difference
    jitter = 1u << 3,       ///< fast timing jitter
    flicker = 1u << 4,      ///< amplitude flicker and gain noise
    dropouts = 1u << 5,
    hiss = 1u << 6,       ///< noise and the steady tones
    saturation = 1u << 7, ///< both saturation stages
};

constexpr std::uint32_t all_ingredients = 0xFF;

constexpr std::uint32_t operator|(ingredient a, ingredient b) { return static_cast<std::uint32_t>(a) | static_cast<std::uint32_t>(b); }
constexpr std::uint32_t operator|(std::uint32_t a, ingredient b) { return a | static_cast<std::uint32_t>(b); }

struct settings
{
    double sample_rate = 44100;

    /// Every random process (wobble, jitter, flicker, noise) follows from the seed, and does not
    /// depend on which ingredients are switched on.
    std::uint64_t seed = 1;

    /// How hard the tape is driven, per channel (dB). Empty: the level the profile was fitted at.
    std::optional<stereo> record_gain_db;

    /// Applied at the very end (dB). 0 keeps the level of a real capture, which sits below the source
    /// by about the record gain.
    double output_gain_db = 0;

    /// +1 or -1 to force the polarity; 0 takes the profile's.
    int polarity = 0;

    std::uint32_t ingredients = all_ingredients;

    /// Start bypassed (see engine::set_bypass).
    bool bypass = false;
};

/// How far the output lags the input, in sample frames, and where the delay comes from.
struct latency
{
    std::size_t response = 0; ///< the static-response filter
    std::size_t timing = 0;   ///< the moving delay line, at rest
    std::size_t flicker = 0;  ///< the flicker filters
    std::size_t total = 0;
};

/// The random control signals behind one stretch of output, one value per output frame, for checking
/// the engine against the Python model (analysis/verify_engine.py). Timing values are microseconds.
struct trace
{
    std::vector<double> transport;
    std::vector<double> differential;
    std::vector<double> jitter_common;
    std::array<std::vector<double>, 2> jitter_own;
    std::vector<double> flicker_common;
    std::array<std::vector<double>, 2> flicker_own;
    std::array<std::vector<double>, 2> gain_noise; ///< zeros if the profile has none
    std::array<std::vector<double>, 2> dropout_gain;
    std::array<std::vector<double>, 2> background; ///< noise plus tones, as added to the signal

    /// The filters the engine designed for this sample rate (filled on the first traced call).
    std::array<std::vector<double>, 2> response_filter;
    std::size_t response_pre = 0; ///< tap of the response filter that is time zero
    std::vector<double> flicker_filter_common;
    std::vector<double> flicker_filter_own;
    std::array<std::vector<double>, 2> gain_noise_filter; ///< empty if the profile has none
};

class engine
{
public:
    /// Designs the filters for the sample rate and allocates everything the engine will need.
    /// Throws std::invalid_argument for a sample rate it cannot work at.
    engine(const profile& p, const settings& s);
    ~engine();

    engine(engine&&) noexcept;
    engine& operator=(engine&&) noexcept;

    /// Processes interleaved stereo frames (L R L R ...); `in` and `out` hold the same number of
    /// samples and may be the same memory. Does not allocate, lock or block, so it may run on an
    /// audio thread. The output is `delay().total` frames behind the input.
    void process(std::span<const float> in, std::span<float> out) noexcept;

    /// The same, also recording the control signals (this one allocates: for offline checks only).
    void process(std::span<const float> in, std::span<float> out, trace& record);

    latency delay() const noexcept;

    /// Switch parts of the model while it runs: a set of `ingredient` bits. Changes are faded in
    /// over a few milliseconds. Safe to call from another thread than the one that processes.
    void set_ingredients(std::uint32_t mask) noexcept;
    std::uint32_t ingredients() const noexcept;

    /// Bypass passes the input through unchanged, delayed by the engine's latency so that switching
    /// does not jump in time. Safe to call from another thread.
    void set_bypass(bool on) noexcept;
    bool bypass() const noexcept;

    /// Forgets the audio inside the engine (after a seek or a new track). The random processes carry
    /// on. Not safe while another thread is in process().
    void reset() noexcept;

private:
    struct impl;
    std::unique_ptr<impl> impl_;
};

} // namespace tape
