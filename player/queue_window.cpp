#include "queue_window.h"

#include <string>

#include "frame.h"
#include "imtui/imtui.h"

namespace korre
{
namespace
{

void coloured(const ImColor& colour, const std::string& text)
{
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(colour));
    ImGui::TextUnformatted(text.c_str());
    ImGui::PopStyleColor();
}

/// The lamp next to a switch: green when on, red when off.
void lamp(bool on)
{
    coloured(on ? ImColor(0, 255, 0) : ImColor(255, 0, 0), "█");
    ImGui::SameLine();
}

} // namespace

queue_action queue_window::draw()
{
    action_ = queue_action::none;
    ImGui::SetNextWindowPos(ImVec2(83, 2), ImGuiCond_Once);
    framed_window(width_, height_, "Audio_Queue", [this] { content(); });
    return action_;
}

void queue_window::content()
{
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(ImColor(255, 255, 255)));

    ImGui::TextUnformatted("");
    ImGui::TextUnformatted(" ");
    ImGui::SameLine();
    if (ImGui::Button("  ◀◀ \n PREV \n") && queue_.previous())
    {
        action_ = queue_action::play_current;
    }
    ImGui::SameLine();
    ImGui::TextUnformatted(" ");
    ImGui::SameLine();
    if (ImGui::Button("  ▶▶ \n NEXT \n") && !queue_.upcoming().empty())
    {
        action_ = queue_.next() ? queue_action::play_current : queue_action::unload;
    }

    ImGui::SetCursorPos(ImVec2(29, 1));
    if (ImGui::Button("  CLR  "))
    {
        queue_.clear();
        action_ = queue_action::unload;
    }
    ImGui::SetCursorPos(ImVec2(29, 3));
    if (ImGui::Button("  DEL  ") && !queue_.upcoming().empty())
    {
        const auto was_current = *queue_.current();
        queue_.remove_last();
        if (queue_.upcoming().empty())
        {
            action_ = queue_action::unload;
        }
        else if (*queue_.current() != was_current)
        {
            action_ = queue_action::play_current;
        }
    }

    ImGui::SetCursorPos(ImVec2(29, 5));
    lamp(queue_.shuffle());
    if (ImGui::Button(" SHF  "))
    {
        queue_.set_shuffle(!queue_.shuffle());
    }

    ImGui::SetCursorPos(ImVec2(29, 7));
    lamp(queue_.repeat_one);
    if (ImGui::Button(" RPT1 "))
    {
        queue_.repeat_one = !queue_.repeat_one;
    }

    ImGui::SetCursorPos(ImVec2(29, 9));
    ImGui::Button("  OTH  ");

    // The list: two tracks back, the current one, two ahead, and how many more.
    ImGui::SetCursorPos(ImVec2(0, 4));
    ImGui::TextUnformatted(" ");
    ImGui::SameLine();
    ImGui::PushStyleColor(ImGuiCol_ChildBg, static_cast<ImVec4>(ImColor(30, 30, 30)));
    ImGui::BeginChild("qu", ImVec2(29, 6));

    const auto& history = queue_.history();
    const auto& upcoming = queue_.upcoming();
    const auto name = [](const play_queue::entry& e) { return e.path.filename().string(); };

    if (history.size() >= 2)
    {
        coloured(ImColor(179, 179, 179), "┃  " + name(history[1]));
    }
    else
    {
        ImGui::TextUnformatted(" ");
    }
    if (!history.empty())
    {
        coloured(ImColor(221, 221, 138), "┃  " + name(history[0]));
    }
    else
    {
        ImGui::TextUnformatted(" ");
    }

    coloured(ImColor(255, 255, 104), upcoming.empty() ? std::string("┣━ N/A") : "┣━ " + name(upcoming[0]));
    if (upcoming.size() >= 2)
    {
        coloured(ImColor(221, 221, 138), "┃  " + name(upcoming[1]));
    }
    if (upcoming.size() >= 3)
    {
        coloured(ImColor(179, 179, 179), "┃  " + name(upcoming[2]));
    }
    if (upcoming.size() >= 4)
    {
        coloured(ImColor(140, 140, 140), "┖  +" + std::to_string(upcoming.size() - 3) + ". ...");
    }

    ImGui::EndChild();
    ImGui::PopStyleColor();

    ImGui::PopStyleColor();
}

} // namespace korre
