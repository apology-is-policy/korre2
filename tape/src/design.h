#pragma once

// Turning a profile's tables into filters for one sample rate. The formulas are those of the Python
// prototype (analysis/emulator.py); analysis/streamref.py repeats the filter designs below line by
// line, so the two can be compared number by number.

#include <complex>
#include <cstddef>
#include <vector>

#include "tape/profile.h"

namespace tape::detail
{

/// Piecewise-linear interpolation; outside the table the end values are held (numpy.interp).
double interp(const std::vector<double>& xs, const std::vector<double>& ys, double x) noexcept;

/// Density at f from a table on a linear frequency grid; zero outside the table.
double psd_linear(const std::vector<double>& freqs, const std::vector<double>& psd, double f) noexcept;

/// Density at f from a table on a log-spaced grid, interpolated log-log; zero outside the table.
double psd_log(const std::vector<double>& freqs, const std::vector<double>& psd, double f) noexcept;

/// The measured response of one channel at any frequency. Below the table the magnitude keeps the
/// slope of its lowest half octave and the phase its slope against log frequency; above it the
/// magnitude is held and the phase continues as a pure delay.
class response_curve
{
public:
    response_curve(const profile::response& eq, int channel);
    std::complex<double> operator()(double f) const noexcept;

private:
    std::vector<double> log_freqs_;
    const std::vector<double>& freqs_;
    const std::vector<double>& db_;
    const std::vector<double>& phase_;
    double low_db_slope_;    ///< dB per octave below the table
    double low_phase_slope_; ///< radians per octave below the table
    double high_phase_slope_; ///< radians per Hz above the table
};

/// Flicker depth (RMS fraction) at f: log-log interpolation, falling below the table with the slope
/// of its first two points (never rising), held above it.
double flicker_depth(const std::vector<double>& freqs, const std::vector<double>& rms, double f) noexcept;

/// Sizes of the engine's filters at a sample rate.
struct sizes
{
    std::size_t response_taps;  ///< length of the static-response filter
    std::size_t response_pre;   ///< taps before time zero (the filter's delay)
    std::size_t response_block; ///< partition of the convolver: adds its own length as delay
    std::size_t flicker_half;   ///< the flicker filters have 2 * half + 1 taps and delay by half
    std::size_t control_step;   ///< audio samples per sample of the slow wobble signals
};
sizes sizes_for(double sample_rate) noexcept;

/// The static response of one channel as a filter of sizes::response_taps taps, time zero at tap
/// sizes::response_pre. The delay common to both channels is taken out, their difference stays in.
std::vector<double> response_filter(const profile& p, int channel, double sample_rate);

/// A symmetric (zero-phase once its delay is allowed for) filter whose gain is the flicker depth.
std::vector<double> flicker_filter(const std::vector<double>& freqs, const std::vector<double>& rms, double sample_rate);

/// First-order high shelf, unity at DC and `gain_db` far above the corner 1 / (2 pi tau):
/// y[n] = b0 x[n] + b1 x[n-1] - a1 y[n-1]. Bilinear transform without prewarping (scipy.signal.bilinear).
struct shelf
{
    double b0, b1, a1;
};
shelf high_shelf(double tau, double gain_db, double sample_rate) noexcept;

} // namespace tape::detail
