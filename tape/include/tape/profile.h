#pragma once

// A tape profile: what one deck with one kind of cassette does to sound, as measured by the analysis
// scripts (analysis/fitprofile.py, calibrate.py) and stored as JSON in profiles/.
//
// Everything is a table in physical units (Hz, dB, radians, microseconds), so a profile does not
// depend on the sample rate it was measured at: the engine designs its filters for the rate it runs at.

#include <array>
#include <expected>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tape
{

/// One value per channel: [0] left, [1] right.
using stereo = std::array<double, 2>;

struct profile
{
    std::string name;
    int version = 0;

    /// Record level of the song the profile was fitted on (dB): how hard the tape was driven.
    stereo gain_db{};
    /// Delay of each channel through the chain. Only the difference is used: the common part is dropped.
    stereo delay_us{};
    /// +1, or -1 if the chain turns the waveform upside down (the WM-D6C captures do).
    int polarity = 1;

    /// Static response per channel on a log-spaced frequency grid: magnitude and phase.
    struct response
    {
        std::vector<double> freqs;
        std::array<std::vector<double>, 2> db;
        std::array<std::vector<double>, 2> phase; ///< radians, unwrapped
    } eq;

    /// Background noise per channel, one-sided power spectral density (full scale squared per Hz).
    struct noise
    {
        std::vector<double> freqs;
        std::array<std::vector<double>, 2> psd;
    } hiss;

    /// Slow timing wobble common to both channels, with the transport's mechanical lines.
    /// Density in microseconds squared per Hz. It hands over to `jitter` around crossover_hz.
    struct wobble
    {
        std::vector<double> freqs;
        std::vector<double> psd_us2_per_hz;
        double crossover_hz = 0; ///< 0: no fade (the differential part)

        /// A rotating part's own wobble (the capstan's 7.5 Hz, its harmonics, the motor): a steady
        /// sine. Kept apart from the table because a narrow peak in a noise spectrum fades in and out
        /// over tens of seconds, which the deck's lines do not. Absent in older profiles.
        ///
        /// A tape recorded and played on the same deck carries each such line twice: once frozen into
        /// the tape when it was recorded, once added when it is played, a hair apart in frequency
        /// (the tape did not run at exactly the same speed both times). The two beat: over minutes
        /// the flutter swells to the sum of the two and fades to their difference. A profile lists
        /// them as two lines; with `phase` on both, the beat starts where it stood on the fitted
        /// stretch of tape.
        struct line
        {
            double hz = 0;
            double us = 0; ///< RMS, microseconds
            /// The sine's phase at the first sample, radians: us * sqrt(2) * sin(2 pi hz t + phase).
            /// Without it the line starts at a phase drawn from the seed.
            std::optional<double> phase;
        };
        std::vector<line> lines;
    };
    wobble transport;
    wobble differential; ///< left minus right

    /// Fast timing jitter (scrape flutter): a part common to both channels and a part of their own.
    struct fast_timing
    {
        std::vector<double> freqs;
        std::vector<double> psd_common_us2_per_hz;
        std::vector<double> psd_indep_us2_per_hz;
    } jitter;

    /// Amplitude flicker (head contact): how fast it moves, and how deep it is at each audio frequency.
    struct amplitude_flicker
    {
        std::vector<double> rate_freqs;
        std::vector<double> rate_psd; ///< shape only: the engine scales it to unit variance
        std::vector<double> depth_freqs;
        std::vector<double> depth_common; ///< RMS fraction, shared by both channels
        std::vector<double> depth_indep;  ///< RMS fraction, each channel's own
    } flicker;

    /// Gain noise: a fast wobble (up to a few hundred Hz) of each channel's level as a whole, each
    /// channel with its own depth (the left track runs along the tape's edge and has more). Absent in
    /// older profiles.
    struct gain_noise_set
    {
        std::vector<double> rate_freqs;
        std::vector<double> rate_psd; ///< shape only: the engine scales it to unit variance
        std::vector<double> depth_freqs;
        std::array<std::vector<double>, 2> depth; ///< RMS fraction per channel; held outside the table
    };
    std::optional<gain_noise_set> gain_noise;

    struct dropout_event
    {
        double depth_db = 0;
        double dur_ms = 0;
        bool both = false; ///< both channels at once
    };
    struct dropout_set
    {
        double rate_per_min = 0;
        std::vector<dropout_event> events; ///< measured events to draw from
    } dropouts;

    struct treble_saturation
    {
        double tau_s = 0;    ///< pre-emphasis corner as a time constant
        double shelf_db = 0; ///< pre-emphasis gain far above the corner
        double c = 0;        ///< cubic coefficient on the pre-emphasised signal
    };
    struct saturation_set
    {
        /// Level of the cubic's third harmonic below a signal at the reference level, per channel
        /// (the left track, along the tape's edge, distorts more). A profile gives one number for
        /// both channels or one for each.
        stereo cubic_rel_db{};
        std::optional<double> ref_rms_dbfs;  ///< absent: no flat cubic
        std::optional<treble_saturation> hf; ///< absent: no treble saturation (the metal tape)
    } saturation;

    /// The deck's faint steady tones (capstan and motor rates, mains hum).
    struct tone
    {
        double hz = 0;
        stereo dbfs{};        ///< RMS level per channel
        double phase_deg = 0; ///< left relative to right
    };
    std::vector<tone> tones;
};

/// Reads a profile. On failure the string says what is wrong (missing table, mismatched lengths, ...).
std::expected<profile, std::string> parse_profile(std::string_view json);
std::expected<profile, std::string> load_profile(const std::filesystem::path& path);

} // namespace tape
