#include "convolver.h"

#include <algorithm>
#include <stdexcept>

namespace tape::detail
{

partitioned_convolver::partitioned_convolver(std::span<const double> taps, std::size_t block)
    : block_(block), parts_(taps.size() / block), fft_(2 * block), filter_(parts_ * (block + 1)),
      history_(parts_ * (block + 1)), input_(2 * block, 0.0), output_(block, 0.0), work_(2 * block)
{
    if (parts_ == 0 || taps.size() != parts_ * block)
    {
        throw std::invalid_argument("filter length must be a multiple of the block size");
    }
    // Each partition of the filter, zero-padded to two blocks, as a spectrum.
    for (std::size_t p = 0; p < parts_; ++p)
    {
        std::fill(work_.begin(), work_.end(), std::complex<double>{});
        for (std::size_t i = 0; i < block_; ++i)
        {
            work_[i] = taps[p * block_ + i];
        }
        fft_.forward(work_.data());
        std::copy_n(work_.begin(), block_ + 1, filter_.begin() + static_cast<std::ptrdiff_t>(p * (block_ + 1)));
    }
}

void partitioned_convolver::reset() noexcept
{
    std::fill(history_.begin(), history_.end(), std::complex<double>{});
    std::fill(input_.begin(), input_.end(), 0.0);
    std::fill(output_.begin(), output_.end(), 0.0);
    pos_ = 0;
}

void partitioned_convolver::process(double* samples, std::size_t n) noexcept
{
    double* collecting = input_.data() + block_;
    for (std::size_t i = 0; i < n; ++i)
    {
        collecting[pos_] = samples[i];
        samples[i] = output_[pos_];
        if (++pos_ == block_)
        {
            run_block();
            pos_ = 0;
        }
    }
}

void partitioned_convolver::run_block() noexcept
{
    const std::size_t bins = block_ + 1;

    // Spectrum of the last two input blocks. Its circular convolution with a filter partition is
    // correct in the second half (the first half wraps around), and that half is what is kept.
    for (std::size_t i = 0; i < 2 * block_; ++i)
    {
        work_[i] = input_[i];
    }
    fft_.forward(work_.data());
    newest_ = (newest_ + parts_ - 1) % parts_;
    std::copy_n(work_.begin(), bins, history_.begin() + static_cast<std::ptrdiff_t>(newest_ * bins));

    // Partition p of the filter acts on the input of p blocks ago.
    auto* acc = reinterpret_cast<double*>(work_.data());
    std::fill(acc, acc + 2 * bins, 0.0);
    for (std::size_t p = 0; p < parts_; ++p)
    {
        const auto* x = reinterpret_cast<const double*>(history_.data() + ((newest_ + p) % parts_) * bins);
        const auto* h = reinterpret_cast<const double*>(filter_.data() + p * bins);
        for (std::size_t k = 0; k < bins; ++k)
        {
            const double xr = x[2 * k], xi = x[2 * k + 1], hr = h[2 * k], hi = h[2 * k + 1];
            acc[2 * k] += xr * hr - xi * hi;
            acc[2 * k + 1] += xr * hi + xi * hr;
        }
    }
    for (std::size_t k = 1; k < block_; ++k) // the upper half of a real signal's spectrum mirrors the lower
    {
        work_[2 * block_ - k] = std::conj(work_[k]);
    }
    fft_.inverse(work_.data());

    const double scale = 1.0 / static_cast<double>(2 * block_);
    for (std::size_t i = 0; i < block_; ++i)
    {
        output_[i] = work_[block_ + i].real() * scale;
    }
    std::copy_n(input_.begin() + static_cast<std::ptrdiff_t>(block_), block_, input_.begin());
}

} // namespace tape::detail
