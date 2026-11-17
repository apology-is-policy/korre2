#pragma once

// Endless random signals with a prescribed spectrum: the wobble, jitter, flicker and hiss of the tape.
//
// The Python prototype makes each of them for a whole track at once, with one FFT as long as the
// track. Here they have to run forever, so each is made in overlapping blocks: every block is an
// independent Gaussian signal with exactly the wanted spectrum, and consecutive blocks are cross-faded
// with a sine/cosine window, which keeps the variance constant. The spectrum of the result is the
// wanted one, smoothed over about two FFT bins.

#include <complex>
#include <cstddef>
#include <functional>
#include <vector>

#include "fft.h"
#include "random.h"

namespace tape::detail
{

class spectral_noise
{
public:
    /// `psd(f)` is the one-sided power density at f Hz (units squared per Hz); `rate` is the rate the
    /// signal is produced at and `block` the FFT size (power of two), which sets the resolution to
    /// about 2 * rate / block Hz. `unit_variance` rescales the spectrum so that the signal has variance 1.
    /// `stagger` (0..block/2) offsets the block boundaries, so that several generators do not all do
    /// their FFT at the same moment.
    spectral_noise(const std::function<double(double)>& psd, double rate, std::size_t block, rng random,
                   bool unit_variance = false, std::size_t stagger = 0);

    double next() noexcept
    {
        if (pos_ == half_)
        {
            refill();
        }
        return ready_[pos_++];
    }

    /// The standard deviation the signal is built to have.
    double sigma() const noexcept { return sigma_; }

private:
    void refill() noexcept;
    void synthesise() noexcept;

    std::size_t size_;
    std::size_t half_;
    fft fft_;
    rng random_;
    std::vector<double> amplitude_;           ///< per bin 0..size/2
    std::vector<double> window_;              ///< sin(pi (i + 0.5) / size)
    std::vector<std::complex<double>> block_; ///< real part: one block, imaginary part: the next one
    bool imaginary_next_ = false;             ///< the imaginary half of block_ has not been used yet
    std::vector<double> tail_;                ///< second half of the previous block, windowed
    std::vector<double> ready_;               ///< finished samples
    std::size_t pos_;
    double sigma_ = 0;
};

/// A slow random signal (below about 60 Hz) produced at the audio rate: generated at a low control
/// rate, which keeps a fine frequency resolution affordable, and interpolated up with a short
/// windowed sinc.
class slow_noise
{
public:
    /// The control rate is audio_rate / step; `block` is the FFT size at the control rate.
    slow_noise(const std::function<double(double)>& psd, double audio_rate, std::size_t step, std::size_t block, rng random);

    double next() noexcept
    {
        if (phase_ == 0)
        {
            history_[head_] = source_.next();
            head_ = (head_ + 1) % taps;
        }
        const double* k = kernel_.data() + phase_ * taps;
        double v = 0;
        for (std::size_t i = 0; i < taps; ++i)
        {
            v += k[i] * history_[(head_ + i) % taps];
        }
        phase_ = phase_ + 1 == step_ ? 0 : phase_ + 1;
        return v;
    }

    double sigma() const noexcept { return source_.sigma(); }

private:
    static constexpr std::size_t taps = 16; ///< control samples under the interpolation kernel

    spectral_noise source_;
    std::size_t step_;
    std::vector<double> kernel_; ///< step_ rows of `taps` weights, oldest sample first
    double history_[taps] = {};
    std::size_t head_ = 0; ///< index of the oldest sample in history_
    std::size_t phase_ = 0;
};

} // namespace tape::detail
