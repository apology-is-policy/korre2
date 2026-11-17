#pragma once

// A long FIR filter applied block by block in the frequency domain (uniformly partitioned
// convolution). The cost per sample barely depends on the filter's length, where a direct filter of
// 16,000 taps would take most of a processor core. The price is a delay of one partition.

#include <complex>
#include <cstddef>
#include <span>
#include <vector>

#include "fft.h"

namespace tape::detail
{

class partitioned_convolver
{
public:
    /// `taps.size()` must be a multiple of `block`, and `block` a power of two.
    partitioned_convolver(std::span<const double> taps, std::size_t block);

    /// Filters n samples in place. The output lags the input by `block` samples (plus whatever delay
    /// the filter itself has).
    void process(double* samples, std::size_t n) noexcept;

    /// Forgets the signal: as if silence had been playing.
    void reset() noexcept;

    std::size_t delay() const noexcept { return block_; }

private:
    void run_block() noexcept;

    std::size_t block_;
    std::size_t parts_;
    fft fft_;
    std::vector<std::complex<double>> filter_;  ///< parts_ spectra of block_ + 1 bins
    std::vector<std::complex<double>> history_; ///< the last parts_ input spectra, a ring
    std::size_t newest_ = 0;
    std::vector<double> input_;                 ///< previous block, then the block being collected
    std::vector<double> output_;                ///< the finished block being handed out
    std::vector<std::complex<double>> work_;
    std::size_t pos_ = 0;
};

} // namespace tape::detail
