#include "meter_window.h"

#include <format>
#include <string>

#include "frame.h"
#include "imtui/imtui.h"

namespace korre
{
namespace
{

/// The level each lamp of a ladder lights at, top to bottom: a dB apart near the top, where it
/// matters, and wider apart further down.
constexpr int steps[] = {0, -1, -2, -3, -4, -5, -6, -7, -8, -9, -10, -12, -14, -16, -18, -20, -24, -28, -32, -36, -42, -48, -54, -60};
constexpr int rows = static_cast<int>(sizeof steps / sizeof steps[0]);

const ImColor white(255, 255, 255);
const ImColor grey(110, 110, 110);
const ImColor unlit(48, 48, 48);
const ImColor axis_blue(120, 220, 238);
const ImColor lamp_on(0, 255, 0);
const ImColor lamp_off(60, 60, 60);

/// Red from -2 dB up, amber down to -9, green below.
ImColor zone(int db) { return db >= -2 ? ImColor(255, 60, 60) : db >= -9 ? ImColor(255, 215, 0) : ImColor(0, 220, 70); }

/// The topmost lamp a level reaches, or `rows` if it reaches none.
int top_lamp(double db)
{
    for (int i = 0; i < rows; ++i)
    {
        if (db >= steps[i])
        {
            return i;
        }
    }
    return rows;
}

void coloured(const ImColor& colour, const std::string& text)
{
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(colour));
    ImGui::TextUnformatted(text.c_str());
    ImGui::PopStyleColor();
}

} // namespace

meter_window::meter_window(level_meter& meter) : meter_(meter) {}

void meter_window::draw()
{
    ImGui::SetNextWindowPos(ImVec2(124, 2), ImGuiCond_Once);
    framed_window(width_, height_, "Audio_Level", [this] { content(); });
}

void meter_window::content()
{
    // ---- the reading: two switches, one lamp lit. Pressing one puts the other out.
    const auto choice = [&](float x, const char* label, level_meter::reading reading) {
        ImGui::SetCursorPos(ImVec2(x, 1));
        coloured(meter_.mode() == reading ? lamp_on : lamp_off, "█");
        ImGui::SameLine();
        ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(white));
        if (ImGui::Button(label))
        {
            meter_.set_mode(reading);
        }
        ImGui::PopStyleColor();
    };
    choice(2, " RMS ", level_meter::reading::rms);
    choice(11, " PEAK ", level_meter::reading::peak);

    // ---- the ladders
    constexpr float ladder_x[2] = {8, 14};
    constexpr float top = 4;
    ImGui::SetCursorPos(ImVec2(2, top - 1));
    coloured(axis_blue, "dB");
    ImGui::SetCursorPos(ImVec2(ladder_x[0] + 2, top - 1));
    coloured(white, "L");
    ImGui::SetCursorPos(ImVec2(ladder_x[1] + 2, top - 1));
    coloured(white, "R");

    for (int i = 0; i < rows; ++i)
    {
        const int db = steps[i];
        if (db % 6 == 0 || db == -3 || db == -9)
        {
            ImGui::SetCursorPos(ImVec2(1, top + static_cast<float>(i)));
            coloured(axis_blue, std::format("{:>3} ╴", db));
        }
    }
    for (int c = 0; c < 2; ++c)
    {
        const int bar = top_lamp(meter_.bar_db(c));
        const int mark = top_lamp(meter_.mark_db(c));
        for (int i = 0; i < rows; ++i)
        {
            ImGui::SetCursorPos(ImVec2(ladder_x[c], top + static_cast<float>(i)));
            if (i >= bar)
            {
                coloured(zone(steps[i]), "▆▆▆▆▆"); // lit: the bar
            }
            else if (i == mark)
            {
                coloured(zone(steps[i]), "━━━━━"); // the mark, above the bar
            }
            else
            {
                coloured(unlit, "▆▆▆▆▆");
            }
        }

        // The mark's level in figures, under its ladder.
        const double held = meter_.mark_db(c);
        ImGui::SetCursorPos(ImVec2(ladder_x[c] - 1, top + static_cast<float>(rows) + 1));
        coloured(held > -90.0 ? white : grey, held > -90.0 ? std::format("{:>6.1f}", held) : std::string("   ---"));
    }
    ImGui::SetCursorPos(ImVec2(1, top + static_cast<float>(rows) + 1));
    coloured(axis_blue, "max");

    // ---- samples at full scale
    ImGui::SetCursorPos(ImVec2(2, top + static_cast<float>(rows) + 3));
    coloured(meter_.over() ? ImColor(255, 60, 60) : lamp_off, "█");
    ImGui::SameLine();
    coloured(meter_.over() ? white : grey, " OVER");
}

} // namespace korre
