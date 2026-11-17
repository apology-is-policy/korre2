#include "tape_shelf.h"

#include <algorithm>

namespace korre
{

tape_shelf::tape_shelf(playback& player, std::filesystem::path folder) : player_(player), folder_(std::move(folder)) { rescan(); }

void tape_shelf::rescan()
{
    const std::filesystem::path current = selected_ >= 0 ? profiles_[static_cast<std::size_t>(selected_)] : std::filesystem::path();
    profiles_.clear();
    std::error_code ec;
    for (const auto& entry : std::filesystem::directory_iterator(folder_, ec))
    {
        if (entry.is_regular_file(ec) && entry.path().extension() == ".json")
        {
            profiles_.push_back(entry.path());
        }
    }
    std::ranges::sort(profiles_);
    const auto it = std::ranges::find(profiles_, current);
    selected_ = it == profiles_.end() ? -1 : static_cast<int>(it - profiles_.begin());
}

std::expected<void, std::string> tape_shelf::select(int index)
{
    if (index < 0 || index >= static_cast<int>(profiles_.size()))
    {
        player_.clear_profile();
        selected_ = -1;
        return {};
    }
    auto ok = player_.set_profile(profiles_[static_cast<std::size_t>(index)]);
    if (ok)
    {
        selected_ = index;
    }
    return ok;
}

std::expected<void, std::string> tape_shelf::select(const std::string& name)
{
    if (name == "none")
    {
        return select(-1);
    }
    for (std::size_t i = 0; i < profiles_.size(); ++i)
    {
        if (profiles_[i].filename() == name || profiles_[i].stem() == name)
        {
            return select(static_cast<int>(i));
        }
    }
    // A profile from somewhere else: put it on the shelf too.
    const std::filesystem::path path(name);
    std::error_code ec;
    if (std::filesystem::is_regular_file(path, ec))
    {
        profiles_.push_back(path);
        return select(static_cast<int>(profiles_.size()) - 1);
    }
    return std::unexpected("no profile \"" + name + "\" in " + folder_.string());
}

std::expected<void, std::string> tape_shelf::step(int direction)
{
    const int choices = static_cast<int>(profiles_.size()) + 1; // "none" is one of them
    const int next = ((selected_ + 1 + direction) % choices + choices) % choices - 1;
    return select(next);
}

} // namespace korre
