#include "file_window.h"

#include <algorithm>
#include <cstring>

#include "frame.h"
#include "imtui/imtui.h"

namespace korre
{
namespace
{

bool playable(const std::filesystem::path& path)
{
    auto ext = path.extension().string();
    std::ranges::transform(ext, ext.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return ext == ".wav" || ext == ".flac" || ext == ".mp3" || ext == ".txt";
}

} // namespace

file_window::file_window(const std::filesystem::path& folder)
{
    std::strncpy(folder_, folder.string().c_str(), sizeof folder_ - 1);
    rescan();
}

void file_window::rescan()
{
    items_.clear();
    problem_.clear();
    selected_ = 0;
    std::error_code ec;
    for (const auto& entry : std::filesystem::directory_iterator(folder_, ec))
    {
        if (entry.is_regular_file(ec) && playable(entry.path()))
        {
            items_.push_back(entry.path());
        }
    }
    if (ec)
    {
        problem_ = "Cannot read that folder ";
    }
    std::ranges::sort(items_);
}

std::optional<std::filesystem::path> file_window::draw()
{
    chosen_.reset();
    ImGui::GetIO().ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
    ImGui::SetNextWindowPos(ImVec2(2, 15), ImGuiCond_Once);
    framed_window(width_, height_, "Audio_Select", [this] { content(); });
    return chosen_;
}

void file_window::content()
{
    ImGui::TextUnformatted(" ");
    ImGui::TextUnformatted("Workspace:");
    ImGui::TextUnformatted(" ");

    ImGui::PushStyleColor(ImGuiCol_FrameBg, static_cast<ImVec4>(ImColor(30, 30, 30)));
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(ImColor(255, 255, 104)));
    const bool entered = ImGui::InputText("", folder_, sizeof folder_, ImGuiInputTextFlags_EnterReturnsTrue);
    ImGui::PopStyleColor(2);
    ImGui::SameLine();
    if (ImGui::Button(" RELOAD ") || entered)
    {
        rescan();
    }

    ImGui::TextUnformatted(" ");
    if (!problem_.empty())
    {
        ImGui::TextUnformatted(problem_.c_str());
    }
    else if (items_.empty())
    {
        ImGui::TextUnformatted("No audio files at destination ");
    }
    else
    {
        ImGui::TextUnformatted("Selected: ");
        ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(ImColor(255, 255, 255)));
        ImGui::SameLine();
        ImGui::TextUnformatted(items_[selected_].filename().string().c_str());
        ImGui::PopStyleColor();
    }
    ImGui::TextUnformatted(" ");

    ImGui::TextUnformatted(" ");
    ImGui::SameLine();
    ImGui::PushStyleColor(ImGuiCol_FrameBg, static_cast<ImVec4>(ImColor(30, 30, 30)));
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(ImColor(255, 255, 104)));
    if (ImGui::BeginListBox("Audio Select", ImVec2(static_cast<float>(width_) - 2.f, static_cast<float>(height_) - 14.f)))
    {
        for (std::size_t n = 0; n < items_.size(); ++n)
        {
            const bool is_selected = selected_ == n;
            ImGui::PushID(static_cast<int>(n));
            if (ImGui::Selectable(items_[n].filename().string().c_str(), is_selected))
            {
                selected_ = n;
            }
            ImGui::PopID();
            if (is_selected)
            {
                ImGui::SetItemDefaultFocus();
            }
        }
        ImGui::EndListBox();
    }
    ImGui::PopStyleColor(2);

    ImGui::TextUnformatted("");
    ImGui::TextUnformatted("             ");
    ImGui::SameLine();
    ImGui::PushStyleColor(ImGuiCol_FrameBg, static_cast<ImVec4>(ImColor(60, 60, 60)));
    ImGui::Checkbox(" Normalize track to 0dB", &normalize_);
    ImGui::PopStyleColor();
    ImGui::TextUnformatted("");

    ImGui::TextUnformatted("");
    ImGui::SameLine();
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(ImColor(255, 255, 255)));
    ImGui::TextUnformatted("                ");
    ImGui::SameLine();
    if (ImGui::Button(" LOAD SELECTED AUDIO ") && !items_.empty())
    {
        chosen_ = items_[selected_];
    }
    ImGui::PopStyleColor();
}

} // namespace korre
