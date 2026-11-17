#include "noise.h"

#include <cmath>
#include <numbers>

namespace tape::detail
{

spectral_noise::spectral_noise(const std::function<double(double)>& psd, double rate, std::size_t block, rng random,
                               bool unit_variance, std::size_t stagger)
    : size_(block), half_(block / 2), fft_(block), random_(random), amplitude_(block / 2 + 1), window_(block),
      block_(block), tail_(block / 2), ready_(block / 2), pos_(block / 2)
{
    // A bin of the two-sided FFT below gets a complex Gaussian of variance 2 a^2; bins k and N - k
    // both contribute, so the signal's variance is the sum over all N bins of a^2. With
    // a^2 = psd * rate / (2 N) that is the integral of the one-sided density. No DC.
    double variance = 0;
    amplitude_[0] = 0;
    for (std::size_t k = 1; k <= half_; ++k)
    {
        const double f = static_cast<double>(k) * rate / static_cast<double>(size_);
        const double a2 = std::max(psd(f), 0.0) * rate / (2.0 * static_cast<double>(size_));
        amplitude_[k] = std::sqrt(a2);
        variance += k == half_ ? a2 : 2.0 * a2;
    }
    if (unit_variance && variance > 0)
    {
        const double scale = 1.0 / std::sqrt(variance);
        for (double& a : amplitude_)
        {
            a *= scale;
        }
        variance = 1.0;
    }
    sigma_ = std::sqrt(variance);

    for (std::size_t i = 0; i < size_; ++i)
    {
        window_[i] = std::sin(std::numbers::pi * (static_cast<double>(i) + 0.5) / static_cast<double>(size_));
    }

    // Start as if a block had come before, so that the signal is stationary from its first sample.
    synthesise();
    for (std::size_t i = 0; i < half_; ++i)
    {
        tail_[i] = window_[half_ + i] * block_[half_ + i].real();
    }
    refill();
    pos_ = std::min(stagger, half_ - 1);
}

void spectral_noise::synthesise() noexcept
{
    // Independent complex Gaussians on all N bins with an even amplitude profile: the real and the
    // imaginary part of the transform are then two independent real signals with the same spectrum,
    // so one FFT yields two blocks.
    auto* d = reinterpret_cast<double*>(block_.data());
    d[0] = d[1] = 0;
    for (std::size_t k = 1; k < size_; ++k)
    {
        const double a = amplitude_[k <= half_ ? k : size_ - k];
        d[2 * k] = a * random_.normal();
        d[2 * k + 1] = a * random_.normal();
    }
    fft_.inverse(block_.data());
}

void spectral_noise::refill() noexcept
{
    const bool use_imaginary = imaginary_next_;
    if (!use_imaginary)
    {
        synthesise();
    }
    imaginary_next_ = !use_imaginary;

    const auto* d = reinterpret_cast<const double*>(block_.data()) + (use_imaginary ? 1 : 0);
    for (std::size_t i = 0; i < half_; ++i)
    {
        ready_[i] = tail_[i] + window_[i] * d[2 * i];
        tail_[i] = window_[half_ + i] * d[2 * (half_ + i)];
    }
    pos_ = 0;
}

slow_noise::slow_noise(const std::function<double(double)>& psd, double audio_rate, std::size_t step, std::size_t block, rng random)
    : source_(psd, audio_rate / static_cast<double>(step), block, random), step_(step), kernel_(step * taps)
{
    // Kaiser-windowed sinc with its cutoff at the control rate's Nyquist frequency. The signal lives
    // below a third of the control rate, its first image above two thirds, so the wide transition band
    // of a 16-sample kernel fits in between (stop band below -80 dB).
    const double beta = 8.0;
    const auto bessel_i0 = [](double x) {
        double sum = 1, term = 1;
        for (int k = 1; k < 60; ++k)
        {
            term *= (x / (2.0 * k)) * (x / (2.0 * k));
            sum += term;
        }
        return sum;
    };
    const double half = static_cast<double>(taps) / 2.0;
    for (std::size_t phase = 0; phase < step_; ++phase)
    {
        // Output sits `phase / step` of a control sample after history sample taps/2 - 1.
        const double frac = static_cast<double>(phase) / static_cast<double>(step_);
        double sum = 0;
        double* row = kernel_.data() + phase * taps;
        for (std::size_t i = 0; i < taps; ++i)
        {
            const double t = static_cast<double>(i) - (half - 1.0) - frac; // distance in control samples
            const double x = std::numbers::pi * t;
            const double sinc = std::fabs(x) < 1e-12 ? 1.0 : std::sin(x) / x;
            const double r = t / half;
            const double w = std::fabs(r) < 1.0 ? bessel_i0(beta * std::sqrt(1.0 - r * r)) / bessel_i0(beta) : 0.0;
            row[i] = sinc * w;
            sum += row[i];
        }
        for (std::size_t i = 0; i < taps; ++i)
        {
            row[i] /= sum; // exact at DC
        }
    }
    for (std::size_t i = 0; i < taps; ++i) // fill the history, so the first outputs are already valid
    {
        history_[i] = source_.next();
    }
}

} // namespace tape::detail
