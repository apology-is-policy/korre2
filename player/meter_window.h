#pragma once

#include "level_meter.h"

namespace korre
{

/// The level meter: two ladders of lamps, a mark on each that sticks at the highest point reached,
/// and a switch between the RMS and the peak reading.
class meter_window
{
public:
    explicit meter_window(level_meter& meter);

    void draw();

private:
    void content();

    level_meter& meter_;
    int width_ = 24;
    int height_ = 35;
};

} // namespace korre
