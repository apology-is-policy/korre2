#pragma once

// A curve drawn with Braille characters: each character cell holds 2 x 4 dots, so a plot of W x H
// cells has 2W x 4H points, the finest a text terminal can show.

#include <span>
#include <string>
#include <vector>

namespace korre
{

/// Draws `values` (each 0..1, one per dot column: two per character cell) as a curve on `rows`
/// character rows. Neighbouring points are joined, so the curve is unbroken however steep it is.
/// Returns one UTF-8 string per row, the top row first; a cell with no dot in it is a space.
std::vector<std::string> braille_curve(std::span<const float> values, int rows);

} // namespace korre
