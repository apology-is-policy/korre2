# The tape engine

Plays audio through a measured tape profile (`profiles/*.json`), block by block, in real time.
A library with no user interface, no audio device and no file code in it: the player and the offline
tool `korre-render` both sit on top of it.

```cpp
#include "tape/engine.h"

auto profile = tape::load_profile("profiles/wmd6c_xlii_sideB.json");   // std::expected
tape::settings settings;
settings.sample_rate = 48000;
tape::engine engine(*profile, settings);        // designs the filters for this sample rate

engine.process(in, out);                         // interleaved stereo float, any number of frames
engine.set_bypass(true);                         // from any thread; faded, no click
engine.set_ingredients(tape::ingredient::eq | tape::ingredient::hiss);
```

`process()` does not allocate, lock or block. The output lags the input by `engine.delay().total`
frames (about 37 ms); a bypassed engine delays the dry signal by the same amount, so switching does
not jump in time.

## What it does to the sound

The chain, in the physical order of recording and playback. The model and every number in it come
from the measurements in `analysis/` (`emulator.py` is the reference implementation, `FINDINGS.md`
the record of how each part was found).

| stage | what | how |
|---|---|---|
| record gain | how hard the tape is driven | per channel, from the profile or `settings` |
| saturation | a faint cubic; then treble saturation, because tape is recorded with boosted treble | cubic; first-order shelf, cubic, the exact inverse shelf |
| static response | magnitude and phase per channel, including the bass roll-off's large phase rotation and the delay between the channels | one filter of a third of a second per channel, applied as a partitioned FFT convolution |
| timing | slow wobble with the transport's mechanical lines, the slow left-right difference, fast jitter (a common part and a part per channel) | one moving delay line per channel, read with a 48-tap windowed sinc |
| amplitude flicker | deeper towards the treble; a common part and a part per channel | two short symmetric filters per channel, each times a slow random gain |
| dropouts | short dips, drawn from the measured ones | random events |
| background | the recorded tape's noise per channel and the deck's faint steady tones | noise with the measured spectrum; sine generators |
| polarity | the WM-D6C chain inverts | sign |

Every part can be switched while it runs (`set_ingredients`). All random signals follow from
`settings.seed` and do not depend on which parts are switched on, so two renders that differ in one
ingredient share the same wobble, jitter, flicker and noise.

## Files

| file | what |
|---|---|
| `include/tape/profile.h`, `src/profile.cpp` | the profile as a struct; reading and checking the JSON |
| `include/tape/engine.h`, `src/engine.cpp` | the engine: the stages and their switching |
| `src/design.*` | the profile's tables turned into filters for one sample rate |
| `src/convolver.*` | uniformly partitioned convolution: a 16,000-tap filter at the cost of a few FFTs per block |
| `src/noise.*` | endless random signals with a prescribed spectrum |
| `src/fft.*`, `src/random.h` | a small double-precision FFT; a fixed random generator, so a seed means the same on every machine |

Cost: a 218 s song renders in 8 s including decoding and FLAC encoding, so the engine takes under
4% of one core at 48 kHz. Setting it up (filter design, the first noise blocks) takes about 0.1 s.
Memory: about 30 MB at 44.1 and 48 kHz and twice that at 96 kHz, mostly the noise generators' blocks.

## How it differs from the Python model, and why

`emulator.py` works on a whole track at once. Two things in it cannot be done on audio as it arrives,
so the engine defines them differently; `analysis/streamref.py` states the engine's definitions in
numpy.

1. **The static response.** The model applies the measured table exactly, with one FFT as long as
   the track. The engine uses a filter of 16,384 taps (at 44.1 and 48 kHz) with 11.6 ms before time
   zero. The table's own fine ripple, which is measurement noise, corresponds to energy seconds
   before and after time zero; a real tape chain is causal, so the part before is not physical and
   the engine leaves it out. The result differs from the whole-track response by about -28 dB in
   the 20-60 Hz band (0.3 dB), -35 dB in 60-200 Hz and below -50 dB above that.
2. **The random signals.** The model draws each for the whole track from one long FFT. The engine
   makes them in overlapping blocks (1.4 s at the audio rate, 44 s at the 187 Hz control rate of the
   slow wobble), cross-faded so that the variance stays constant. The spectrum is the table's,
   smoothed over about two bins.

## How it is checked

- `tests/test_tape.cpp` (run by `ctest`): the building blocks against straightforward reference
  computations, and the engine's guarantees: its delay, exact pass-through when everything is off
  and when bypassed, the same output however the audio is cut into blocks, reproducibility from the
  seed, click-free switching, `reset()`, all sample rates from 22.05 to 192 kHz.
- `analysis/verify_engine.py`: against the Python model, on real music.
  `korre-render --trace` writes out the control signals the engine used; the script applies the
  Python chain with those same signals and compares sample by sample.

Result on Shallow (chrome profile) and I Miss You (metal profile), 60 s each at 48 kHz:

| check | result |
|---|---|
| filter designs, engine against `streamref.py` | equal to 1e-16 (-318 dB) |
| output against the Python chain with the engine's own control signals, for nine ingredient sets | -152 dB, the resolution of the 32-bit float output |
| control signals with different ingredient sets | identical |
| wobble, jitter, flicker and noise against the profile's tables | band levels within a few percent; noise within 0.25 dB per octave from 45 Hz up (0.1 dB from 180 Hz up); mechanical lines at 1.66, 7.52 and 43.56 Hz (table: 1.65, 7.53, 43.58) |
| a full render of Shallow through `align.py` and `signature.py`, against the tape | speed deviation within 0.001% in every band; timing jitter within 0.35 us per band; response within 0.4 dB below 60 Hz and 0.1 dB above; residual within 0.4 dB per octave |

The last row is the same test the Python emulation has to pass before a blind pair is made from it.
One number in it is off, and it is the model's, not the port's: amplitude flicker around 1-2 kHz
reads 0.2-0.5% where the tape has 0.1-0.4%. A Python render with the same profile reads the same
(`FINDINGS.md`, 2026-11-17): it comes from the treble-saturation stage added in v0.4.
