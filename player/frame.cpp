#include "frame.h"

#include <string>

#include "imtui/imtui.h"

namespace korre
{

void framed_window(int width, int height, const char* name, const std::function<void()>& content)
{
    ImGui::SetNextWindowSize(ImVec2(static_cast<float>(width), static_cast<float>(height)), ImGuiCond_Once);

    ImGui::PushStyleColor(ImGuiCol_WindowBg, static_cast<ImVec4>(ImColor(0, 0, 0)));
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(ImColor(255, 255, 255)));

    const ImGuiWindowFlags flags = ImGuiWindowFlags_NoScrollbar | ImGuiWindowFlags_NoScrollWithMouse | ImGuiWindowFlags_NoSavedSettings |
                                   ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoDecoration |
                                   ImGuiWindowFlags_NoResize;

    ImGui::Begin(name, nullptr, flags);

    // The box: top edge, sides, bottom edge.
    std::string edge;
    for (int i = 0; i < width - 3; ++i)
    {
        edge += "═";
    }
    ImGui::TextUnformatted(("╔" + edge + "╗").c_str());
    const std::string side = "║" + std::string(static_cast<std::size_t>(width - 3), ' ') + "║";
    for (int i = 0; i < height - 2; ++i)
    {
        ImGui::TextUnformatted(side.c_str());
    }
    ImGui::TextUnformatted(("╚" + edge + "╝").c_str());

    // The small box and the name, set into the top edge.
    ImGui::SetCursorPos(ImVec2(1, 0));
    ImGui::TextUnformatted("╡");
    ImGui::SameLine();
    ImGui::Button(" ");
    ImGui::SameLine();
    ImGui::TextUnformatted("╞");

    ImGui::SetCursorPos(ImVec2(7, 0));
    ImGui::TextUnformatted("╡");
    ImGui::SameLine();
    ImGui::TextUnformatted(name);
    ImGui::SameLine();
    ImGui::TextUnformatted("╞");

    ImGui::SetCursorPos(ImVec2(1, 1));
    ImGui::BeginChild("wnd_content", ImVec2(static_cast<float>(width - 1), static_cast<float>(height)), false, flags);

    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(ImColor(120, 220, 238)));
    ImGui::PushStyleColor(ImGuiCol_Button, static_cast<ImVec4>(ImColor(80, 80, 80)));
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, static_cast<ImVec4>(ImColor(120, 120, 120)));
    ImGui::PushStyleColor(ImGuiCol_ButtonActive, static_cast<ImVec4>(ImColor(71, 167, 169)));
    content();
    ImGui::PopStyleColor(4);

    ImGui::EndChild();
    ImGui::End();
    ImGui::PopStyleColor(2);
}

} // namespace korre
