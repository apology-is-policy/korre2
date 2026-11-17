# Player rewrite plan

Goal: turn the imported korre player into a stable C++23 program that plays music through a measured
tape profile (`profiles/*.json`), keeping the patched imtui interface and its look.

## Where things stand (2026-11-17)
- The original is imported unchanged at the repo root (`docs/PROVENANCE.md`).
- Size: ~3,200 lines of own code (`main.cpp`, `src/`, `include/`), plus vendored `imtui/` (patched),
  `pffft/` and `src/decoders/minimp3*.h`. Links PortAudio, FLAC/FLAC++, ncursesw and Armadillo
  (Armadillo only for the convolver). GPL-3.0. The binary is called `kora`.
- It configures with CMake 4.1 / Apple clang 21 but does **not compile**: `include/sinks/portaudio_sink.h`
  uses `std::thread` without `#include <thread>`; the remaining errors cascade from that.
- Three `std::thread`s (PortAudio sink worker, convolver worker, convolver visualiser) and no mutex,
  atomic or condition variable anywhere: shared state is unsynchronised.
- The model the engine has to implement is `analysis/emulator.py` (v0.4). It is feed-forward and
  real-time capable; nothing needs more than a few milliseconds of look-ahead.

## Stages
0. **Baseline.** Make the import build with the smallest possible change (the missing include, whatever
   else today's compiler rejects), nothing behavioural. Record what was needed.
1. **Safety net.** Warnings on for own code, the sanitizer switches the CMake file already has
   (address, undefined, thread), and a headless smoke test (decode a file into a null sink) so that
   later steps can be checked without the terminal UI.
2. **Remove the convolver and Armadillo.** `src/elements/dsp_convolver.cpp`, its header, its uses in
   `korre.cpp` / `korre.h`, the CMake dependency. Leave one clean effect slot in the chain where the tape
   engine will sit.
3. **The tape engine as a library** (`tape/`, no UI, no PortAudio):
   - profile loader: JSON tables → filters, designed once per sample rate at load
   - stages, in the emulator's order: record gain + saturation (flat cubic, treble saturation between
     pre- and de-emphasis) → static response per channel (measured magnitude and phase: short
     partitioned convolver, or high-pass sections + short FIR) → one modulated delay line per channel
     (transport, slow L−R, fast jitter common + per channel; polyphase windowed-sinc table) →
     amplitude flicker (two short FIRs × slow noise) → noise bed + deck tones → polarity
   - streaming generators for the random processes (filtered noise; wandering oscillators for the
     capstan / motor / roller lines), seeded
   - block interface `process(in, out, frames)`, no allocation or locks inside
   - an offline tool, `korre-render in.flac --profile p.json out.flac`
   - **verification against the Python emulator:** deterministic stages (gain, saturation, static
     response) compared sample by sample with `emulator.py`; the random stages by running the C++ render
     through `align.py` + `signature.py` and comparing with the tape, exactly as the Python emulation is
     checked
4. **Threading.** Audio callback reads from a lock-free single-producer/single-consumer ring; a decoder
   thread fills it; the UI thread sees meters and spectrum through atomics or snapshots; orderly
   start-up and shutdown (joined threads, no detached workers).
5. **C++23 pass over the rest** (ownership, `std::span`, `std::expected`, ranges, `std::jthread`,
   `std::format`), behaviour unchanged, interface and look kept.
6. **Spectrum display:** correct windowing and level scaling, log-frequency bands, fast (pffft).
7. **Profiles in the interface:** choose deck / tape profile, bypass, the ingredient ladder as switches;
   later the optional HRIR stage with selectable ear sets (kept separate from the tape model).

## Decisions taken as defaults (say so if you want otherwise)
- Keep PortAudio and the vendored imtui / pffft / minimp3.
- Vendor a single-header JSON reader for the profiles.
- The engine lives in its own directory and never includes UI or audio-device headers.
- Each stage of this plan is one or a few commits, so the history shows what changed and why.

## Open
- Commits: the repo has none yet; nothing has been committed without being asked.
- The static-response stage keeps a small convolver (or fitted high-pass sections): "remove all
  convolution code" becomes "remove the old Armadillo convolver, keep a small purpose-built one".
