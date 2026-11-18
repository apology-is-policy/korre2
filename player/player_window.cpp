#include "player_window.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <format>
#include <string>
#include <vector>

#include "braille.h"
#include "frame.h"
#include "imtui/imtui.h"
#include "tape/engine.h"

namespace korre
{
namespace
{

const ImColor white(255, 255, 255);
const ImColor yellow(255, 255, 104);
const ImColor axis_blue(120, 220, 238);
const ImColor grey(140, 140, 140);

void coloured(const ImColor& colour, const std::string& text)
{
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(colour));
    ImGui::TextUnformatted(text.c_str());
    ImGui::PopStyleColor();
}

/// "label" in the window's colour, the value in white, on one line.
void detail(const char* label, const std::string& value)
{
    ImGui::TextUnformatted(label);
    ImGui::SameLine();
    coloured(white, value);
}

} // namespace

player_window::player_window(playback& player, spectrum& display, tape_shelf& shelf) : player_(player), display_(display), shelf_(shelf) {}

std::string player_window::draw(const std::string& message, const playback::levels& levels)
{
    message_ = &message;
    levels_ = &levels;
    problem_.clear();
    ImGui::SetNextWindowPos(ImVec2(43, 2), ImGuiCond_Once);
    framed_window(width_, height_, "Audio_Player", [this] { content(); });
    return problem_;
}

void player_window::content()
{
    const ImGuiWindowFlags flags = ImGuiWindowFlags_NoScrollbar;

    ImGui::TextUnformatted("  ");
    ImGui::SameLine();
    ImGui::BeginChild("Col1", ImVec2(28, 8), false, flags);
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(white));
    ImGui::TextUnformatted(R"(.------------------------.)");
    ImGui::TextUnformatted(R"(|\\////////       90 min |)");
    ImGui::TextUnformatted(R"(| \/  __  ______  __     |)");
    ImGui::TextUnformatted(R"(|    /  \|\.....|/  \    |)");
    ImGui::TextUnformatted(R"(|    \__/|/_____|\__/    |)");
    ImGui::TextUnformatted(R"(| A   ______________     |)");
    ImGui::TextUnformatted(R"(|    /              \    |)");
    ImGui::TextUnformatted(R"(|___/_._o________o_._\___|)");
    ImGui::PopStyleColor();
    ImGui::EndChild();

    ImGui::SameLine();
    ImGui::SetCursorPos(ImVec2(28, 0));
    ImGui::BeginChild("Col2", ImVec2(static_cast<float>(width_) / 2.f - 10, 9), false, flags);
    track_details();
    ImGui::EndChild();

    ImGui::SameLine();
    ImGui::SetCursorPos(ImVec2(57, 0));
    ImGui::BeginChild("Col3", ImVec2(21, 9), false, flags);
    tape_panel();
    ImGui::EndChild();

    // From here down the text is white: the STOP button, the position and the spectrum's box.
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(white));
    transport();
    spectrum_box();
    ImGui::PopStyleColor();

    // The line under the spectrum: what the player has to say (a damaged file, a device that would
    // not open).
    ImGui::SetCursorPos(ImVec2(1, 32));
    coloured(ImColor(255, 130, 130), *message_);
}

void player_window::track_details()
{
    ImGui::TextUnformatted("╒══╡Track_Details╞══════════╕");
    for (int i = 0; i < 7; ++i)
    {
        ImGui::TextUnformatted("│                           │");
    }
    ImGui::TextUnformatted("╘═══════════════════════════╛");

    const audio_info& info = player_.info();
    const std::uint64_t frames = info.frames;
    const unsigned bits = info.bits_per_sample != 0 ? info.bits_per_sample : 16; // MP3 has no word length: count it as 16
    const double megabytes = static_cast<double>(frames) * info.channels * (bits / 8) / 1048576.0;

    ImGui::SetCursorPos(ImVec2(0, 1));
    if (!player_.has_track())
    {
        // Nothing in the deck yet: the same lines, empty.
        for (const char* label : {"Audio Format: ", " Sampling Rate: ", " Bit Depth: ", " Channels: ", " Data Size: ", " Number of Samples: ", " Duration: "})
        {
            detail(label, "-");
        }
        return;
    }
    detail("Audio Format: ", info.container == "MP3" ? std::format("MP3 {} kbps", info.bitrate_kbps) : info.container + "/" + info.encoding);
    detail(" Sampling Rate: ", std::to_string(info.sample_rate));
    detail(" Bit Depth: ", info.bits_per_sample != 0 ? std::to_string(info.bits_per_sample) : std::string("-"));
    detail(" Channels: ", std::to_string(info.channels));
    detail(" Data Size: ", std::format("{:.2f} MB", megabytes));
    detail(" Number of Samples: ", std::to_string(frames));
    detail(" Duration: ", std::format("{:.2f} s", info.sample_rate ? static_cast<double>(frames) / info.sample_rate : 0.0));
}

void player_window::tape_panel()
{
    ImGui::TextUnformatted("╒══╡DSP╞═══════════╕");
    for (int i = 0; i < 7; ++i)
    {
        ImGui::TextUnformatted("│                  │");
    }
    ImGui::TextUnformatted("╘═══════╡");
    ImGui::SameLine();
    ImGui::PushStyleColor(ImGuiCol_FrameBg, static_cast<ImVec4>(ImColor(60, 60, 60)));
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(yellow));
    const bool has_tape = player_.has_profile();
    // Lit while the file plays as it is: no tape in the deck, or the tape bypassed.
    if (ImGui::RadioButton("Bypass", !has_tape || player_.bypass()) && has_tape)
    {
        player_.set_bypass(!player_.bypass());
    }
    ImGui::SameLine();
    ImGui::PopStyleColor(2);
    ImGui::TextUnformatted("╞══╛");

    // ---- which tape: its name, and a step either way through the profiles and "no tape"
    ImGui::SetCursorPos(ImVec2(1, 1));
    std::string name = has_tape ? player_.profile_name() : std::string("no tape");
    if (name.size() > 18)
    {
        name = name.substr(name.size() - 18); // the end of a long name tells the profiles apart
    }
    coloured(has_tape ? yellow : grey, name);

    ImGui::SetCursorPos(ImVec2(1, 2));
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(white));
    if (ImGui::Button(" ◀ "))
    {
        if (auto ok = shelf_.step(-1); !ok)
        {
            problem_ = ok.error();
        }
    }
    ImGui::SameLine();
    ImGui::TextUnformatted(std::format(" TAPE {}/{} ", shelf_.selected() + 1, shelf_.profiles().size()).c_str());
    ImGui::SameLine();
    if (ImGui::Button(" ▶ "))
    {
        if (auto ok = shelf_.step(+1); !ok)
        {
            problem_ = ok.error();
        }
    }
    ImGui::PopStyleColor();

    // ---- the parts of the model, each with its lamp
    struct part
    {
        const char* label;
        tape::ingredient bit;
    };
    static const part parts[4][2] = {
        {{" EQ  ", tape::ingredient::eq}, {" SAT ", tape::ingredient::saturation}},
        {{" WOW ", tape::ingredient::transport}, {" L-R ", tape::ingredient::differential}},
        {{" JIT ", tape::ingredient::jitter}, {" FLK ", tape::ingredient::flicker}},
        {{" DRP ", tape::ingredient::dropouts}, {" HISS", tape::ingredient::hiss}},
    };
    const std::uint32_t mask = player_.ingredients();
    for (int row = 0; row < 4; ++row)
    {
        for (int col = 0; col < 2; ++col)
        {
            const part& p = parts[row][col];
            const auto bit = static_cast<std::uint32_t>(p.bit);
            const bool on = (mask & bit) != 0;
            ImGui::SetCursorPos(ImVec2(static_cast<float>(1 + 9 * col), static_cast<float>(3 + row)));
            coloured(!has_tape ? ImColor(70, 70, 70) : on ? ImColor(0, 255, 0) : ImColor(255, 0, 0), "█");
            ImGui::SameLine();
            ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(has_tape ? white : grey));
            if (ImGui::Button(p.label) && has_tape)
            {
                player_.set_ingredients(mask ^ bit);
            }
            ImGui::PopStyleColor();
        }
    }

    // ---- the level on its way out, and a lamp for samples that hit full scale
    const playback::levels& levels = *levels_;
    const float elapsed = ImGui::GetIO().DeltaTime;
    const float peak = std::max(levels.peak[0], levels.peak[1]);
    const float now_db = peak > 0 ? 20.0f * std::log10(peak) : -120.0f;
    peak_db_ = std::max(now_db, peak_db_ - 20.0f * elapsed);
    if (levels.clipped != clipped_seen_)
    {
        clipped_seen_ = levels.clipped;
        clip_lamp_s_ = 2.0f;
    }
    clip_lamp_s_ = std::max(0.0f, clip_lamp_s_ - elapsed);

    ImGui::SetCursorPos(ImVec2(1, 7));
    ImGui::TextUnformatted(peak_db_ > -99.0f ? std::format("pk {:+5.1f} dB", peak_db_).c_str() : "pk   --- dB");
    if (clip_lamp_s_ > 0)
    {
        ImGui::SameLine();
        coloured(ImColor(255, 60, 60), " CLIP");
    }
}

void player_window::transport()
{
    ImGui::TextUnformatted(" ");
    ImGui::SameLine();
    const bool has_track = player_.has_track(); // without one the buttons and the slider are there but do nothing
    if (ImGui::Button(player_.playing() ? " ⏸ \n PAUSE \n" : " ▶ \n PLAY  \n") && has_track)
    {
        if (player_.playing())
        {
            player_.pause();
        }
        else if (auto ok = player_.play(); !ok)
        {
            problem_ = ok.error();
        }
    }

    ImGui::SameLine();
    ImGui::TextUnformatted(" ");
    ImGui::SameLine();
    if (ImGui::Button(" ⏹ \n STOP \n") && has_track)
    {
        player_.pause();
        player_.seek(0);
    }
    ImGui::SameLine();
    ImGui::TextUnformatted(" ");
    ImGui::SameLine();

    // The position: drag it to seek.
    const audio_info& info = player_.info();
    const auto limit = static_cast<std::uint64_t>(std::numeric_limits<int>::max());
    int position = has_track ? static_cast<int>(std::min(player_.position(), limit)) : 0;
    const int length = static_cast<int>(std::min(std::max<std::uint64_t>(has_track ? info.frames : 0, 1), limit));
    char label[32];
    std::snprintf(label, sizeof label, "\n%.0f s", has_track && info.sample_rate ? static_cast<double>(position) / info.sample_rate : 0.0);

    ImGui::PushStyleColor(ImGuiCol_FrameBg, static_cast<ImVec4>(ImColor(30, 30, 30)));
    ImGui::PushStyleColor(ImGuiCol_FrameBgHovered, static_cast<ImVec4>(ImColor(60, 60, 60)));
    ImGui::PushStyleColor(ImGuiCol_FrameBgActive, static_cast<ImVec4>(ImColor(60, 60, 60)));
    ImGui::PushStyleColor(ImGuiCol_SliderGrab, static_cast<ImVec4>(yellow));
    ImGui::SetNextItemWidth(static_cast<float>(width_ - 19));
    if (ImGui::SliderInt("", &position, 0, length, label) && has_track)
    {
        player_.seek(static_cast<std::uint64_t>(std::max(position, 0)));
    }
    ImGui::PopStyleColor(4);

    ImGui::TextUnformatted("");
}

void player_window::spectrum_box()
{
    constexpr int rows = 17;
    ImGui::TextUnformatted("╒════════════════════════════╡Frequency_Spectrum╞════════════════════════════╕");
    const ImVec2 inside = ImGui::GetCursorPos(); // the first row inside the box
    for (int i = 0; i < rows; ++i)
    {
        ImGui::TextUnformatted("│                                                                            │");
    }

    // The frequency axis. The spacing of the labels follows the display's scale: even steps in pitch
    // from 20 Hz to 20 kHz.
    const auto tick = [](const char* rule, const char* label) {
        ImGui::TextUnformatted(rule);
        ImGui::SameLine();
        ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(axis_blue));
        ImGui::SameLine();
        ImGui::TextUnformatted(label);
        ImGui::SameLine();
        ImGui::PopStyleColor();
    };
    tick("├╢", "20Hz");
    tick("╟──╢", "50");
    tick("╟───╢", "100");
    tick("╟───╢", "200");
    tick("╟──╢", "400");
    tick("╟──────╢", "1k");
    tick("╟───╢", "2k");
    tick("╟────╢", "4k");
    tick("╟────╢", "8k");
    tick("╟──╢", "13");
    tick("╟╢", "2");
    ImGui::TextUnformatted("┤");
    ImGui::TextUnformatted("╘╩════╩══╩══╩═══╩═══╩═══╩═══╩══╩═══╩══════╩══╩═══╩══╩════╩══╩════╩══╩══╩══╩╩═╛");

    // The curve, in Braille dots: two points per character cell across the box and four per row, the
    // finest a terminal can draw. The box is 76 cells wide inside, the display has 152 points.
    const ImVec2 after = ImGui::GetCursorPos();
    const std::vector<std::string> lines = braille_curve(display_.values(), rows);
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(ImColor(251, 244, 224)));
    for (int r = 0; r < rows; ++r)
    {
        ImGui::SetCursorPos(ImVec2(inside.x + 1, inside.y + static_cast<float>(r)));
        ImGui::TextUnformatted(lines[static_cast<std::size_t>(r)].c_str());
    }
    ImGui::PopStyleColor();
    ImGui::SetCursorPos(after);
}

} // namespace korre
