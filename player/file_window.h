#pragma once

#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace korre
{

/// The file selector: a folder (the "workspace"), the audio files and playlists in it, and a button
/// to put the selected one in the queue.
class file_window
{
public:
    explicit file_window(const std::filesystem::path& folder);

    /// Draws the window; returns the file the user asked to load in this frame, if any.
    std::optional<std::filesystem::path> draw();

    /// "Normalize track to 0dB": tracks are played with their loudest sample at full scale.
    bool normalize() const noexcept { return normalize_; }

private:
    void content();
    void rescan();

    std::vector<std::filesystem::path> items_;
    std::size_t selected_ = 0;
    char folder_[512] = {};
    std::string problem_; ///< why the folder could not be listed
    bool normalize_ = false;
    std::optional<std::filesystem::path> chosen_;
    int width_ = 41;
    int height_ = 22;
};

} // namespace korre
