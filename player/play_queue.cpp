#include "play_queue.h"

#include <algorithm>
#include <fstream>
#include <random>
#include <string>

namespace korre
{

std::size_t play_queue::add(const std::filesystem::path& path)
{
    std::size_t count = 0;
    auto ext = path.extension().string();
    std::ranges::transform(ext, ext.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (ext == ".txt")
    {
        std::ifstream file(path);
        std::string line;
        while (std::getline(file, line))
        {
            while (!line.empty() && (line.back() == '\r' || line.back() == ' ' || line.back() == '\t'))
            {
                line.pop_back();
            }
            if (line.empty())
            {
                continue;
            }
            std::filesystem::path track(line);
            if (track.is_relative())
            {
                track = path.parent_path() / track;
            }
            upcoming_.push_back({std::move(track), added_++});
            ++count;
        }
    }
    else
    {
        upcoming_.push_back({path, added_++});
        count = 1;
    }
    if (shuffle_ && count > 0)
    {
        set_shuffle(true); // mix the new ones in
    }
    return count;
}

bool play_queue::next()
{
    if (upcoming_.empty())
    {
        return false;
    }
    history_.push_front(std::move(upcoming_.front()));
    upcoming_.pop_front();
    return !upcoming_.empty();
}

bool play_queue::previous()
{
    if (history_.empty())
    {
        return false;
    }
    upcoming_.push_front(std::move(history_.front()));
    history_.pop_front();
    return true;
}

bool play_queue::finished()
{
    if (repeat_one)
    {
        return !upcoming_.empty();
    }
    return next();
}

void play_queue::remove_last()
{
    if (upcoming_.empty())
    {
        return;
    }
    // "Last" is the one added last, wherever shuffle has put it.
    const auto last = std::ranges::max_element(upcoming_, {}, &entry::order);
    upcoming_.erase(last);
}

void play_queue::set_shuffle(bool on)
{
    shuffle_ = on;
    if (upcoming_.size() < 3)
    {
        return; // the current track stays put, and one track to come has only one order
    }
    const auto first = upcoming_.begin() + 1;
    if (on)
    {
        std::mt19937 random{std::random_device{}()};
        std::shuffle(first, upcoming_.end(), random);
    }
    else
    {
        std::sort(first, upcoming_.end(), [](const entry& a, const entry& b) { return a.order < b.order; });
    }
}

} // namespace korre
