# Korre

Korre is a console audio player for macOS that plays music through a measured model of a tape deck:
a Sony WM-D6C and the cassettes recorded on it. It grew out of the original
[korre](https://github.com/apology-is-policy/korre) player (demo of the original interface:
https://github.com/BoosterOfOld/korre/assets/52963062/1f04e0a6-ac47-4655-a71f-26d2df28bef3).

Three parts live in this repository:

| part | where | state |
|---|---|---|
| **The measurements.** What the deck and each tape do to a digital source, measured from captures: response and phase, wow and flutter, fast timing jitter, amplitude flicker, noise, saturation. The result is a profile per deck and tape. | [`analysis/`](analysis/README.md), `profiles/` | working; the log is [`analysis/FINDINGS.md`](analysis/FINDINGS.md) |
| **The tape engine.** A C++ library that plays audio through a profile in real time, and `korre-render`, which does it to a file. | [`tape/`](tape/README.md), `tools/` | working, checked against the measurements |
| **The player.** The terminal interface, queue and playback. | `main.cpp`, `src/`, `include/` | the original player, being rewritten ([plan](docs/REWRITE_PLAN.md)); it does not use the engine yet |

## Build

Needs CMake 3.20+, a C++23 compiler (tested with Apple clang 21), and from Homebrew:

```
brew install flac portaudio ncurses
```

```
cmake -S . -B build
cmake --build build
ctest --test-dir build        # the tests
```

`-DKORRE_BUILD_PLAYER=OFF` builds only the libraries, `korre-render` and the tests (no PortAudio or
ncurses needed). `-DKORRE_SANITIZE=address` or `=thread` gives a sanitizer build; use a separate build
directory for it.

## Play a file through a tape

```
build/bin/korre-render song.flac song_on_tape.flac --profile profiles/wmd6c_xlii_sideB.json
```

| profile | deck and tape |
|---|---|
| `wmd6c_xlii_sideB.json` | WM-D6C, chrome (type II) cassette, side B; captured from the line output |
| `wmd6c_xlii_sideA.json` | the same cassette, side A |
| `wmd6c_metalxr.json` | WM-D6C, Sony Metal XR; captured from the headphone output into headphones |

`korre-render --help` lists the options: the random seed, which parts of the model to apply, how hard
the tape is driven, output level and format. The output has the level of a real capture, which sits
about 7 dB below the source.

## The player

```
build/bin/kora
```

Plays WAV (16 and 24 bit), FLAC and MP3 files and plain-text playlists (one path per line) through
PortAudio, with a play queue, shuffle, output device selection and a spectrum display.

## Third-party code

In the repository: [imtui](https://github.com/ggerganov/imtui) with Dear ImGui (patched for UTF-8
box-drawing characters), [pffft](https://bitbucket.org/jpommier/pffft/), [minimp3](https://github.com/lieff/minimp3)
and [nlohmann/json](https://github.com/nlohmann/json). Linked: [FLAC](https://github.com/xiph/flac),
[PortAudio](https://www.portaudio.com), ncurses.

Licence: GPL-3.0 (`LICENSE`). Where the player's code came from: [`docs/PROVENANCE.md`](docs/PROVENANCE.md).
