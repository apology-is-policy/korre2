# Player rewrite plan

Goal: turn the imported korre player into a stable C++23 program that plays music through a measured
tape profile (`profiles/*.json`), keeping the patched imtui interface and its look.

## Where things stand (2026-11-17)
- Stages 0-6 are done and stage 7 is done as far as the tape goes: `kora` is the original interface on
  a new playback core, with the tape engine in the path and its controls in the DSP panel.
- Nothing of the original audio path is left (`sampler`, `sink`, `wave`, `wave_source`, `meter`, the old
  decoders, the `PA_*` globals). The interface code was rewritten file by file into `player/`, keeping
  the layout, the strings and the colours.
- **Not yet run with sound.** Everything is tested without a sound card (the audio device sits behind
  an interface), and the interface was driven through a scripted session with `--device none`, also
  under the address and the thread sanitizer. Opening a real output device could not be tried from the
  environment the rewrite was done in: CoreAudio does not answer there. `playback/src/portaudio_output.cpp`
  (about 110 lines) is the one piece no test reaches, and the first thing to check by ear.

Layout:

| directory | what |
|---|---|
| `audio/` | reading and writing audio files: streaming WAV / FLAC / MP3 readers, WAV / FLAC writers |
| `tape/` | the tape engine ([README](../tape/README.md)) |
| `playback/` | decoder thread, engine and a lock-free queue to the audio callback ([README](../playback/README.md)) |
| `player/` | `kora`, the terminal interface ([README](../player/README.md)) |
| `tools/` | `korre-render`: a file through a profile, offline |
| `tests/` | `ctest`; fixtures made by ffmpeg |
| `profiles/` | fitted tape profiles (JSON) |
| `analysis/` | the measurement toolkit and the reference model |
| `imtui/`, `pffft/`, `third_party/` | vendored: imtui with Dear ImGui (patched), pffft, minimp3, nlohmann/json |

Build and test:

```
cmake -S . -B build && cmake --build build && ctest --test-dir build
cmake -S . -B build-asan -DCMAKE_BUILD_TYPE=Debug -DKORRE_SANITIZE=address && cmake --build build-asan && ctest --test-dir build-asan
cmake -S . -B build-tsan -DCMAKE_BUILD_TYPE=Debug -DKORRE_SANITIZE=thread && cmake --build build-tsan && ctest --test-dir build-tsan
```

## Stages
0. **Baseline. Done.** Four include lines; the import builds on a current toolchain.
1. **Safety net. Done.** One top-level CMake file; warnings on our own code; `KORRE_SANITIZE=address|thread`;
   tests under CTest. The player links Homebrew's ncursesw: the hand-built copy in `/usr/local` only
   found a terminal description inside the owner's own terminal.
2. **Remove the convolver and Armadillo. Done.**
3. **The tape engine as a library. Done** (`tape/`, `tools/korre-render`). The port is exact to the
   resolution of its float output against the Python chain, and a full render measures like the tape
   (`tape/README.md`).
4. **Playback core and threading. Done** (`playback/`). The audio callback only copies from a lock-free
   queue; a decoder thread reads the file in pieces and runs the engine; a seek is an atomic increment.
   One flaw found on the way and fixed with a test: the decoder kept its lock while it had work, which
   could keep the interface waiting.
5. **C++23 pass over the interface. Done** (`player/`): `std::expected` for everything that can fail, no
   raw `new`, no globals, no exceptions escaping to the top. Command-line arguments.
6. **Spectrum display. Done** (`player/spectrum.*`): Hann window, a fixed dB scale, bands evenly spaced in
   pitch that match the printed axis, fed from the samples really played.
7. **Profiles in the interface. Done for the tape:** profile selection, bypass and a switch per part of
   the model, in the DSP panel and the Tape menu. **Open:** the optional HRIR stage with selectable ear
   sets (kept separate from the tape model).

## Next
- Listen. Real output through PortAudio, then tape against bypass on a few songs.
- Per-track or per-profile record level in the interface (the engine takes it; the player uses the level
  the profile was fitted at).
- Gapless transition between tracks (the decoder thread can open the next file ahead of time).
- The treble-saturation stage's effect on the mids (see Open).
- HRIR stage.

## Decisions taken as defaults (say so if you want otherwise)
- Keep PortAudio and the vendored imtui / pffft / minimp3.
- Vendor a single-header JSON reader for the profiles.
- The engine lives in its own directory and never includes UI or audio-device headers.
- Each stage of this plan is one or a few commits, so the history shows what changed and why.

## Open
- The model's treble-saturation stage adds 0.1-0.15% of amplitude flicker around 1-2 kHz that the tape
  does not show (`analysis/FINDINGS.md`, 2026-11-17). A question for the model, not for the port.
- `imtui/` and `pffft/` could move under `third_party/` with the other vendored code.
