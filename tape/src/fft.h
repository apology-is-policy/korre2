#pragma once

// A small complex FFT in double precision, for power-of-two sizes. The engine needs it for filter
// design, for the partitioned convolution and for synthesising noise with a given spectrum; none of
// that is heavy enough to want a faster library (and pffft, used by the display, is single precision).

#include <complex>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace tape::detail
{

class fft
{
public:
    explicit fft(std::size_t size); ///< size must be a power of two, at least 2

    std::size_t size() const noexcept { return size_; }

    /// X[k] = sum x[n] exp(-2 pi i k n / N), in place.
    void forward(std::complex<double>* data) const noexcept { transform(data, false); }
    /// x[n] = sum X[k] exp(+2 pi i k n / N), in place. Not scaled: divide by N for the inverse of forward().
    void inverse(std::complex<double>* data) const noexcept { transform(data, true); }

private:
    void transform(std::complex<double>* data, bool inverse) const noexcept;

    std::size_t size_;
    std::vector<double> cos_;        ///< cos(2 pi k / N), k < N/2
    std::vector<double> sin_;        ///< sin(2 pi k / N), k < N/2
    std::vector<std::uint32_t> rev_; ///< bit-reversed index
};

/// Smallest power of two that is not less than n.
std::size_t pow2_ceil(std::size_t n) noexcept;

} // namespace tape::detail
