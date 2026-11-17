// kora: the terminal player.

#include <clocale>
#include <cstdio>
#include <filesystem>
#include <string>
#include <string_view>

#include "app.h"

namespace
{

const char* const usage = R"(usage: kora [options] [file or playlist ...]

Files (WAV, FLAC, MP3) and playlists (.txt, one path per line) are put in the queue.

  --play              start playing the first track at once
  --profile NAME      the tape to play through: a file in the profiles folder (with or without
                      .json), a path to a profile, or "none"
  --profiles DIR      the folder of tape profiles (default: ./profiles, or the one next to the program)
  --dir DIR           the folder the file selector opens in (default: the current folder)
  --device NAME       the output device: its number, or part of its name (default: the system's);
                      "none" plays to nowhere, for trying the program without sound
  --list-devices      print the output devices and exit
  -h, --help          this text

In the program: the mouse works everywhere; q quits.
)";

/// The profiles folder when none is given: ./profiles, or the repository's when the program runs
/// from its build folder, or the installed one.
std::filesystem::path find_profiles(const char* program)
{
    std::error_code ec;
    std::vector<std::filesystem::path> candidates{"profiles"};
    const std::filesystem::path exe = std::filesystem::weakly_canonical(program, ec);
    if (!ec && exe.has_parent_path())
    {
        candidates.push_back(exe.parent_path() / ".." / ".." / "profiles"); // build/bin/kora
        candidates.push_back(exe.parent_path() / ".." / "share" / "korre" / "profiles");
    }
    for (const auto& c : candidates)
    {
        if (std::filesystem::is_directory(c, ec))
        {
            return std::filesystem::weakly_canonical(c, ec);
        }
    }
    return "profiles";
}

} // namespace

int main(int argc, char* argv[])
{
    korre::options opt;
    bool list_devices = false;

    for (int i = 1; i < argc; ++i)
    {
        const std::string_view arg = argv[i];
        const auto value = [&]() -> std::string {
            if (i + 1 >= argc)
            {
                std::fprintf(stderr, "kora: missing value after %s\n", argv[i]);
                std::exit(2);
            }
            return argv[++i];
        };
        if (arg == "-h" || arg == "--help")
        {
            std::fputs(usage, stdout);
            return 0;
        }
        else if (arg == "--play")
        {
            opt.play = true;
        }
        else if (arg == "--profile")
        {
            opt.profile = value();
        }
        else if (arg == "--profiles")
        {
            opt.profiles = value();
        }
        else if (arg == "--dir")
        {
            opt.workspace = value();
        }
        else if (arg == "--device")
        {
            opt.device = value();
        }
        else if (arg == "--list-devices")
        {
            list_devices = true;
        }
        else if (arg.starts_with("--"))
        {
            std::fprintf(stderr, "kora: unknown option %s\n\n%s", argv[i], usage);
            return 2;
        }
        else
        {
            opt.files.emplace_back(arg);
        }
    }

    if (list_devices)
    {
        for (const auto& d : korre::app::list_devices())
        {
            std::printf("%3d  %s  (%.0f Hz)\n", d.index, d.name.c_str(), d.default_sample_rate);
        }
        return 0;
    }

    std::error_code ec;
    if (opt.workspace.empty())
    {
        opt.workspace = std::filesystem::current_path(ec);
    }
    if (opt.profiles.empty())
    {
        opt.profiles = find_profiles(argv[0]);
    }
    for (auto& file : opt.files)
    {
        file = std::filesystem::absolute(file, ec);
    }

    std::setlocale(LC_ALL, ""); // the box-drawing characters need the terminal's UTF-8 locale
    korre::app application(std::move(opt));
    return application.run();
}
