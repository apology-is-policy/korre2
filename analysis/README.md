# Tape analysis

Measurement scripts for the WM-D6C tape capture: what the tape chain does to a
digital source, measured from recordings rather than guessed. Results so far are in
[FINDINGS.md](FINDINGS.md).

## Setup

Needs Python 3.11+, `ffmpeg`/`ffprobe` on the PATH (Homebrew `ffmpeg`), and (numpy, scipy, matplotlib):

```
python3 -m venv .venv            # in the repo root
.venv/bin/pip install -r analysis/requirements.txt
```

Run scripts from this folder: `../.venv/bin/python <script>.py ...`

## Data

Audio never goes into git. `data/` (repo root, gitignored) holds symlinks:

| path | what |
|---|---|
| `data/side_a.flac`, `data/side_b.flac` | the tape capture, 24-bit/192 kHz |
| `data/sources/<track>.flac` | the digital source of a song, e.g. `sources/B3.flac` |
| `data/metal-tape.flac` | the metal tape, both sides in one file, 24-bit/96 kHz (track ids `MA1`…`MB7`) |
| `data/sources/metal_source.flac` | one Tidal capture of the metal tape's whole playlist; `splitsource.py` cuts it into `sources/MA1.flac`… |

Set `KORRE2_DATA` to use a different folder. Track IDs, song boundaries and titles are
in `tracks.py`.

## Scripts

| script | what it does |
|---|---|
| `splitsource.py` | cuts the metal tape's long Tidal capture into one 24/48 source file per song (boundaries in `tracks.py`) |
| `flacscan.py <file>` | maps which byte ranges of a (damaged) FLAC still hold valid frames |
| `levels.py` | per-track peak, RMS, L-R balance and full-scale (clipped) samples |
| `noise.py [--track B3]` | leader vs blank-tape noise, spectral lines, how far a song rises above the hiss |
| `channels.py [--detail B3]` | inter-channel delay and L/R level balance, no source needed |
| `sourcecheck.py <file>` | sanity check of a candidate source (e.g. flags vinyl needle drops) |
| `align.py <track>` | finds the song in the capture, corrects polarity, tracks speed / wow / flutter (in 200 Hz–8 kHz: the chain rotates the bass phase), warps the tape onto the source timeline -> `out/<track>_aligned.npz` |
| `measure.py <track>` | frequency response, coherence, per-channel delay, residual vs level, compression |
| `residual.py <track>` | splits the residual into gain wobble, timing wobble and the rest; timing-wobble spectrum |
| `investigate.py <tracks...>` | hypothesis tests with null comparisons: common vs differential timing, speed vs loudness, treble gain memory and cross-band coupling, harmonic distortion fit, what's left, treble flicker, dropouts |
| `stereo.py <tracks...>` | inter-channel coherence and phase per octave, source vs tape |
| `dynamics.py <tracks...>` | distortion vs level (interleaved-second cross-validation), noise floor after sounds, demodulated modulation vs source level |
| `leaks.py <tracks...>` | signal leaking in from elsewhere: channel crosstalk (2-input fit), print-through (long-lag correlation), the residual below 700 Hz; run it on the emulation too, which is the null |
| `spectro.py <track>` | spectrograms of tape and emulation side by side plus difference panels for L+R and L−R -> `out/listening/<track>/spectrograms.png`; `--a/--b/--out` for any two files |
| `eqplot.py <track>` | static response of tape and emulation against the source, overlaid: magnitude, difference, phase, and loud-minus-quiet passages -> `out/listening/<track>/response.png` |
| `diagset.py <track>` | diagnostic blind pairs (four bands, mono, L−R) from a listening set, to locate by ear a difference the measurements don't show |
| `coupling.py <tracks...>` | is the modulation driven by the music? coherence of each octave's AM and timing with the bass waveform, the level and the band's own level; attack/decay asymmetry |
| `peaks.py <tracks...>` | gain on the linear prediction by amplitude class: does the deck round off peaks? |
| `bassdist.py <tracks...>` | distortion driven by the bass alone, in the low band |
| `levelsplit.py <tracks...>` | is the fast amplitude modulation of a band multiplicative or added? AM at 96-384 Hz rates by the band's own level, per octave and channel (flat: it scales with the signal; halving per 6 dB: added noise) |
| `crossband.py <tracks...>` | is a channel's amplitude modulation one gain for all frequencies or separate per band? coherence of the demodulated AM (and timing) between octave bands, per modulation rate |
| `satfit.py <track> [--apply P] [--check T2]` | fits the treble saturation stage (cubic on the pre-emphasised signal) from the treble gain by level, tape minus emulation; `--check` predicts another song |
| `modstats.py` | per-octave modulation estimators: short-window gain/timing fits and complex demodulation (library) |
| `signature.py <track> [<track>emu]` | the measurement signature calibration matches: speed deviation, demodulated timing and AM spectra per octave with L/R coherence, residual level, static magnitude and phase; with two ids, a side-by-side comparison |
| `fitprofile.py` | per-song measurements (static response with phase, transport and differential wobble, dropouts, hiss) used by `calibrate.py --init` |
| `calibrate.py --track B3 --name N [--init] --iters K` | fits an emulator profile by analysis-by-synthesis (render → align → signature → correct) -> `profiles/N.json`; `--only transport,jitter` adapts just the wobble depth of an existing profile to one song; `--engine` renders with the C++ engine (ten times faster); `--gain-noise` adds the per-channel gain noise to a profile that has none; `--refresh-noise`, `--tones song\|side` (a tone must also be present in the recorded silences) |
| `emulator.py` | the reference tape model, v0.5 (offline; the C++ engine in `../tape/` is its streaming form): measured magnitude+phase per channel, transport and differential wobble, fast jitter (common + per channel), amplitude flicker per octave, dropouts, hiss, saturation |
| `render.py <track> --profile P` | listening set: ingredient ladder + real tape + blind pair -> `out/listening/<track>/` (`--folder` for another name, `--engine` to render with the C++ engine, `--record-gain L R` for a song the profile was not fitted on); also `--source/--out` for any file; registers `<track>emu` so the pipeline can measure the render |
| `streamref.py` | the C++ engine's own definitions in numpy: its two filter designs and the chain applied with given control signals (library for `verify_engine.py`) |
| `verify_engine.py <track> --profile P` | checks the C++ tape engine (`../tape/`, through `korre-render --trace`) against the model: filter designs, output sample by sample with the engine's own wobble/jitter/noise, the random signals against the profile's tables, and how far the engine's short response filter is from the whole-track one; `--register <id>` renders the whole song with the engine so `align.py` and `signature.py` can measure it against the tape |
| `testsignal.py [--check]` | generates the test-tape signal + manifest (`out/testtape_v2.*`); protocol in [TESTTAPE.md](TESTTAPE.md) |

`measure.py`, `residual.py`, `investigate.py`, `stereo.py`, `dynamics.py` and `signature.py` need `align.py` to have run for that track. Outputs and
caches go to `out/` (gitignored).

## Conventions

- Levels are dBFS the way ffmpeg's `astats` reports them: 10·log10(mean square), so a
  full-scale sine reads -3 dBFS.
- Inter-channel delays: microseconds, positive = left later than right.
- "Coherence" is the share of the tape output explained by a linear filter of the
  source; 1 - coherence is what any impulse response would miss.
- The tape's background noise is taken from the silent gaps between songs (recorded with
  silence going in), not from the blank leader, which is 3-5 dB quieter in the mids.
- When a test finds something on the tape, run the emulation through the same script: it
  contains no effect the model lacks, so it shows what the estimator invents by itself.
