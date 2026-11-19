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
6. **Spectrum display. Done** (`player/spectrum.*`, `player/braille.*`): a fixed dB scale, points evenly
   spaced in pitch that match the printed axis, fed from the samples really played. Redone on 2026-11-18
   after the owner's first look: a window length per point (5 ms in the treble to a sixth of a second
   in the bass), no hold, and a curve in Braille dots (152 x 68) instead of the plot widget.
7. **Profiles in the interface. Done for the tape:** profile selection, bypass and a switch per part of
   the model, in the DSP panel and the Tape menu. **Open:** the optional HRIR stage with selectable ear
   sets (kept separate from the tape model).

## Next
- Per-track or per-profile record level in the interface (the engine takes it; the player uses the level
  the profile was fitted at).
- Gapless transition between tracks (the decoder thread can open the next file ahead of time).
- The treble-saturation stage's effect on the mids (see Open).
- HRIR stage.

Done on 2026-11-18 after the owner's first sessions with the player (their screenshots show it playing
through a real output device; that path still has no test of its own): the spectrum redone (stage 6), a level meter window (`player/meter_window.*`,
`level_meter.*`: RMS or peak reading, a sticky mark per channel), the windows' default places (queue and
selector left, player in the middle, meter right), and the player window shown from the start.

From the tape model (`analysis/FINDINGS.md`, 2026-11-19):
- All profiles but the first metal one carry their flutter lines as lines now, and the rotating parts'
  lines as pairs with phases: the recording's wobble and the playback's, which beat (`transport.lines`
  with `phase`; the engine reads it). The capstan's flutter is one number for the deck, 6 to 7 us RMS per
  pass; what looked like a depth per stretch of tape was the place in the beat. A profile carries the
  beat as it stood on the fitted song. For the player a typical tape would start anywhere in it: take
  the phases out of a profile and the engine draws them from the seed.
- Distortion is fitted per channel on the metal profiles (the left track has more). The chrome
  profiles have no flat cubic left; their treble-saturation stage alone makes 2 to 9 dB more third-order
  products than the chrome tape shows while giving the right loss of treble. It bends the waveform; the
  tape seems to follow the treble's envelope. A stage that does that is the next change to the model.
- The alignment has a second, linear stage (`analysis/align.py`), and every figure for timing and
  roughness from before 2026-11-19 is on the old basis.
- Still open: 250 Hz in the quieter passages (the emulations leave about 1 dB more than the tapes);
  the wobble between the channels at 3-12 Hz (20% low, no rule for it); the jitter table's one point per
  octave between 48 and 96 Hz.
- The owner could not tell `MB3_v2` from the tape and told `MB3` (v1) apart: `wmd6c_metalxr_v2` is the
  metal profile to keep; `wmd6c_metalxr` (v1) stays as the tests' example of a profile from before
  lines and gain noise.

## Decisions taken as defaults (say so if you want otherwise)
- Keep PortAudio and the vendored imtui / pffft / minimp3.
- Vendor a single-header JSON reader for the profiles.
- The engine lives in its own directory and never includes UI or audio-device headers.
- Each stage of this plan is one or a few commits, so the history shows what changed and why.

## Open
- The model's treble-saturation stage adds 0.1-0.15% of amplitude flicker around 1-2 kHz that the tape
  does not show (`analysis/FINDINGS.md`, 2026-11-17). A question for the model, not for the port.
- `imtui/` and `pffft/` could move under `third_party/` with the other vendored code.
