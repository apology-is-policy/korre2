# Player rewrite plan

Goal: turn the imported korre player into a stable C++23 program that plays music through a measured
tape profile (`profiles/*.json`), keeping the patched imtui interface and its look.

## Where things stand (2026-11-17)
- Stages 0-3 are done: the import builds, the build system and the tests are in place, the convolver and
  Armadillo are gone, and the tape engine exists as a library with an offline tool, checked against the
  Python model.
- The player itself (`main.cpp`, `src/`, `include/`) still runs on its original audio path: a chain of
  `sampler` objects pulled one sample at a time from the audio callback, global variables for the stream
  state, the whole track decoded into memory first, and no synchronisation between its threads. It does
  not use `audio/` or `tape/` yet. That is stage 4.

Layout:

| directory | what |
|---|---|
| `audio/` | reading and writing audio files: streaming WAV / FLAC / MP3 readers, WAV / FLAC writers |
| `tape/` | the tape engine ([README](../tape/README.md)) |
| `tools/` | `korre-render`: a file through a profile, offline |
| `tests/` | `ctest`; fixtures made by ffmpeg |
| `profiles/` | fitted tape profiles (JSON) |
| `analysis/` | the measurement toolkit and the reference model |
| `main.cpp`, `src/`, `include/`, `imtui/`, `pffft/` | the imported player |
| `third_party/` | minimp3, nlohmann/json |

Build and test:

```
cmake -S . -B build && cmake --build build && ctest --test-dir build
cmake -S . -B build-asan -DCMAKE_BUILD_TYPE=Debug -DKORRE_SANITIZE=address && cmake --build build-asan && ctest --test-dir build-asan
```

## Stages
0. **Baseline. Done.** Four include lines; `build/bin/kora` builds on a current toolchain.
1. **Safety net. Done.** One top-level CMake file; warnings on our own code, a stricter set for new code;
   `KORRE_SANITIZE=address|thread`; tests under CTest. The headless test covers the new decoders
   (`tests/test_audio.cpp`, against files written by ffmpeg) rather than the old ones, which stage 4
   removes. The player links Homebrew's ncursesw: the hand-built copy in `/usr/local` only found a
   terminal description inside the owner's own terminal.
2. **Remove the convolver and Armadillo. Done.** The DSP panel keeps its frame and Bypass button as the
   slot for the tape controls.
3. **The tape engine as a library. Done** (`tape/`, `tools/korre-render`). Verification in
   `tape/README.md`: the port is exact to the resolution of its float output (-152 dB against the Python
   chain run with the engine's own control signals), and a full render measures like the tape.
   Where the engine has to differ from the whole-track model (a short filter for the static response,
   random signals made in blocks) is written down there too.
4. **Playback core and threading.** A `playback` library between the interface and the audio device:
   - a decoder thread reads the file in pieces (`audio/`), runs the tape engine, and fills a lock-free
     single-producer/single-consumer queue of small chunks; each chunk carries its position in the track
     and an epoch number, so a seek is one atomic increment and stale audio is dropped by the callback
   - the audio callback only copies from the queue: no decoding, no FFT, no allocation, no locks
   - the interface reads position, level and the played samples (for the spectrum) through atomics and a
     second lock-free queue; orderly start-up and shutdown, joined threads
   - the audio device behind a small interface, so the whole path can be tested without sound
   - then delete `sampler`, `sink`, `wave`, `wave_source`, `meter`, the old decoders and the `PA_*` globals
5. **C++23 pass over the interface code** (ownership, `std::span`, `std::expected`, `std::format`),
   behaviour unchanged, interface and look kept. Command-line arguments (files to queue, `--profile`,
   `--device`), which also make the player testable in a detached terminal.
6. **Spectrum display:** correct windowing and level scaling (a dB scale instead of normalising each
   frame to its own peak), log-frequency bands that match the printed axis, fed from the played samples.
7. **Profiles in the interface:** choose deck / tape profile, bypass, the ingredient ladder as switches;
   later the optional HRIR stage with selectable ear sets (kept separate from the tape model).

## Decisions taken as defaults (say so if you want otherwise)
- Keep PortAudio and the vendored imtui / pffft / minimp3.
- Vendor a single-header JSON reader for the profiles.
- The engine lives in its own directory and never includes UI or audio-device headers.
- Each stage of this plan is one or a few commits, so the history shows what changed and why.

## Open
- Level in the player. A real capture sits about 7 dB below its source (the record gain), so with the
  engine on the player has to make that up to keep bypass comparisons fair, and that can push peaks over
  full scale. Plan: make-up gain equal to the record gain, a little fixed headroom on both paths, and a
  clip indicator.
- The model's treble-saturation stage adds 0.1-0.15% of amplitude flicker around 1-2 kHz that the tape
  does not show (`analysis/FINDINGS.md`, 2026-11-17). A question for the model, not for the port.
