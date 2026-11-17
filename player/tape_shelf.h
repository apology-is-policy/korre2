#pragma once

// The tape profiles on offer: the .json files of one folder, and which of them is in the deck.

#include <expected>
#include <filesystem>
#include <string>
#include <vector>

#include "korre/playback.h"

namespace korre
{

class tape_shelf
{
public:
    tape_shelf(playback& player, std::filesystem::path folder);

    void rescan();
    const std::filesystem::path& folder() const noexcept { return folder_; }
    const std::vector<std::filesystem::path>& profiles() const noexcept { return profiles_; }

    /// Index into profiles() of the profile in use, or -1 for none (the file as it is).
    int selected() const noexcept { return selected_; }
    /// Puts a profile in the deck, or takes it out with -1.
    std::expected<void, std::string> select(int index);
    /// By file name, with or without ".json", or by path; "none" takes the tape out.
    std::expected<void, std::string> select(const std::string& name);
    /// The next (+1) or previous (-1) choice, going round through "none".
    std::expected<void, std::string> step(int direction);

private:
    playback& player_;
    std::filesystem::path folder_;
    std::vector<std::filesystem::path> profiles_;
    int selected_ = -1;
};

} // namespace korre
