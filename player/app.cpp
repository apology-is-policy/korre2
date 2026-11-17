#include "app.h"

#include <algorithm>
#include <format>

#include "imtui/imtui-impl-ncurses.h"
#include "imtui/imtui.h"

namespace korre
{

namespace
{

std::unique_ptr<audio_output> make_output(const options& opt)
{
    if (opt.device && *opt.device == "none")
    {
        return std::make_unique<silent_output>(); // plays to nowhere, at the real pace
    }
    return std::make_unique<portaudio_output>();
}

} // namespace

app::app(options opt)
    : options_(std::move(opt)), output_(make_output(options_)), sound_card_(dynamic_cast<portaudio_output*>(output_.get())),
      player_(*output_), shelf_(player_, options_.profiles), queue_window_(queue_), file_window_(options_.workspace),
      player_window_(player_, spectrum_, shelf_)
{
    if (sound_card_)
    {
        devices_ = sound_card_->devices();
    }
    if (options_.device && sound_card_)
    {
        // A number is PortAudio's device index; anything else is looked for in the device names.
        const std::string& wanted = *options_.device;
        const bool is_number = !wanted.empty() && std::ranges::all_of(wanted, [](unsigned char c) { return std::isdigit(c) != 0; });
        const auto it = std::ranges::find_if(devices_, [&](const output_device& d) {
            return is_number ? d.index == std::stoi(wanted) : d.name.find(wanted) != std::string::npos;
        });
        if (it != devices_.end())
        {
            sound_card_->select(it->index);
        }
        else
        {
            say("no output device matches \"" + wanted + "\": using the default", true);
        }
    }
    if (options_.profile)
    {
        if (auto ok = shelf_.select(*options_.profile); !ok)
        {
            say(ok.error(), true);
        }
    }
    for (const auto& file : options_.files)
    {
        queue_.add(file);
    }
    if (queue_.current())
    {
        load_current(options_.play);
    }
}

app::~app() = default;

std::vector<output_device> app::list_devices()
{
    portaudio_output output;
    return output.devices();
}

int app::run()
{
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGui::GetIO().IniFilename = nullptr; // no settings file left in whatever folder the program runs in
    screen_ = ImTui_ImplNcurses_Init(true);
    ImTui_ImplText_Init();

    while (!quit_)
    {
        ImTui_ImplNcurses_NewFrame();
        ImTui_ImplText_NewFrame();
        ImGui::NewFrame();

        frame();

        ImGui::Render();
        ImTui_ImplText_RenderDrawData(ImGui::GetDrawData(), screen_);
        ImTui_ImplNcurses_DrawScreen();

        after_frame();
    }

    player_.unload();
    ImTui_ImplText_Shutdown();
    ImTui_ImplNcurses_Shutdown();
    ImGui::DestroyContext();
    return 0;
}

void app::frame()
{
    menu_bar();

    if (auto chosen = file_window_.draw())
    {
        enqueue(*chosen);
    }

    switch (queue_window_.draw())
    {
    case queue_action::play_current:
        load_current(true);
        break;
    case queue_action::unload:
        unload();
        break;
    case queue_action::none:
        break;
    }

    if (player_.has_track())
    {
        if (std::string problem = player_window_.draw(message_); !problem.empty())
        {
            say(std::move(problem), true);
        }
    }

    // 'q' quits, unless a text field has the keyboard.
    if (!ImGui::GetIO().WantTextInput && ImGui::IsKeyPressed('q', false))
    {
        quit_ = true;
    }
}

void app::after_frame()
{
    // The samples played since the last frame go to the spectrum display.
    float played[4096];
    const auto elapsed = static_cast<double>(ImGui::GetIO().DeltaTime);

    message_age_s_ += elapsed;
    if (!message_.empty() && message_age_s_ > 10.0)
    {
        message_.clear();
    }
    bool any = false;
    while (const std::size_t n = player_.read_played(played))
    {
        spectrum_.feed(std::span<const float>(played, n));
        any = true;
    }
    if (player_.playing() || any)
    {
        spectrum_.update(elapsed);
    }
    else
    {
        spectrum_.decay(elapsed);
    }

    if (player_.take_finished())
    {
        if (queue_.finished())
        {
            load_current(true);
        }
        else
        {
            unload();
        }
    }

    // A file that decodes with trouble says so once.
    if (player_.has_track() && queue_.current() && warned_for_ != queue_.current()->string())
    {
        if (std::string warning = player_.warning(); !warning.empty())
        {
            warned_for_ = queue_.current()->string();
            say(queue_.current()->filename().string() + ": " + warning, true);
        }
    }
}

void app::menu_bar()
{
    if (!ImGui::BeginMainMenuBar())
    {
        return;
    }
    ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(ImColor::HSV(1.f / 7.0f, 0.9f, 0.9f)));
    ImGui::TextUnformatted("Korre ");
    ImGui::PopStyleColor();
    ImGui::SameLine();

    if (ImGui::BeginMenu("File "))
    {
        if (ImGui::MenuItem("Exit  "))
        {
            quit_ = true;
        }
        ImGui::EndMenu();
    }

    if (ImGui::BeginMenu("Tape "))
    {
        if (ImGui::MenuItem("No Tape", nullptr, shelf_.selected() < 0))
        {
            (void)shelf_.select(-1);
        }
        const auto& profiles = shelf_.profiles();
        for (std::size_t i = 0; i < profiles.size(); ++i)
        {
            if (ImGui::MenuItem(profiles[i].stem().string().c_str(), nullptr, shelf_.selected() == static_cast<int>(i)))
            {
                if (auto ok = shelf_.select(static_cast<int>(i)); !ok)
                {
                    say(ok.error(), true);
                }
            }
        }
        if (ImGui::MenuItem("Refresh Tape List"))
        {
            shelf_.rescan();
        }
        ImGui::EndMenu();
    }

    if (sound_card_ && ImGui::BeginMenu("Output Device "))
    {
        if (ImGui::MenuItem("Refresh Device List"))
        {
            // PortAudio can only look for devices while nothing is playing through it.
            const bool was_playing = player_.playing();
            player_.pause();
            sound_card_->close();
            devices_ = sound_card_->devices();
            if (was_playing)
            {
                if (auto ok = player_.play(); !ok)
                {
                    say(ok.error(), true);
                }
            }
        }
        if (ImGui::BeginMenu("Devices           >"))
        {
            if (ImGui::MenuItem(sound_card_->selected() < 0 ? "Use Default Device (selected)" : "Use Default Device"))
            {
                choose_device(-1);
            }
            for (const auto& d : devices_)
            {
                const std::string label = std::format("Device {}: {} at {}Hz{}", d.index, d.name, static_cast<int>(d.default_sample_rate),
                                                      d.index == sound_card_->selected() ? " (selected)" : "");
                if (ImGui::MenuItem(label.c_str()))
                {
                    choose_device(d.index);
                }
            }
            ImGui::EndMenu();
        }
        ImGui::EndMenu();
    }

    if (!message_.empty())
    {
        ImGui::SameLine();
        ImGui::PushStyleColor(ImGuiCol_Text, static_cast<ImVec4>(message_is_error_ ? ImColor(255, 130, 130) : ImColor(179, 179, 179)));
        ImGui::TextUnformatted(("  " + message_).c_str());
        ImGui::PopStyleColor();
    }
    ImGui::EndMainMenuBar();
}

void app::choose_device(int index)
{
    sound_card_->select(index);
    if (auto ok = player_.restart_output(); !ok)
    {
        say(ok.error(), true);
    }
}

void app::enqueue(const std::filesystem::path& path)
{
    const bool was_empty = queue_.upcoming().empty();
    if (queue_.add(path) == 0)
    {
        say(path.filename().string() + ": the playlist is empty", true);
    }
    if (was_empty && queue_.current())
    {
        load_current(false);
    }
}

void app::load_current(bool then_play)
{
    while (const std::filesystem::path* path = queue_.current())
    {
        double gain = 1.0;
        std::expected<void, std::string> loaded;
        if (file_window_.normalize())
        {
            // "Normalize track to 0dB": find the loudest sample first.
            if (const auto peak = measure_peak(*path); !peak)
            {
                loaded = std::unexpected(peak.error());
            }
            else if (*peak > 0)
            {
                gain = 1.0 / static_cast<double>(*peak);
            }
        }
        if (loaded)
        {
            loaded = player_.load(*path, gain);
        }
        if (loaded)
        {
            spectrum_.set_sample_rate(player_.info().sample_rate);
            if (then_play)
            {
                if (auto ok = player_.play(); !ok)
                {
                    say(ok.error(), true);
                }
            }
            return;
        }
        say(loaded.error(), true);
        queue_.next(); // skip a file that will not open
    }
    unload();
}

void app::unload() { player_.unload(); }

void app::say(std::string message, bool is_error)
{
    message_ = std::move(message);
    message_is_error_ = is_error;
    message_age_s_ = 0;
}

} // namespace korre
