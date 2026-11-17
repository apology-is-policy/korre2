#include "fft.h"

#include <cmath>
#include <numbers>
#include <stdexcept>
#include <utility>

namespace tape::detail
{

std::size_t pow2_ceil(std::size_t n) noexcept
{
    std::size_t p = 1;
    while (p < n)
    {
        p <<= 1;
    }
    return p;
}

fft::fft(std::size_t size) : size_(size)
{
    if (size < 2 || (size & (size - 1)) != 0)
    {
        throw std::invalid_argument("fft size must be a power of two");
    }
    cos_.resize(size / 2);
    sin_.resize(size / 2);
    for (std::size_t k = 0; k < size / 2; ++k)
    {
        const double a = 2.0 * std::numbers::pi * static_cast<double>(k) / static_cast<double>(size);
        cos_[k] = std::cos(a);
        sin_[k] = std::sin(a);
    }
    rev_.resize(size);
    std::size_t bits = 0;
    while ((std::size_t{1} << bits) < size)
    {
        ++bits;
    }
    for (std::size_t i = 0; i < size; ++i)
    {
        std::size_t r = 0;
        for (std::size_t b = 0; b < bits; ++b)
        {
            r |= ((i >> b) & 1u) << (bits - 1 - b);
        }
        rev_[i] = static_cast<std::uint32_t>(r);
    }
}

void fft::transform(std::complex<double>* data, bool inverse) const noexcept
{
    // std::complex<double> is laid out as two doubles; working on them directly keeps the compiler from
    // calling its slow, NaN-careful complex multiplication.
    auto* d = reinterpret_cast<double*>(data);
    const std::size_t n = size_;

    for (std::size_t i = 0; i < n; ++i)
    {
        const std::size_t j = rev_[i];
        if (i < j)
        {
            std::swap(d[2 * i], d[2 * j]);
            std::swap(d[2 * i + 1], d[2 * j + 1]);
        }
    }

    const double sign = inverse ? 1.0 : -1.0;
    for (std::size_t half = 1; half < n; half <<= 1)
    {
        const std::size_t stride = n / (2 * half);
        for (std::size_t start = 0; start < n; start += 2 * half)
        {
            for (std::size_t j = 0; j < half; ++j)
            {
                const double wr = cos_[j * stride];
                const double wi = sign * sin_[j * stride];
                double* a = d + 2 * (start + j);
                double* b = a + 2 * half;
                const double tr = wr * b[0] - wi * b[1];
                const double ti = wr * b[1] + wi * b[0];
                b[0] = a[0] - tr;
                b[1] = a[1] - ti;
                a[0] += tr;
                a[1] += ti;
            }
        }
    }
}

} // namespace tape::detail
