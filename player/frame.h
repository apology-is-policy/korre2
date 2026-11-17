#pragma once

// The look of a korre window: a double-line box drawn with text, the name in the top edge, and the
// content inside it.

#include <functional>

namespace korre
{

/// Draws a window of `width` x `height` character cells called `name` and runs `content` inside it.
/// Call ImGui::SetNextWindowPos() first to place it.
void framed_window(int width, int height, const char* name, const std::function<void()>& content);

} // namespace korre
