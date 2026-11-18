#include "braille.h"

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace korre
{
namespace
{

/// The bit of the dot at (column 0..1, row 0..3) of a cell, in the Unicode Braille block (U+2800 + bits).
constexpr std::uint8_t dot_bit[2][4] = {{0x01, 0x02, 0x04, 0x40}, {0x08, 0x10, 0x20, 0x80}};

} // namespace

std::vector<std::string> braille_curve(std::span<const float> values, int rows)
{
    rows = std::max(rows, 1);
    const std::size_t cells = (values.size() + 1) / 2;
    const int height = 4 * rows; // in dots
    std::vector<std::uint8_t> bits(static_cast<std::size_t>(rows) * cells, 0);

    const auto dot_row = [&](float v) {
        const float clamped = std::isfinite(v) ? std::clamp(v, 0.0f, 1.0f) : 0.0f;
        return (height - 1) - static_cast<int>(std::lround(clamped * static_cast<float>(height - 1)));
    };
    const auto set = [&](std::size_t x, int y) {
        bits[static_cast<std::size_t>(y / 4) * cells + x / 2] |= dot_bit[x % 2][y % 4];
    };

    int previous = 0;
    for (std::size_t x = 0; x < values.size(); ++x)
    {
        const int y = dot_row(values[x]);
        // From this point towards the one before, stopping short of it: the step between two
        // neighbours is drawn in the later one's column.
        int from = y, to = y;
        if (x > 0 && previous < y)
        {
            from = previous + 1;
        }
        else if (x > 0 && previous > y)
        {
            to = previous - 1;
        }
        for (int d = from; d <= to; ++d)
        {
            set(x, d);
        }
        previous = y;
    }

    std::vector<std::string> out(static_cast<std::size_t>(rows));
    for (std::size_t r = 0; r < out.size(); ++r)
    {
        std::string& line = out[r];
        line.reserve(cells * 3);
        for (std::size_t c = 0; c < cells; ++c)
        {
            const std::uint8_t b = bits[r * cells + c];
            if (b == 0)
            {
                line += ' ';
                continue;
            }
            const unsigned code = 0x2800u + b; // three bytes of UTF-8
            line += static_cast<char>(0xE0 | (code >> 12));
            line += static_cast<char>(0x80 | ((code >> 6) & 0x3F));
            line += static_cast<char>(0x80 | (code & 0x3F));
        }
    }
    return out;
}

} // namespace korre
