# Findings

Capture: "You Don't Get to See the Tears" mixtape (Dec 2023). Tidal "Master" stream →
Yamaha A-S801 DAC + analog stage (headphone out) → Sony WM-D6C, Maxell XLII 90 (Type II),
**Dolby NR off** → WM-D6C line out → Realtek ALC1220 line in, 24-bit/192 kHz.

## Owner's listening observations (not measured yet)
- The "dynamic distortion" changes with **signal loudness**.
- The WM-D6C sound depends strongly on the **batteries** (4× AA). Best: fresh standard Duracell
  alkalines. Other alkalines (Varta, Energizer) are audibly worse; NiMH rechargeables
  (4 × 1.2 V = 4.8 V instead of ~6 V) are the worst.
- Listening straight off the Walkman's headphone out (DT 770 Pro 32 Ω) gives the full effect.

## 2026-11-14/15: first pass

### The capture files (`flacscan.py`, `levels.py`)
- The copies on the Mac are damaged: valid audio only up to **A 28:38** and **B 27:08**.
  After that the files hold leftover disk blocks from unrelated files (don't share them).
  Intact originals are on the Linux desktop.
- 12 songs survive without clipping (11 complete + B7, which is cut off). A1 and A7 touch
  full scale (2 and 4 samples, left channel).
- Above ~20 kHz there is only noise, so 48–96 kHz is enough for analysis.

### Noise (`noise.py`)
- Tape hiss **-63.4 dBFS** (20 Hz–20 kHz), rising toward the treble, independent in each
  channel. The leader section (no tape) is far quieter, so the hiss is all tape.
- Faint steady lines at 1084 Hz (-84 dBFS) and 34.7 kHz (-80 dBFS), probably motor or
  bias leakage. Inaudible.

### Left/right, no source needed (`channels.py`, 12 songs)
- The left channel is **later** in 12/12 songs: side A ~10–12 µs, side B
  8 → 30 → 31 → 33 → 25 → 24 → 14 µs (B1..B7). The offset is similar at low and high
  frequencies (a real time shift) and drifts along the tape.
- The left channel is **louder** in 12/12: ~+1 dB overall, rising to +1.6 dB at 8 kHz
  and +2.75 dB at 16 kHz.

### Shallow (B3) against its source (`align.py`, `measure.py`, `residual.py`)
Source: Supraphon retail download, 16-bit/44.1 kHz (plenty for this; tape noise is
~35 dB above 16-bit's floor). Assumed to be the same master Tidal served in 2023.

**Polarity:** inverted relative to this source file. *(Corrected 2026-11-16: it differs per
song/master, see below; not a confirmed property of the chain.)*

**Speed and wow/flutter** (tracked up to ~15 Hz):
- Playback vs recording speed within 0.013% (same machine both ways).
- Wow 0.018% RMS (0.3–4 Hz), flutter 0.014% RMS (4–20 Hz), unweighted.
- Periodic components at 1.64 / 3.32 / 4.96 Hz (one rotating part, e.g. a ~9 mm pinch
  roller) and 7.5 Hz (e.g. a ~2 mm capstan). **Caveat:** Shallow's tempo is ~96 BPM ≈
  1.6 Hz, so the 1.64 Hz series needs confirming on a second song. *(Confirmed 2026-11-16:
  present in songs at 76, 56 and 136 BPM.)*

**Channels, now confirmed against the source:** left is +0.95 dB louder at 1 kHz and
**31.8 µs later** than the right.

**Frequency response**, re 1 kHz, power-only estimate (the phase-based H1 estimate is
dragged down in the treble by residual timing jitter):

| | 31 Hz | 50 Hz | 100 Hz–1 kHz | 2 kHz | 4 kHz | 6.4 kHz | 10 kHz | 12.8 kHz | 16 kHz |
|---|---|---|---|---|---|---|---|---|---|
| L | -3.5 | -1.2 | -0.3..0 | +0.6 | +1.2 | +1.3 | +0.7 | +0.1 | -3.2 |
| R | -2.7 | -1.4 | -0.2..0 | +0.4 | +0.6 | +0.2 | -1.4 | -2.9 | -6.2 |

So: flat, with a gentle presence lift; the right channel loses treble earlier.

**How much a linear filter explains** (coherence): 99.9% at 100–500 Hz, 99% at 1 kHz,
93% at 3 kHz, 73% at 8 kHz, 51% at 12.8 kHz. An impulse response captures nearly
everything below 1 kHz and misses 10–50% of the output energy from 3 kHz up.

**The residual** (tape minus the best linear prediction):
- About **-23 dB relative to the signal at every level** from -30 dB up, and down at the
  hiss floor in quiet passages. Not level-dependent, so no saturation onset in this recording.
- In loud passages **~65% of it is timing wobble** faster than the tracker follows
  (null test: 1%), ~2% gain wobble, ~33% the rest (distortion, noise, ...).
- The residual timing wobble is ~16 µs RMS. Half of it is slow leftovers the warp smoothed
  over; the rest is at 4–80 Hz, with ~3.6 µs at 30–80 Hz (≈0.1% speed-equivalent). Weighted
  W&F specs barely count flutter that fast. Peaks at 7.5 / 15.1 / 30.1 Hz (harmonics of the
  7.5 Hz part), 18.2, 25.5 and 43.6/45.2 Hz.

**Treble compression:** gain drops **~1.7 dB at 6.3 kHz and ~2.5 dB at 10 kHz** when the
band is loud. None at 250 Hz–3 kHz. *(Not replicated, 2026-11-16: absent in three other
songs; it is a step between quiet and loud sections rather than a compression curve, most
likely a difference between the Supraphon and Tidal masters of Shallow.)*

### What this means for the old impulse-response attempt
It could only ever capture the linear part: everything below ~1 kHz, but none of the
modulation effects (wow, flutter, scrape flutter, treble flicker) or the hiss, which is
where the remaining character lives (see the next section).

## 2026-11-16: four songs, deeper tests (`align.py`, `measure.py`, `residual.py`, `investigate.py`)

Songs with sources: B3 Shallow (FLAC), A4 Don't Speak (MP3 320k), A6 Forever Young (FLAC
24/48), A5 I Miss You (MP3 320k, aligned poorly: only 19% of windows match, probably a
different master, so it's discounted below). A2 Join Me in Death: the "Razorblade Mix" MP3
does **not** match the tape (no window correlates in either polarity); the 2008 compilation
used a different mix. Dropped.

### Confirmed across songs
- **Frequency response** agrees within ~0.5 dB between songs: flat ±0.6 dB from 100 Hz to
  2 kHz, ~+1 dB presence lift at 4–8 kHz, -1.2 to -1.9 dB at 50 Hz, the right channel
  losing treble earlier (L-R +2.7..+4.0 dB at 12.8 kHz).
- **Left louder** by +0.75..+1.17 dB; **left later** by 9.7–11.3 µs on side A (matching the
  source-free estimate) and 31.8 µs on Shallow (side B).
- **Speed** playback vs recording within 0.008–0.013%. Wow 0.017–0.023% RMS, flutter
  0.013–0.018% RMS (unweighted, ≤15 Hz).
- **The mechanical fingerprint** is identical in every song: 1.64 Hz (+harmonics) wow, and
  fast-flutter peaks at 7.5, 15.1, 18.2, 25.5, 30.1, 32.8, 43.6, 45.2 Hz. This reads as a
  7.53 Hz rotating part (capstan) with harmonics, and a ~25.5 Hz part (motor) with
  sidebands at ±7.5 Hz (18.2, 32.8) and 2×25.5-7.5 = 43.6 Hz. Deterministic, so it can be
  modelled as a sum of sinusoids plus a random part.
- **Polarity** relative to the source file: inverted for Shallow, Forever Young and I Miss
  You, the same for Don't Speak. The chain can't flip per song, so the masters differ. The
  chain itself probably inverts (3 of 4), but only the test tape can say.

### Hypothesis tests (`investigate.py`, each against a null)
| test | result |
|---|---|
| timing wobble: common or per channel? | **Common** (L/R correlation 0.97–0.99, coherence ≈1 at the mechanical peaks). The only L-R difference is a faint ~1–2 µs wobble at 1.7 / 3.3 Hz: the pinch roller tilting the tape. |
| does loudness move the speed? | No: all correlations at the null level (|r| < 0.03) on this line-out capture. |
| treble compression with level? | No: slope in the loud half -0.006..-0.037 dB/dB. |
| does bass/overall loudness lower the treble? | Only a faint hint on the hottest-recorded song (Don't Speak): ~-0.15 dB of treble per 10 dB of overall level, above null. Possibly the onset of tape saturation. |
| harmonic distortion (FIR-Hammerstein, 2nd+3rd order, tested out of sample) | Not detectable from music except a trace of 3rd order (~-43 dB) in Forever Young. At these recording levels distortion is ≲0.5%, odd order dominant. |
| what's left after linear + timing + gain | **Rides on the signal** (slope 0.6–1.0 dB/dB, far above hiss) and **rises ~6 dB/octave**: about -37 dB re signal at 1 kHz up to -16 dB at 8 kHz. |
| what that leftover is (3–10 kHz, 1.4–5.8 ms windows) | ~30–50% **fast timing jitter** (4–7 µs RMS, scrape flutter) and ~20–40% **treble amplitude flicker** (10–15% RMS on side A, 23% on Shallow/side B: head-to-tape contact). Rest ~20–30%. *(Corrected in v0.2: the flicker figures were an alignment artefact. With the fixed alignment, 3–10 kHz is ~75% timing, ~11% gain (5.6% RMS), ~14% rest.)* |
| dropouts | Gain dips below -1 dB ~8–17/min (mostly in both channels at once), below -3 dB ~0.3–2/min. *(Corrected in v0.2: an alignment artefact; Shallow has none.)* |

### The model this points to (to be confirmed by the test tape)
1. **Static, per channel:** frequency response, L/R gain and treble tilt, inter-channel
   delay (slowly drifting with position on the tape).
2. **Transport timing** (common to both channels): wow incl. the 1.64 Hz series, flutter
   with the capstan/motor line spectrum, ~11–17 µs RMS up to ~45 Hz; a ~1 µs differential
   component at the pinch-roller rate.
3. **Fast modulation, strongest in the treble:** scrape-flutter timing jitter (~5 µs) and
   head-contact amplitude flicker (10–25%). *(Corrected in v0.2: mostly timing, broadband to ≥2.8 kHz
   rates; amplitude flicker only ~1% below 4 kHz and 7–9% at 8–13 kHz.)* Together they produce noise that is
   proportional to the music and rises toward the treble.
4. **Hiss** (-63 dBFS, independent per channel) and brief dropouts.
5. At these levels, **not** harmonic distortion, compression or level-dependent behaviour.
   A candidate for the "dynamic distortion that changes with loudness" is item 3: it scales
   with the music, so loud passages carry more treble shimmer and grain, and quiet ones
   leave only hiss.

Caveat: part of item 3 could be differences between the 2023 Tidal stream (MQA) and today's
sources. The steady tones on the test tape separate that cleanly.

### Open
- The test tape: a steady 3150 Hz tone (flutter, scrape flutter) and a 10 kHz tone (treble
  flicker) show item 3 directly as sidebands around a pure tone; stepped tones and sweeps
  at hotter levels show where distortion and compression begin; the battery 2×2.
- Fetch the intact originals from the Linux box.
- Listening test: rebuild from the source one ingredient at a time (linear → + channel
  offsets → + transport flutter → + fast treble modulation → + hiss) and compare blind,
  level-matched, with the real tape.

## 2026-11-16: left/right similarity (`stereo.py`)
Inter-channel coherence and phase, source vs tape (B3, A4, A6):
- **Below 4 kHz the tape leaves the channels exactly as alike as the source** (coherence ±0.01).
- **Inter-channel phase grows with frequency**, a pure time offset (right leads): side B
  (~30 µs) +12° at 1 kHz, +39° at 4 kHz, +84° at 8 kHz, +110° at 12 kHz; side A (~11 µs) ~+35–44° at 8–12 kHz.
- **The top octave decorrelates**: coherence at 12 kHz drops 0.96 → 0.43 (Shallow, quiet) and
  0.98 → 0.77 (Forever Young), from per-channel hiss and the independent part of the flicker.
- With the treble level difference (left +3–4 dB at 12–16 kHz), the tape gives the top
  octave a lateralised, partly decorrelated, "airy" quality, while timing cues and level cues
  point to opposite sides (right earlier, left louder). This is the owner's
  "binaural-like" hunch in measured form.

## 2026-11-16: prototype emulator v0.1 (`fitprofile.py`, `emulator.py`, `render.py`)
Profile `profiles/wmd6c_xlii_sideB.json`, fitted from Shallow. Null floors come from fits with
the *target* shifted by 1 s (shifting the regressor inflated the floor), smoothed, and only
components >2× above the floor are kept. Listening set: `out/listening/B3/`.

Validation: the emulated Shallow measured with the same pipeline as the real tape:
| measured | real tape | emulation v0.1 |
|---|---|---|
| mechanical lines | 1.64/3.32 + 7.5…43.6 Hz | same lines |
| wow 0.3–4 Hz | 0.018% | 0.019% |
| L–R gain | +0.95 dB | +0.94 dB |
| leftover 1 kHz / 8 kHz (loud) | −51.5 / −46.0 dBFS | −53.6 / −46.4 dBFS |
| L–R delay | 31.8 µs | 27.4 µs |
| flutter 4–20 Hz | 0.014% | 0.009% |
| fast treble jitter (1.5 ms fits) | ~7 µs | 3.8 µs |
| treble flicker / broadband gain wobble | 23% / 1.8% | 14% / 2.9% |

*(v0.1's measurements used the flawed alignment; see the v0.2 sections below.)*

Calibration gaps for v0.2:
1. The minimum-phase EQ adds ~4 µs between channels: set the static delay so the *measured*
   L–R comes out at 31.8 µs.
2–3. Flutter at 4–20 Hz and fast jitter are low. The >2× floor rule likely drops real broadband
   flutter, and the 45 Hz transport/scrape crossover loses energy.
4. Flicker depth must grow **faster than proportionally with frequency** (less in the mids, more
   in the treble): try ∝ f² normalised at the treble band, then confirm with the test tape's
   3150 Hz and 10 kHz tones.
Method: iterate analysis-by-synthesis, adjusting the profile until measure(emulation) ≈
measure(tape), since the pipeline has its own smoothing and floor biases.

## 2026-11-16: first blind test (owner), and what it pointed at (`dynamics.py`)
Blind X/Y (tape vs emulation v0.1), heard over Bose QC45 via Bluetooth: **the tape was
obvious on first listen.** The owner's observations:
1. The climax ("I'm off the deep end…", ~1:45): the tape has penetrating, heart-grabbing
   power; the emulation is defined but lifeless.
2. Piano and acoustic guitar are far too detailed and clean in the emulation.
3. The tape's hiss seems responsive: it rises when a sound ends into silence, then slowly
   settles.

Follow-up tests:
- **Distortion vs level** (2nd/3rd-order, trained and tested on alternating seconds, so the
  climax is in both): rises with level to -45 dB (L) / -48 dB (R) re signal at Shallow's loudest;
  the emulation gives -47 / -49. Not the missing ingredient. (The earlier first-half/second-half
  split was blind to Shallow's climax; corrected here.)
- **Treble floor in silences vs time since a loud sound**: flat (-68.3 dBFS at 0.3–1 s, 1–3 s and
  >3 s). The first ~0.3 s after a sound can't be tested this way: the music's own tail still
  fills the band.
- Reading: observations 1–3 fit **too little fast modulation** in v0.1. The validation already
  showed treble flicker at ~60% and scrape jitter at ~55% of the tape's, and the "rest" component
  is not modelled. On decaying tails the modulation turns treble into noise-like sidebands that
  swell and fade with the tail (observation 3), it softens detail (2), and on a belted voice it
  thickens like a subtle ensemble effect (1). Unconfirmed: the Supraphon master may differ from
  the Tidal stream that was taped; a BlackHole capture of Tidal's Shallow would remove that confound.

### Plan for v0.2 (done, see below; items 1–3 changed shape once the alignment was fixed)
1. Calibrate fast modulation by analysis-by-synthesis until the emulation measures like the tape on
   residual.py, investigate.py E/E2 and the flutter numbers: stronger treble flicker with a steeper
   frequency law, scrape jitter level, 4–20 Hz flutter.
2. Model the "rest" as noise that rides on the signal, per band, at the measured share.
3. Calibrate the static L–R delay so the measured value is 31.8 µs.
4. Re-render, blind test again; if possible from a Tidal capture of Shallow.

## 2026-11-16: Tidal capture of Shallow (BlackHole)
- Captured from Tidal at 24-bit/48 kHz (Max, normalisation off, volume 100%) →
  `data/sources/B3.flac`; the Supraphon CD is kept as `B3_supraphon.flac`. No clipping (peak -0.011 dBFS);
  the master itself is brickwall-limited to ~0 dBFS.
- **Tidal and the Supraphon CD are the same master**: identical gain, response within 0.01 dB to
  16 kHz, coherence 0.9998–1.0000. So the blind-test differences are the tape, not the source.
- Against the real source, the tape is again **polarity-inverted**: the chain most likely inverts
  (Don't Speak's MP3 is probably itself inverted relative to Tidal).
- Re-alignment: 76% of windows matched, wow 0.018%, flutter 0.016%, lines at 1.65/3.34/4.99/7.51 Hz (unchanged).
- Shallow's treble "step" is therefore not a master difference. Over 5 s windows the treble gain moves
  only ±0.2 dB, and at 10 kHz it follows level (partial r -0.46, vs +0.12 for time): about
  -0.2..-0.3 dB in the loudest climax stretches. A small, real, level-dependent treble loss. The
  larger per-block step (-1.7..-2.5 dB) is unresolved; modulation sidebands raising quiet treble
  bands is one candidate. The test tape's stepped tones will settle it.

## 2026-11-16: v0.2. A better alignment, and what it overturned
New sources, all captured from Tidal via BlackHole: A2 Join Me in Death and A5 I Miss You
(16/44.1, the versions Tidal serves now), A6 Forever Young (identical to the purchased 24/48 file:
same gain, coherence 1.0000 to 12 kHz, so A6 keeps the 24/48 file; the capture is `A6_tidal.flac`).
The old I Miss You MP3 is kept as `A5_mp3.mp3`.

### The alignment flaw (`align.py`)
- Join Me in Death and I Miss You first looked like poor source matches (49% / 18% of windows tracked,
  coherence 0.13 at 8 kHz), but their treble *level* followed the source as closely as the good
  songs (0.2–0.6 dB block-to-block). Only the fine timing failed.
- Cause: `align.py` picked each window's delay in 200 Hz–8 kHz but judged the match on the
  **full-band** waveform. Below ~200 Hz the tape chain turns the phase by 90–300° (next section), so
  the bass is anti-correlated with the source (median window match −0.1 to −0.5 below 200 Hz) and
  bass-heavy windows were rejected. The warp then interpolated across the gaps, leaving tens of µs of
  timing error.
- Fix: polarity and tracking now use 200 Hz–8 kHz throughout (`TRACK_BAND`). Windows tracked:
  B3 77% → 98%, A2 49% → 98%, A4 → 99%, A5 18% → 95%, A6 83% → 98%. Polarity is now decisive
  (window match ~+0.9 vs ~−0.6).
- **Polarity:** inverted against the Tidal-captured sources of B3, A2 and A5, and against A6's file
  (identical to Tidal); the same only against A4's MP3. **The chain inverts** (4 of 4 Tidal-equivalent
  sources); Don't Speak's MP3 is itself inverted relative to Tidal.

### The chain's low-frequency phase (static, the same in every song)
Phase of tape re source after removing the 1–8 kHz delay, left channel (right within ~5°):

| | 25 Hz | 32 Hz | 40 Hz | 50 Hz | 63 Hz | 100 Hz | 200 Hz | 500 Hz | 2 kHz |
|---|---|---|---|---|---|---|---|---|---|
| 5 songs (spread ±10°) | ≈ +285° | ≈ +212° | +170° | +139° | +109° | +72° | +40° | +26° | +33° |
| minimum phase from the magnitude | +107° | +84° | +70° | +52° | +41° | +25° | +13° | +8° | +10° |

At 40 Hz the tape's bass is inverted relative to its mids. The measured magnitude is only −4.5 dB at
30 Hz, so this much phase needs a steep roll-off below 20 Hz that music can't reveal: probably
several coupling capacitors in cascade (Yamaha out, Walkman line in, record/playback amps, line out,
the capture card's input). v0.1's minimum-phase EQ missed it; v0.2 uses the measured phase
(`fitprofile.eq_magnitude_phase`, 0.7 Hz resolution so the bottom octave has data).

### What the fast modulation really is (`modstats.py`, `signature.py`)
New estimator: **complex demodulation** per octave band. With analytic signals of the prediction Ŷ
and the residual R, c = R·conj(Ŷ)/(|Ŷ|²+ε) splits the residual into amplitude modulation (real part)
and phase modulation (imaginary part → timing) at every sample, giving modulation spectra up to half
the band width (2.8 kHz rates in the 8 kHz octave). Checked on synthetic ground truth: 10% AM reads
8.4% AM / 0.5 µs; 5 µs timing reads 4.0 µs / 1.7% AM. The old 64-sample window fits pass the same
test (9.1% / 5.15 µs).

With the corrected alignment both estimators agree on Shallow (3–10 kHz: window fits 5.6% gain /
4.6 µs timing, demodulation 5.8% / 3.9 µs), and the picture changes:
- **The residual is mostly timing.** Shallow, µs RMS per modulation-rate band, the same in every
  octave from 1 to 13 kHz (the signature of a pure time shift):

  | rate | 3–6 Hz | 6–12 | 12–24 | 24–48 | 48–96 | 96–192 | 192–384 | 384–768 | 768–1536 | 1536–2800 |
  |---|---|---|---|---|---|---|---|---|---|---|
  | timing (µs) | 1.4 | 2.2 | 2.3 | 3.1 | 1.9 | 1.1 | 1.2 | 1.2 | 1.2 | 1.2 |
  | L/R coherence (8 kHz octave) | 0.82 | 0.96 | 0.97 | 0.98 | 0.94 | 0.70 | 0.57 | 0.47 | 0.37 | 0.30 |

  Below 48 Hz this is transport flutter the warp didn't follow (common to both channels). Above it,
  a broadband **scrape flutter** continues flat to at least 2.8 kHz, partly independent per channel.
  At 13 kHz, ~3 µs of fast jitter is a phase modulation of ~0.25 rad: noise sidebands that follow
  the music.
- **Amplitude flicker is small**, and steeply frequency-dependent: demodulated AM per rate band is
  ~0.2–0.4% at 1 kHz, 0.5–0.7% at 2 kHz, 0.5–1.4% at 4 kHz, 1.5–3.8% at 8 kHz, 4–12% at 13 kHz,
  with part of it leakage from the timing jitter and hiss. Its L/R coherence is low (0.1–0.6).
- **Correction:** the earlier "treble flicker 10–15% (side A) / 23% (Shallow)" was an artefact of
  the alignment flaw: large timing errors break the small-τ linearisation and the fits book them as
  gain. So v0.1 had several times too much amplitude flicker, and its fast timing stopped at 375 Hz
  rates while the tape's runs flat to ≥2.8 kHz. The blind test's "too clean, too detailed" fits a
  missing broadband scrape flutter.
- **Dropouts:** with the corrected alignment Shallow has **no** gain dips below −1 dB in loud 11 ms
  windows. The earlier "8–17/min" came from the same alignment artefact.

### Across songs (`signature.py`, corrected alignment)
Fast timing jitter per rate band is the same on every song: 24–48 Hz ~2.6–3.4 µs, 48–96 Hz ~2.1–2.35,
then ~1.0–1.6 µs per band out to 2.8 kHz (Join Me in Death ~2–2.4). The low-frequency phase is identical
on both sides (+224..+237° at 30 Hz, +136..+144° at 50 Hz, ~+70° at 100 Hz). Amplitude flicker at
8 kHz per rate band: 1.0–4.7% (A4, A5, A6), 1.5–3.8% (B3).
**Join Me in Death is an outlier**: 2–3× the AM (8–10% per rate band at 8 kHz) and more fast jitter.
It sits at the very start of side A, so either the tape behaves worse there or Tidal's current version
differs subtly in the treble. It is left out of profile averages for now.

## 2026-11-16: emulator v0.2, calibrated by analysis-by-synthesis (`calibrate.py`)
Model (`emulator.py`): record gain → tiny cubic → **measured magnitude and phase** per channel →
one warp per channel with transport (slow, line spectrum) + differential (slow L−R) + **fast jitter**
(45 Hz–4 kHz, a common part and a per-channel part) → **amplitude flicker** with a per-octave depth
and a per-octave L/R share → hiss per channel → polarity.

Calibration loop: render Shallow from the Tidal source → `align.py` → `signature.py` → compare with
the real tape's signature → correct EQ/phase/gain, transport (from the speed-deviation bands and the
24–48 Hz timing), jitter (per rate band, and its common share from the L/R coherence), flicker
(depth per octave, solving emu AM = 0.7 × injected + leakage; L/R share per octave; rate spectrum).
Seven iterations (`out/calib/B3_history.json`, logs `out/calib_B3*.log`).

Final profile `profiles/wmd6c_xlii_sideB.json` (v0.1's is kept in `analysis/out/v01/`):
| | value |
|---|---|
| gain at 1 kHz | L −7.26, R −8.22 dB |
| L−R delay | +31.8 µs (from the measured phase; matches the tape exactly now) |
| transport | 65 µs RMS total (mostly the slow drift below 1 Hz), mechanical lines included |
| differential (slow L−R) | 3.5 µs RMS |
| fast jitter | common 3.15 µs + per channel 1.14 µs RMS (45 Hz–4 kHz); common share 0.99 below 100 Hz, 0.78 at ~270 Hz, 0.49 above 2 kHz |
| amplitude flicker depth | 0.7% (1 kHz), 1.3% (2k), 1.3% (4k), 7.3% (8k), 9.0% (13k); L/R share 0.23–0.28 below 4 kHz, ~0.5 above |
| dropouts | none |
| hiss | blank tape +0.7 dB (in-song top-octave floor −66.9 vs blank −67.3 dBFS) |

Validation, measured with the same pipeline (iteration 7):
| | tape | emulation v0.2 |
|---|---|---|
| speed deviation per band 0.3–20 Hz | 0.003 / 0.004 / 0.018 / 0.010 / 0.009 / 0.001 % | identical |
| timing µs, 8 kHz octave, 24–48 / 48–96 / 96–192 / 192–384 / 384–768 / 768–1536 / 1536–2800 Hz | 3.08 / 1.89 / 1.11 / 1.17 / 1.16 / 1.21 / 1.24 | 3.07 / 1.87 / 1.11 / 1.24 / 1.21 / 1.27 / 1.31 |
| timing L/R coherence, same bands | 0.98 / 0.94 / 0.70 / 0.57 / 0.47 / 0.37 / 0.30 | 0.98 / 0.93 / 0.70 / 0.58 / 0.47 / 0.36 / 0.30 |
| AM %, 13 kHz octave, 24–48 / 96–192 / 768–1536 Hz | 9.77 / 7.58 / 12.19 | 9.61 / 7.66 / 13.03 |
| residual re signal, loud, 1k / 2k / 4k / 8k / 13k | −26.1 / −21.3 / −14.3 / −8.7 / −3.9 dB | −26.7 / −22.0 / −14.9 / −9.1 / −4.1 dB |
| static response L/R, 30 Hz–14 kHz | (9 points) | within 0.1 dB and 2° |
| 3rd-order distortion at the loudest, L/R | −44.6 / −48.9 dB | −46.9 / −48.4 dB |

Remaining gaps, all small:
- Slow timing left after the warp at 3–12 Hz is ~25% low in the emulation (1.1 vs 1.45 µs, a 0.004%
  pitch wobble). The speed-deviation spectrum itself matches, so this is in what the warp can't follow.
- High-rate AM at 4 kHz is ~30% high (1.9 vs 1.4% at 384–768 Hz); AM L/R coherence below 4 kHz ~0.07 high.
- **Level dependence** (`dynamics.py` test 3, demodulated modulation per source-loudness class). Fast
  jitter is flat with level on both. The emulation (level-independent by construction) reproduces most of
  the tape's apparent rise of slow timing and 4 kHz AM with level, so that part is the estimator reacting
  to denser music. What it doesn't reproduce: the tape's **8 kHz AM grows ~30% from quiet to loud**
  (slow 5.6 → 7.5%, fast 6.3 → 8.1%; emulation flat ~7–8%), and slow timing is ~1 µs higher in the
  loudest blocks (6.1 vs 5.1 µs; possibly position on the tape rather than level). Candidates for v0.3
  once the test tape's stepped tones confirm them.

Listening set: `out/listening/B3/` (ladder `1_source` … `6_full`, `tape`, blind `X.wav`/`Y.wav` with a fresh
shuffle for this version). v0.1's set is in `out/listening/B3_v01/`.

## 2026-11-16: second blind test (owner), and the noise floor (`leaks.py`, `spectro.py`)
Blind X/Y, v0.2 vs tape. The tape was identified again, first by a giveaway (the tape file began with
the tail of the previous song; fixed, see below), then by ear:
1. The lead vocal is **vastly improved** over v0.1.
2. Behind the loud vocal (after ~1:45) the piano is far too separated and discernible in the
   emulation; on tape the vocal overshadows and absorbs it.
3. The tape has "a deep palpable presence and spaciousness in the background", "some sort of low
   ambient substrate that makes you feel space", intimate, "inside of it". The emulation has nothing there.

### Leaks from elsewhere (`leaks.py`): none
The model predicts each tape channel from the same source channel at the same moment. Tested what
that misses, with the emulation (no leaks by construction) as the reference:
| test | tape | emulation | verdict |
|---|---|---|---|
| crosstalk, 2-input fit, path gain re direct at 63 Hz / 1 kHz / 8 kHz | −24 / −39 / −24 dB | −25 / −40 / −24 dB | **estimator artefact**, not crosstalk (a trace of real leak only at 125–250 Hz, ~−44 dB) |
| print-through, residual vs source at 0.3–6 s lags | ≤ −71 dB re source | ≤ −74 dB | none |
| residual below 700 Hz re signal, loud blocks | −37 … −32 dB | within 1–2 dB | matched |

Lesson: the 1 s-shift null read 8–10 dB lower than both, so the "crosstalk" looked real until the
emulation went through the same script. With mono delay tracking and a static L–R delay, the fit books
content-dependent timing error as a +90°, +6 dB/octave leak. **The emulation is the null to trust.**

### Spectrograms (`spectro.py`, `out/listening/B3/spectrograms.png`)
Tape minus emulation per octave over the whole song: within 0.1 dB for L+R and 0.3 dB for L−R, 31 Hz
to 16 kHz. The difference panels showed what the averages hide: red streaks at 2–12 kHz in the quiet
intro (both L+R and L−R), a red band above 16 kHz in loud sections, and faint steady lines near 8 and
45 Hz on the tape (far below audibility).

### The tape's real noise floor is the recorded gap, not the blank leader
- Where the source's own treble is absent, the tape's floor sits above v0.2's: +0.9 dB at 2.5 kHz,
  +2.8 at 4–6.4 kHz, +2.6 at 8 kHz, +1.7 at 10 kHz (minimum statistics, 5th percentile of 0.17 s
  blocks per 1/3 octave; the same in L−R). It barely follows the music's level (8 kHz octave: +0.6 dB
  over 15 dB of level), so it is a higher steady floor, not noise riding on the signal.
- The hiss had been measured on the blank leader before the first song. The **silent gaps between
  songs**, recorded with digital silence going in, are noisier (long gaps, quietest 60% of 0.5 s chunks):

  | 1/3 octave | <130 Hz | 200–400 | 500–1k | 1.3–2k | 2.5–6.4k | 8k | 10k | 12.8k | 16k |
  |---|---|---|---|---|---|---|---|---|---|
  | side B, gap − leader (dB) | ~0 | +1.3…+3 | +2…+3 | +3.5…+5 | **+4.2…+5.0** | +3.7 | +2.5 | +1.0 | +0.2 |
  | side A | (leader has its own rumble) | −2…−1 | −1…+1 | +2…+3 | **+3.3…+4.3** | +3.5 | +2.6 | +1.2 | +0.3 |

  The gap floor is stable (300 Hz–6 kHz: −65.8…−66.1 dBFS in every clean chunk on both sides) and
  independent between channels (coherence 0.01 above 2 kHz). Probably bias noise plus the record
  chain's noise, which only exist where the deck recorded.
- So v0.2 had about a third of the real noise power in the presence region. A noise bed that is
  different in each ear and too quiet to register as hiss is a candidate for observation 3
  (and, by masking low-level detail, for 2). To be confirmed by listening.
- Side A's blank leader also carries low-frequency noise the gaps don't (−13 dB at 25 Hz gap vs leader,
  L/R coherence 0.5): something mechanical at the start of that side. The gaps are the reference there too.
- Above 16 kHz the tape has slightly more than v0.2's extrapolated roll-off (response at 18 kHz −4.6 dB
  vs −6.1 dB; the excess at 20 kHz is −72 dBFS). The static response is now measured up to 18 kHz.

### v0.3 changes
- Noise from the recorded gaps (`fitprofile.recorded_noise_psd`, `tracks.recorded_gaps`), used for the
  emulator's hiss and for the noise subtraction in the response estimate; the +0.7 dB patch is gone.
- Response measured to 18 kHz (`EQ_TOP_HZ`).
- `render.py` cuts every listening file to the song itself with identical fades.
- Recalibrated (`calibrate.py --refresh-noise`), since more noise changes what the modulation
  estimators read.

### The deck's steady tones, spotted by the owner in the spectrogram
In the quiet first 75 s the tape's low end showed two faint lines and a "thickening" between ~18 and
60 Hz that the emulation lacked. Measured at 0.05 Hz resolution (first 80 s of Shallow):
| tone | L | R | L re R | what |
|---|---|---|---|---|
| 7.55 Hz | −90.0 dBFS | −90.8 | in phase, coherence 0.99 | capstan rotation: the same rate as the main flutter line |
| 43.55 Hz | −82.5 | −84.0 | in phase, 0.95 | the motor-related rate from the flutter spectrum (2×25.5 − 7.5) |
| 50.00 Hz | −91.3 | −86.3 | +75°, 0.80 (unsteady) | mains hum: recorded onto the tape or picked up by the capture |
| 41.70 Hz | −88.5 | at the floor | | left only, unidentified |
| 60.00 Hz | | | | in the **source** (present in the emulation too): hum in the recording itself |

- 7.55 Hz runs through both whole sides (23–24 dB above the floor, −92…−95 dBFS) and the blank tape
  before song 1, but is not detectable on the 2 s of clear leader (weak test: 0.5 Hz resolution). So it
  needs coated tape at the head: the capstan's once-per-turn irregularity turning standing
  magnetisation into a tone is the likely mechanism. 43.55 Hz is steady on side B's left channel
  (−83 dBFS) and weak or absent on side A; 62.4 Hz (L, −78 dBFS) also shows in side B's whole-side spectrum.
- So the mechanics reach the audio two ways: they modulate the timing (modelled since v0.1) and they
  add faint tones at their own rates (new).
- The "thickening" is the noise floor's shape: it falls away below ~18 Hz, while v0.2's noise, taken
  from a 5.9 Hz-resolution spectrum of the leader, stayed 3–5 dB too high down there.
- Audibility: 43.55 Hz at −83 dBFS is ~20–30 dB under the hearing threshold at realistic headphone
  levels, and 7.55 Hz is infrasonic. Reproduced anyway as part of the deck's fingerprint
  (`fitprofile.steady_tones` → profile `tones`; noise measured at 0.5 Hz resolution below 60 Hz).
  `steady_tones` works where the song leaves the bottom end free (Shallow's intro); on bass-heavy songs
  it finds nothing, and on Forever Young it lets one bass note through, so a side profile should
  measure the tones from the whole side's percentile spectrum instead.

### v0.3 result and the response overlay (`eqplot.py`, `out/listening/B3/response.png`)
Recalibrated with the recorded-gap noise (iterations 8–13) and rendered; `out/listening/B3/` now holds v0.3
(v0.2's set: `B3_v02/`). Checks on the final render:
- **Noise floor:** quietest moments per 1/3 octave, tape minus emulation within ±0.2 dB from 200 Hz to
  16 kHz (was +2.8 dB at 4–6 kHz), within −1.7…+0.4 dB below that.
- **Static response against the source, tape vs emulation:** magnitude within 0.01 dB from 31 Hz to
  12.5 kHz and 0.09 dB at 16 kHz; phase within 2°. The curve itself (L / R, re 1 kHz): −4.0 / −3.8 dB at
  31 Hz, −1.2 / −1.6 at 50 Hz, flat to 1 kHz, +1.2 / +0.6 at 4 kHz, +1.3 / +0.4 at 6 kHz, +0.7 / −1.2 at
  10 kHz, −3.0 / −7.3 at 16 kHz.
- **Does the response change with level?** Loud third minus quiet third of the song (1.4 s windows):
  the tape loses 0.05 dB at 2 kHz, 0.08 at 4 kHz, 0.13–0.17 at 6–8 kHz and 0.12–0.26 at 12.5 kHz in the
  loud passages; the emulation, level-independent by construction, reads 0 ± 0.03. A real but tiny
  level-dependent treble loss, not modelled.
- Fast jitter within 5%, AM within 5–10% in the top octaves, residual per octave within 0.7 dB.
- **Bass-driven distortion** (2nd + 3rd order of the source below 150 Hz, fitted on even seconds, tested on
  odd, loudest-bass blocks; scratch test): −60 / −56 dB re signal at 20–100 / 100–300 Hz on tape (L),
  −65 / −61 dB in the emulation. The tape has a little more, including a trace of 2nd order, but it is
  far too small to be a "presence".

### Owner: the metal tape had the presence too
A Type IV tape of the same songs, with a much lower noise floor, gave the same background presence when
heard from the Walkman's headphone out; after it, the source from the Mac on the same headphones "felt
dead and cold". So noise is unlikely to be the whole tell; what both tapes share is the deck. Note the
direct-listening chain includes the Walkman's headphone amplifier, which the line-out capture does not,
but the blind pair's tell is in the capture itself. Still open after v0.3: nothing measured so far
distinguishes the files apart from the small level-dependent effects (8 kHz AM +30% from quiet to loud,
treble −0.1…−0.3 dB in loud passages, slow timing ~1 µs higher in the loudest blocks).

### Diagnostic blind pairs (`diagset.py`, `out/listening/B3/diagnostic/`)
To let the ear say where the tell lives: six blind pairs, tape vs emulation after identical treatment:
below 150 Hz, 150 Hz–1.3 kHz, 1.3–6 kHz, above 6 kHz, mono (L+R), difference (L−R).

### Is the response's movement tied to the music? (`coupling.py`, `peaks.py`, `stereo.py`; owner's question)
The static curve is identical, so the character is in how the response moves over time. `signature.py`
matches how much it moves and how fast; these tests ask whether the movement follows the signal. The
emulation's modulation is random by construction, so it is the reference.
- **Coherence of each octave's AM and timing with the music** (bass waveform below 200 Hz, its square,
  overall level, the band's own level; rates 1–400 Hz): 0.01–0.05 on tape and on the emulation
  (independent signals read ~0.01). The only excess: 1 kHz octave AM vs the bass waveform at 60–150 Hz,
  0.050 on tape vs 0.016, i.e. ~5% of an AM that is itself 0.3–0.4%.
- **Attack vs decay:** mean AM and timing while the band's level falls fast / falls / is steady / rises /
  rises fast stay within ±0.3% and ±0.4 µs with no pattern, on both.
- **Peaks** (`peaks.py`): gain on the linear prediction by amplitude class is flat within ±0.05 dB from the
  median to the top 0.03% of instants, broadband and at 350 Hz / 1.4 kHz; −0.1 dB across the range at
  4 kHz; at 8 kHz the top 0.03% read −0.18 dB on tape vs +0.13 dB in the emulation. No rounding of transients.
- **Inter-channel coherence of the output per octave** (`stereo.py`): identical, e.g. 12 kHz quiet
  0.97 → 0.49 on both; the largest gap is 12 kHz loud, 0.37 (tape) vs 0.41.
- **Bass-driven distortion** is `bassdist.py` (numbers above).
So the tape's fluctuations are random with respect to the music, and with v0.3 every statistic measured
from music agrees between tape and emulation within small fractions of a dB, except the level-dependent
effects listed above. v0.2 differed audibly in one measured respect, the noise bed.

## 2026-11-16: third blind test (owner): v0.3 not told apart
Blind X/Y, v0.3 vs tape, Bose QC45 over Bluetooth: "having trouble telling X and Y apart", a guess on
intuition, and the guess was wrong. One trial, on the least revealing playback chain, so not proof of
equivalence; but the two tells of v0.2 (background presence, piano behind the vocal) were gone. Between
v0.2 and v0.3 the audible change was the noise bed (recorded-gap noise, +4–5 dB at 1.3–6 kHz), so that
was the tell, or most of it, on this setup. The metal-tape remark (same presence with less noise) stays
unexplained; that comparison was Walkman headphone out vs the Mac, a different chain.
To do: repeat on the DT 770 through the Yamaha; test a song the profile was not fitted on (below).

## 2026-11-16: cross-song validation (profile from Forever Young, applied to I Miss You)
`profiles/wmd6c_xlii_sideA.json` was fitted on A6 alone (`calibrate.py --track A6 --init --iters 6 --tones
side`), then used to emulate A5, which it never saw; `out/signature_A5_xval.txt`, listening set
`out/listening/A5/`. (This run exposed a bug in `align.warp`: positions past the end crashed and positions
before the start wrapped around; they are now held at the edge sample. Real tape excerpts have 8 s of
margin, so earlier results are unaffected.)

What carries over (A5 tape vs its emulation from A6's profile):
| | tape | emulation |
|---|---|---|
| static response, 30 Hz–14 kHz | (9 points) | within 0.1 dB and 2–4° |
| level per octave, L+R / L−R, 31 Hz–8 kHz | | within 0.1 / 0.2 dB (16 kHz: −0.3 / −0.7) |
| timing 12–96 Hz (8 kHz octave) | 1.83 / 2.55 / 2.11 µs | 1.70 / 2.64 / 2.25 µs |

What doesn't:
| | tape | emulation |
|---|---|---|
| speed deviation 6–12 Hz | 0.005% | 0.014% |
| slow timing left after the warp, 3–6 / 6–12 Hz | 0.9 / 1.4 µs | 2.2 / 3.5 µs |
| fast jitter 192–2800 Hz (8 kHz octave) | 0.80–1.13 µs | 1.15–1.63 µs |
| residual re signal, 1k / 4k / 13k | −27.4 / −15.4 / −4.9 dB | −24.0 / −12.3 / −1.5 dB |
| "AM" at 8 kHz, 3–96 Hz rates | 0.95–2.96% | 3.8–4.8% |

- The emulation reads Forever Young's values on I Miss You's music, so the estimators are not
  song-dependent: **the modulation really differs between songs on the same side.** Capstan-rate flutter
  (3–12 Hz, 8 kHz octave, µs): A2 3.9 / 5.9, A4 1.4 / 2.2, A5 0.9 / 1.4, A6 2.2 / 2.8, B3 1.4 / 2.2.
  Fast jitter 192–384 Hz: A5 0.80, A4 1.00, B3 1.17, A6 1.21, A2 1.64 µs. It does not simply follow the
  position on the tape (A4 → A5 → A6 goes down, then up).
- A likely cause for the flutter part: the tape was recorded and played on the same deck, so two wobbles at
  the same 7.53 Hz add, with a relative phase that drifts; the sum then swells and fades along the tape.
  Untested. It would call for two transport passes in the model instead of one stationary spectrum.
- The side-A calibration drove the amplitude flicker to ~0 (0.01% at 4–13 kHz), yet the emulation reads
  3.8–4.8% "AM" at 8 kHz: with τ of total timing error the demodulated gain carries a second-order term
  −½(ωτ)², so **most of the treble "AM" in the signature is timing**, on tape and emulation alike. Side A
  has essentially no amplitude flicker of its own; side B's fitted depths (6% at 8 kHz, 11% at 13 kHz)
  may be partly the same thing and deserve a second look.
- Consequence: a profile fitted on one song carries that song's modulation depth; the emulation of A5 has
  ~3 dB more timing residue than A5's tape. A side profile should be fitted on several songs (the
  calibration takes one song at present), and the model should let modulation depth vary along the tape.

## 2026-11-16: fourth blind test (owner): the cross-song pair, I Miss You
Blind X/Y, A5 tape vs its emulation from Forever Young's profile: the tape was identified correctly, "but
they're very very similar". What gave it away:
1. On the fret-finger slide at the start the tape is less bright / sharp, and "doesn't give you that
   tickle in the side". The same slight loss of treble sharpness on the vocals in the middle of the song.
2. Where the voice gets powerful the tape has a "subtle packing", read as more impact; the emulation
   "contours it carefully".
Measured on this pair (`peaks.py`, `dynamics.py`):
- **Treble saturation is real but tiny:** power gain of each treble band by that band's own level, loudest
  0.5% of 11.6 ms blocks, tape minus emulation: −0.07 dB (2.8–5.7 kHz), −0.12 (5.7–8 kHz), −0.15
  (8–11 kHz), −0.17 (11–16 kHz), falling steadily with level. At the very highest treble peaks the
  coherent gain is 0.2–0.4 dB lower on tape. Not modelled.
- **No packing of the voice shows up:** broadband and midrange peak gain within 0.02 dB on both;
  3rd-order distortion at the loudest −47.8 / −50.3 dB (tape) vs −47.2 / −48.0 dB (emulation).
- The sizeable difference is the one the cross-song numbers predicted: the emulation carries Forever
  Young's wobble, ~3 dB more timing residue, ~40% more fast per-channel jitter and ~3× the capstan-rate
  flutter of A5's own tape. Jitter spreads a bright narrow sound into side frequencies, differently per
  ear, which fits "sharper, with a tickle in the side" as something the emulation adds.
Experiment running: `calibrate.py --track A5 --name wmd6c_xlii_sideA_A5wobble --only transport,jitter`:
static part kept from Forever Young, only the wobble depth adapted to A5's stretch of tape. The earlier
pair is kept in `out/listening/A5_xval/`.

## 2026-11-16: v0.4. Wobble depth per stretch of tape, and treble saturation
### Adapting only the wobble (`calibrate.py --only transport,jitter`)
`profiles/wmd6c_xlii_sideA_A5wobble.json`: the side-A profile from Forever Young with only the transport
and jitter spectra corrected on I Miss You (3 iterations); response, noise and the rest untouched.
A5 tape vs this emulation: speed deviation 6–12 Hz 0.005 vs 0.006% (was 0.014), fast jitter within 5%,
residual re signal per octave within 1 dB (was +3 dB; now 0.8–0.9 dB under), 24–48 Hz timing 2.55 vs
2.57 µs. Not converged: 12–24 Hz timing 1.83 vs 0.88 µs (over-corrected).
So a side profile needs a per-stretch wobble depth; the static part does not.

### Treble saturation (`satfit.py`, emulator `saturation.hf`)
The owner would not discount the small level-dependent treble loss, and it turned out to be lawful.
- Measure: power gain of each treble band by that band's own level (11.6 ms blocks, six level classes,
  re the 75–90% class), tape minus emulation.
- Model: first-order pre-emphasis shelf → cubic (u − c·u³) → the exact inverse shelf, after the flat cubic.
- Fit on Shallow (loud classes only; the quiet ones are noise-dominated): corner 2274 Hz (70 µs), shelf
  +18 dB, c = 0.2013, rms error 0.034 dB. The strength is well determined; the shape is not (errors
  0.034–0.060 dB across the grid, best at the largest shelf tried).
- **Cross-check on I Miss You** (other side, recorded 1.6 dB hotter), loudest 0.5% class, measured vs
  predicted: 2.8–5.7 kHz −0.08 / −0.13; 5.7–8 kHz −0.12 / −0.17; 8–11 kHz −0.16 / −0.11; 11–16 kHz
  −0.18 / −0.16; rms difference over the loud classes 0.022 dB. A consistent property of deck and tape
  with the right level law. The test tape's stepped tones should fix the shelf.
- Added to all three profiles. Shallow's listening set (v0.3) was rendered without it.
- Verified on the re-rendered A5 (wobble adapted + saturation, `out/listening/A5/`): treble band gain by
  level, tape minus emulation, within ±0.05 dB in the loud classes of all five bands (was −0.07…−0.17).
  The coherent gain at the very highest peaks now overshoots: broadband top 0.03% −0.16 dB (tape −0.02),
  4 and 8 kHz envelopes −0.27 dB (tape −0.16 / −0.14). The stage's shape needs the test tape.

## 2026-11-17: the metal tape, captured from the headphone jack
New capture by the owner: `data/metal-tape.flac` (56:17, 24-bit/96 kHz, both sides in one file) and
`data/sources/metal_source.flac` (one Tidal capture of the whole playlist via BlackHole; 44.1 kHz material
at 96 kHz: nothing above 22 kHz). Both decode without errors.
- **Tape:** Sony Metal XR 60 (Type IV, 70 µs), recorded hotter than the chrome. A C60, so a thicker base
  than the chrome C90. Same 14-song session on the same deck (tracklist in `tracks.py`, ids MA1–MB7).
- **Chain, new:** Walkman **headphone jack** → Y splitter (DT 770 Pro 32 Ω on the other branch as load) →
  the Linux box's line in. The 2023 chrome capture went through LINE OUT. Volume slider set by ear.
- **Deck state:** restored by the owner with a custom aftermarket rubber kit including the pinch roller,
  motor oiled, cogs greased; heads, capstan and roller cleaned with isopropyl alcohol just before this
  capture (the roller had gathered a lot of residue). Batteries: Varta alkalines.
- **Level:** music peaks at −1 dBFS on side A; the capture **clips** at full scale in MB1 (33 short
  moments, 29:26–31:12) and MB2 (3 moments at Shallow's climax, ~35:00): 606 samples in all.
  Recommended −3 dB capture gain for further takes.
- **Layout** (`out/metal_locate.json`): each song located on the tape by correlation; consecutive songs
  agree to 0.1 s. Each side starts with 12–18 s of lead-in at −35…−55 dBFS before the first song (0:18.3
  and 28:25.0). The transport stops right after A7 (27:43) and after B7 (56:13).
- **Floors:** recorded gaps and lead-ins −68.2…−68.6 dBFS at 300 Hz–6 kHz (−65.5…−66 at 6–20 kHz);
  capture chain with the transport stopped −87 dBFS, so the chain is ~19 dB under the tape's noise.
  Against the music's RMS (−17.8 dBFS) the 300 Hz–6 kHz floor is ~50.5 dB down; the chrome's was ~49 dB
  down (−69 per channel vs −20). So the recorded floor is about the same on both tapes relative to the
  music, which suggests it is set by the recording chain or bias noise rather than by the tape type.
  Different capture chains, so to be confirmed.
- Pipeline: `tracks.py` holds the metal tracks, source segments and noise stretches (the metal tape's few,
  short gaps are pooled across both sides); `splitsource.py` cuts the long source into
  `data/sources/MA1…MB7.flac` (24/48). `dynamics.py` and `investigate.py` now take the recorded-gap noise
  as their reference instead of the chrome's blank leader.
- Five songs are on both tapes (Join Me in Death, Iris, Shallow, I Miss You, Forever Young): same deck,
  same songs, different tape and capture chain.

### First comparison: Shallow on both tapes (metal MB2 via headphone jack vs chrome B3 via line out)
MB2 aligned: 94% of windows tracked, polarity inverted (as on the chrome), speed −0.019%, wow 0.026%,
flutter 4–20 Hz 0.041% (chrome: 0.019% / 0.012%). Gain at 1 kHz L −5.12 / R −5.79 dB (chrome −7.34 / −8.29).
Static response re 1 kHz, same source:
| | 31 Hz | 50 | 100 | 250 | 500 | 2.5k | 4k | 6.3k | 8k | 10k | 12.5k | 16k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| chrome L | −4.0 | −1.2 | −0.3 | −0.3 | −0.3 | +0.8 | +1.2 | +1.3 | +1.1 | +0.7 | +0.2 | −3.0 |
| metal L | −4.2 | −0.7 | +0.5 | +0.4 | +0.2 | −0.1 | −0.3 | −0.9 | −1.6 | −2.7 | −4.3 | −7.6 |
| metal R | −4.3 | −1.0 | +0.6 | +0.4 | +0.2 | −0.4 | −0.8 | −1.8 | −2.9 | −4.4 | −6.8 | −11.8 |
- **Does the headphone's impedance show?** (owner's question)
  - No resonance bump: metal minus chrome is flat within ~0.15 dB from 60 to 250 Hz (+0.73 / +0.88 / +0.73 /
    +0.76 / +0.80 / +0.78 dB at 63 / 80 / 100 / 125 / 160 / 200 Hz, L). The headphone amplifier's output
    impedance must be low (a few ohms at most), or the DT 770's peak would lift 80–100 Hz.
  - It shows in the bottom octave's phase: extra lead of +12° at 63 Hz, +20° at 40 Hz, +29° at 25 Hz, +37° at
    20 Hz. A single high-pass at ~15 Hz gives 13° / 20° / 30° / 36°: a ~330 µF output capacitor into 32 Ω.
    Magnitude: about −0.5 dB at 40 Hz, −1.3 at 25 Hz, −1.9 at 20 Hz. With 250 Ω headphones the corner would
    be ~2 Hz.
- **The metal capture has much less treble** than the chrome against the same source, and it is static:
  loud third minus quiet third of the song is 0.00 ± 0.06 dB at every frequency on the metal (the chrome
  loses 0.1–0.26 dB of treble when loud). So no saturation at all on the metal despite the hotter
  recording, and not a level-dependent process such as noise reduction. Candidates: the deck's bias / record
  equalisation not matching this tape, or the headphone path's own response. A LINE OUT take of one song in
  the same session would separate tape from playback path.
- A gentle tilt overall: +0.5 dB at 100 Hz falling to 0 at 1 kHz.

### The four shared songs on both tapes (`signature.py`; chrome via line out 2023 → metal via headphone jack 2026)
Metal alignment: MB2 94%, MB3 99%, MB7 100%, MA3 96% of windows tracked; polarity inverted in all four.
| song | speed dev % at 1.5–3 / 3–6 / 6–12 Hz | timing µs (8 kHz octave) at 24–48 / 48–96 / 192–384 / 768–1536 Hz | residual re signal 1k / 4k / 13k dB |
|---|---|---|---|
| Shallow | 0.018/0.010/0.009 → 0.015/0.013/0.025 | 3.08/1.89/1.17/1.21 → 2.53/2.12/1.94/2.03 | −26.0/−14.4/−3.9 → −21.8/−10.3/+0.8 |
| I Miss You | 0.025/0.008/0.005 → 0.013/0.010/0.017 | 2.55/2.11/0.80/1.08 → 2.19/1.93/1.05/1.41 | −27.7/−15.5/−4.9 → −24.2/−12.9/−2.0 |
| Forever Young | 0.025/0.007/0.018 → 0.014/0.010/0.013 | 2.84/2.19/1.21/1.55 → 2.74/2.08/1.16/1.44 | −24.1/−13.4/−3.1 → −25.8/−15.0/−2.2 |
| Join Me in Death | 0.024/0.011/0.019 → 0.018/0.019/0.026 | 3.25/2.23/1.64/2.31 → 2.91/2.28/1.18/1.66 | −21.6/−8.9/+3.2 → −19.4/−12.0/−0.9 |
- **The wobble is the deck's, not the tape's:** the flutter band at 24–96 Hz is the same on both tapes
  (2.2–3.1 and 1.9–2.3 µs). Fast jitter and capstan-rate flutter differ by song in both directions (Shallow
  +65% fast jitter on the metal, Forever Young equal, Join Me in Death less): the per-stretch variation
  again, no systematic tape-type effect. The 1.5–3 Hz roller wow is lower on the metal capture in all four
  (0.013–0.018% vs 0.018–0.025%): cleaned roller, thicker tape, or both.
- **Response, metal minus chrome, consistent in all four** (L): +0.5…+1.2 dB at 50 Hz, +0.7…+1.3 at 100 Hz,
  +0.7…+1.1 at 250 Hz, −1.5…−2.4 at 4 kHz, −2.7…−4.3 at 8 kHz, −4.4…−6.7 at 12.5 kHz. The metal capture is
  tilted: about +1 dB of bass and −4.5 dB at 12.5 kHz.
- **The 15 Hz high-pass of the headphone output is in all four:** extra phase lead +20…+21° at 40 Hz and
  +27…+30° at 25 Hz.
- **L–R delay** drifts along the side on both tapes: metal side B 31.5 → 19.9 → 17.1 µs (Shallow, I Miss You,
  Forever Young); Shallow reads 31.5 µs on both tapes. A property of the deck's tape path. Metal side A
  (Join Me in Death) −8.2 µs.
- **Join Me in Death is an outlier on the metal tape too** (speed +0.045% where the others are −0.009…−0.019%,
  wow 0.063% vs 0.015–0.026%, low window match at the start). Being odd on both tapes, at different
  positions, points at the source: Tidal's current version is probably a different transfer of the
  recording than the one taped in 2023. Keep it out of profiles.

### Owner: the metal capture through the Mac's headphone port "sounds perfect"
2026-11-17. Playback settings confirmed: selector on METAL, Dolby off. The owner played `metal-tape.flac`
through the Mac's headphone output, the same port on which the Tidal source had felt "dead and cold" after
the tape, and it "sounds perfect". So the character is in the captured signal (tape + deck + the Walkman's
headphone stage into the DT 770 load), not in listening from the Walkman as such: a file carries it, hence
an emulation that reproduces the file can. (This capture's response is tilted darker than the chrome's:
~+1 dB bass, −4.5 dB at 12.5 kHz.)

### Correction: the first metal fit diverged; two causes, both in the tooling
The first `calibrate.py` run on MB2 produced an emulation with tens of µs of timing per band and a residual
larger than the signal. Its listening set and profile are set aside as invalid
(`out/listening/MB2_INVALID_diverged_fit/`, `out/wmd6c_metalxr_INVALID_diverged.json`).
1. **`align.py` locked on late at the start of MB2** (11 s with jumps of 1–3 ms and missing windows): the
   coarse offset comes from seconds 5–25, and with this capture's 0.019% speed offset it is ~3 ms off at the
   start, outside the tracker's ±2.7 ms search; MB2 also starts at a joint with the previous song. Fixed by
   `align.refine_start` (a 4 s excerpt from the first seconds, ±30 ms): MB2 +6.29 ms, MA3 −8.88 ms, the
   others under 1 ms. `align.py` now prints a curve check and a WARNING if the tracker lost the signal, and
   `calibrate.py` stops when an emulation's alignment warns.
2. **The calibration's flutter rule above 6 Hz was wrong.** It matched the *tracked* speed deviation at
   6–20 Hz, but the tracker cannot follow wobble that fast (85 ms windows, 150 ms smoothing), so that reading
   is mostly tracker noise; added flutter went into the timing left after the warp instead, round after
   round. The rule now uses the tracked speed deviation below 6 Hz and the demodulated timing from 6 Hz up,
   with each step limited to ×0.5…×2. (On the chrome fit the old rule happened to settle; it left the
   3–12 Hz timing 25% low, which the new rule addresses.)
After re-aligning (all five songs: 98–100% tracked, no holes, steps ≤ 54 µs):
- **Shallow on the metal: unchanged**, so its numbers in the table above are real (6–12 Hz 0.023%, fast
  jitter 1.89 / 1.94 µs at 192–384 / 768–1536 Hz, residual −21.9 / −10.4 / +0.8 dB).
- **Join Me in Death on the metal: wow is normal** (0.012%; speed dev 0.007 / 0.014 / 0.024%, residual
  −24.0 / −12.0 / −0.9 dB). What remains odd is its speed: +0.045% where every other song is
  −0.009…−0.020%. That still points at a different transfer on Tidal, but it is no longer a wobble outlier
  on this tape; the row for it in the table above is superseded.
- The response tilt and the 15 Hz headphone high-pass were measured identically on MB3 and MB7, whose
  curves were clean throughout, and stand.
The metal profile is being refitted on MB3 (I Miss You: 99% tracked, no clipping).

### Metal profile fitted (`profiles/wmd6c_metalxr.json`, on MB3 I Miss You, 7 iterations)
With the pinned alignment start and the new flutter rule the fit converged (last round: transport ×1.00,
jitter ×0.89–1.01). MB3 tape vs emulation (`out/signature_MB3_final.txt`): speed deviation equal in every
band (6–12 Hz 0.017 vs 0.015%); timing in the 8 kHz octave 2.00 / 2.61 / 2.38 / 2.19 / 1.93 / 0.97 / 1.05 /
1.17 / 1.41 / 1.47 µs vs 2.10 / 2.66 / 2.40 / 2.17 / 1.92 / 0.99 / 1.14 / 1.26 / 1.50 / 1.55 µs (3–6 Hz …
1536–2800 Hz): within 5–8% everywhere, including 3–24 Hz, which the old rule left 25% low on the chrome;
timing L/R coherence matched; residual re signal within 0.6 dB per octave; response within 0.1 dB and 1°;
level per octave within 0.1 dB for L+R and L−R. Profile: transport 204 µs RMS (mostly slow drift), jitter
common 3.14 µs + per channel 1.81 µs, flicker 1.7–2.7% at 1–4 kHz and none above, no treble saturation
stage. Listening set with blind pair: `out/listening/MB3/`.

## 2026-11-17: the model in C++, and two things found while checking it

### The tape engine (`tape/`) reproduces the model
The engine is `emulator.py` v0.4 in streaming form (details and the full table in `tape/README.md`).
`verify_engine.py` on Shallow / chrome B and on I Miss You / metal, 60 s each at 48 kHz:
- **The arithmetic is exact.** With the wobble, jitter, flicker and noise the engine itself used
  (`korre-render --trace`), the Python chain gives the engine's output to −152 dB, the resolution of its
  32-bit float output, for every ingredient set tried. The two filter designs agree to 1e-16.
- **The random signals have the profile's spectra.** Transport over 20 minutes, RMS per band (0.05–0.5,
  0.5–3, 3–12, 12–30, 30–45 Hz): table 16.0 / 23.0 / 5.95 / 3.19 / 3.76 µs, engine 16.4 / 21.6 / 5.99 / 3.17 /
  3.65 µs; lines at 1.66, 7.52, 30.11 and 43.56 Hz (table 1.65, 7.53, 30.10, 43.58). Jitter within 4% per
  band, flicker at unit RMS, noise within 0.25 dB per octave from 45 Hz up (0.1 dB from 180 Hz up). Signals that should be independent
  are uncorrelated (|r| < 0.02) and Gaussian (kurtosis 2.98–3.04).
- **A full engine render of Shallow measures like the tape** (`align.py` + `signature.py` on `B3cpp`):
  speed deviation within 0.001% in every band, timing within 0.35 µs per band, residual re signal
  −26.2 / −21.7 / −14.6 / −9.0 / −3.9 dB (tape −26.1 / −21.3 / −14.3 / −8.7 / −3.9), response within 0.1 dB
  above 60 Hz.
- **Where it differs by design: the static response.** The model applies the measured table with one FFT
  as long as the track. The table's fine ripple (24 points per octave of measurement noise) is energy up to
  seconds before and after time zero; the engine's filter keeps 11.6 ms before and a third of a second
  after. Against the whole-track response: −28 dB in 20–60 Hz, −36 dB in 60–200 Hz, −54 dB in 0.2–2 kHz,
  below −68 dB above; −38.5 dB overall on Shallow. In the signature that is 0.3 dB at 30 Hz and 0.4 dB at
  50 Hz on the right channel. A tape chain is causal, so the part before time zero was never physical.
  (A first table in `verify_engine.py` put the transport's 0.05–0.5 Hz band at 20.9 µs "by the table"; that
  was the script integrating a linear interpolation across the table's steep first points. Summing the
  points gives 16.0, and a whole-run Python synthesis reads 15.2–16.5.)

### The treble-saturation stage adds amplitude flicker in the mids that the tape does not have
The first engine render showed more AM than the old Python render around 1–2 kHz, common to both channels.
It is not the port: a fresh Python render with the current profile (`B3py4`) reads the same. The profile
gained `saturation.hf` after the v0.3 render was made, and this is that stage.

| AM % RMS at rates 3–6 / 6–12 / 12–24 / 24–48 / 48–96 / 96–192 Hz | 1 kHz octave | 2 kHz octave |
|---|---|---|
| tape | 0.12 / 0.15 / 0.20 / 0.29 / 0.36 / 0.41 | 0.18 / 0.24 / 0.33 / 0.50 / 0.57 / 0.60 |
| Python v0.3 (no treble saturation) | 0.13 / 0.18 / 0.23 / 0.32 / 0.35 / 0.37 | 0.21 / 0.30 / 0.40 / 0.55 / 0.58 / 0.53 |
| Python v0.4, current profile | 0.20 / 0.24 / 0.29 / 0.38 / 0.45 / 0.52 | 0.28 / 0.35 / 0.44 / 0.60 / 0.66 / 0.68 |
| C++ engine, current profile | 0.21 / 0.24 / 0.29 / 0.38 / 0.46 / 0.53 | 0.29 / 0.35 / 0.46 / 0.59 / 0.67 / 0.68 |

AM L/R coherence at 1 kHz, 3–6 Hz: tape 0.13, v0.3 0.10, v0.4 0.38, engine 0.39. The stage bends the whole
pre-emphasised signal with one cubic, so loud treble also turns the mids down a little, in both channels
at once; on the tape the loss stays in the treble. From 4 kHz up the three renders and the tape agree
within 10%. The stage was fitted on the treble bands only (`satfit.py`), where it predicts well; a version
that leaves the mids alone (the cubic on the treble band only, or a smaller shelf with a larger
coefficient) is the thing to try. Size of the excess: 0.1–0.15% RMS, about 0.01 dB.

### Correction: the metal profile held a 65.3 Hz "deck tone" that is a bass note
`wmd6c_metalxr.json` listed a steady tone at 65.30 Hz, −63.6 / −64.0 dBFS, in phase in both channels.
The engine check showed it as 7 dB of extra background in the 45–90 Hz octave. It is not on the tape:
- In the four silences recorded between songs on the metal tape the level at 65.3 Hz is −89…−112 dBFS, at or
  below the neighbouring frequencies. The 7.55 Hz capstan tone is in every one of them (−88 dBFS, 12 dB above
  its neighbours).
- Through the songs the level at 65.3 Hz runs from −42 to −94 dBFS with the music, as 62.3 and 68.3 Hz do.
65.4 Hz is the note C2. `steady_tones()` takes the 10th percentile over 20 s segments, which removes a note
one song holds; this one is common enough across side B's seven songs to survive, and in whole-side mode
the source is not consulted. Side A does not show it.
- **Fix:** `steady_tones()` now keeps a tone only if it is also there in the recorded silences, within 10 dB
  of its level (`in_recorded_silence`). The chrome profiles' tones (7.55, 43.55, 50.00 Hz on side B; 7.5 Hz
  on side A) pass; the metal keeps 7.55 Hz alone.
- **The first metal listening set had the tone in its emulation** and is set aside as
  `out/listening/MB3_INVALID_false_65Hz_tone/`. At −64 dBFS and 65 Hz it sat near the threshold of hearing
  under music, but it was a difference the tape does not have. The set in `out/listening/MB3/` is rendered
  again from the corrected profile with a new seed: speed deviation within 0.003% per band, timing within
  7%, residual within 1 dB, response within 0.1 dB and 1°, level per octave within 0.1 dB.

## 2026-11-18: gain noise. The left channel's level wobbles more, on both tapes

Looking for where the metal emulation is weakest (`signature.py`, per channel instead of the mean of both):

### The left channel has about 1.5 times the right's amplitude modulation at 1-2 kHz
AM % RMS at rates 12-384 Hz, left over right, and the same ratio for the timing:

| song | tape | AM L/R at 1 / 2 / 4 kHz | timing L/R |
|---|---|---|---|
| I Miss You | metal (MB3) | 1.50 / 1.50 / 1.13 | 1.08 / 1.10 / 1.02 |
| I Miss You | chrome (A5) | 1.31 / 1.63 / 1.27 | 1.08 / 1.10 / 1.02 |
| Shallow | metal (MB2) | 1.30 / 1.24 / 1.11 | 1.01 / 1.05 / 1.03 |
| Shallow | chrome (B3) | 1.01 / 1.06 / 1.05 | 0.98 / 1.03 / 1.01 |
| Forever Young | metal (MB7) | 1.46 / 1.38 / 1.17 | 1.04 / 1.08 / 1.04 |
| Forever Young | chrome (A6) | 1.52 / 1.39 / 1.20 | 1.02 / 1.06 / 1.03 |
| Join Me in Death | metal (MA3) | 2.04 / 1.53 / 1.19 | 1.03 / 1.02 / 1.01 |
| Join Me in Death | chrome (A2) | 1.35 / 1.19 / 1.07 | 1.03 / 1.04 / 1.02 |

Seven of eight, on both tapes and both capture chains, so it belongs to the deck and the format: on a
cassette the left track is the one along the tape's edge. The model had the same flicker depth for both
channels, so the emulation was symmetric: on MB3 its residual at 1 kHz was 1.0 dB too clean on the left
(−24.9 against −23.9 dB) and right on the right.

### It multiplies the signal (`levelsplit.py`)
AM % at 96-384 Hz in the 1 kHz octave, in 85 ms blocks sorted by the band's own level (quietest to
loudest sixth, a 19 dB range):
- metal I Miss You, left: 2.01 1.72 2.04 1.96 1.64 1.56. Flat: it scales with the signal.
- the same, right: 1.69 1.34 1.34 1.23 1.05 0.92. Falls with level, as added noise does.
- the emulation (v0.4), both channels: 1.72 … 0.86 and 1.81 … 0.80. Added noise only, as built.
Forever Young on the metal: left flat at 1.2-1.3%, right 1.07 … 0.86. It reaches down to the 250 Hz octave
(there, at 24-80 Hz: left 0.8-1.0%, right 0.5-0.8%). Chrome Shallow, the exception in the table above, falls with
level in both channels.

### It is one gain for the channel up to about 200 Hz, and something else above (`crossband.py`)
Coherence of the demodulated AM between octave bands of the left channel, rates 3-12 / 12-48 / 48-96 /
96-192 / 192-340 Hz: 1 with 2 kHz 0.42 / 0.40 / 0.34 / 0.29 / 0.11; 2 with 4 kHz 0.58 / 0.54 / 0.47 / 0.38 /
0.16; 1 with 4 kHz 0.22 / 0.23 / 0.22 / 0.24 / 0.10. An emulation with no gain shared between those bands
(the one rendered at that point: the first, rejected version of the new ingredient) reads 0.05, 0.04, 0.03
at 96-192 Hz.
So neighbouring bands move together up to ~200 Hz and not above. (The same script shows no coherence of
the *timing* between bands above 96 Hz, on the tape and equally on the emulation, whose jitter is a true
time shift: the estimator cannot tell there, and nothing follows from it.)

### Model v0.5: gain noise (`emulator.py`, `tape/`, profile section `gain_noise`)
A wobble of each channel's level as a whole: one random gain per channel, the same depth at every
frequency, rate spectrum flat to 150 Hz and gone by 600 Hz, a depth per channel. It sits with the flicker
(same switch). A first version with a spectrum running on as 1/f to 4 kHz was rejected by the calibration
itself: at those rates the gain spreads the strong bass into the higher bands as noise, and the fit pulled
the depth back to nothing.
Fitted on MB3 (`profiles/wmd6c_metalxr_v2.json`; `calibrate.py --gain-noise --engine`, three rounds on
flicker and gain noise, four on everything but the response): **gain noise 2.3% RMS left, 0.95% right.**
Tape against emulation, before (v1, seed 2) and after (v2):

| | tape | v1 | v2 |
|---|---|---|---|
| residual at 1 kHz, L / R, dB | −23.9 / −24.5 | −24.9 / −24.7 | −23.9 / −24.7 |
| residual at 2 kHz, L / R, dB | −18.4 / −19.0 | −18.9 / −19.1 | −18.5 / −19.0 |
| AM % at 1 kHz, 96-192 Hz, L / R | 1.09 / 0.65 | 0.62 / 0.60 | 1.12 / 0.63 |
| AM % at 2 kHz, 96-192 and 192-384 Hz, L | 1.14, 1.15 | 0.74, 0.83 | 1.15, 1.07 |
| AM % at 2 kHz, 96-192 and 192-384 Hz, R | 0.71, 0.71 | 0.68, 0.71 | 0.69, 0.69 |
| timing at 8 kHz, 384-2800 Hz, us | 1.17 1.41 1.47 | 1.24 1.47 1.52 | 1.21 1.44 1.50 |
| timing at 1 kHz, 3-12 Hz, us | 2.71 3.25 | 2.56 2.92 | 2.72 3.14 |

In the refit the flicker moved as well: at 1-4 kHz down to 0.8 / 1.6 / 1.3% (the gain noise took its place),
and at 13 kHz up from nothing to 9%, while the fast jitter came down 3-7%. Those two trade against each
other at 13 kHz (timing makes AM there too); the AM at 13 kHz matches within 5% in both channels either way.

Still not modelled: the left's extra timing at 1-2 kHz (8-10% above the right; not a time shift, since it
is absent at 4-8 kHz); AM on the right at 4 kHz, 96-192 Hz (1.03 against 1.23%); and whatever the
modulation above ~200 Hz is. The chrome profiles have no gain noise yet, though side A shows the same
left-right difference.

Listening set from v2, rendered with the C++ engine: `out/listening/MB3_v2/` (seed 3; `out/listening/MB3/`,
the v1 pair the owner has yet to hear, is untouched). Measured: speed deviation within 0.002% per band,
residual within 0.6 dB per octave (−24.2 / −25.1 dB at 1 kHz against −23.9 / −24.5), response within 0.1 dB
above 100 Hz. At 30 Hz it rolls off 0.4-0.5 dB less than the tape and the left-minus-right signal in the
31.5 Hz octave is ~1.2 dB stronger: the engine's short response filter (`tape/README.md`), which a set
rendered by `emulator.py` does not have. Fitting the response table through the engine would remove it.

## 2026-11-18 (later): two blind tests, Shallow on the metal tape, and steady flutter lines (model v0.6)

### Fifth and sixth blind tests (owner, DT 770): the first metal pair told apart, the refined one not
- `out/listening/MB3/blind` (metal v1, no gain noise): **the tape was identified fast.** The tell, in the
  owner's words: after 1:15 ("Where are you, and I'm so sorry", fingers sliding on the frets in the
  background) the emulation "is much more well separated" than the tape. The same family as the earlier
  tells (Shallow v0.2: the piano too separated behind the loud vocal; A5: the fret slide sharper).
- `out/listening/MB3_v2/blind` (metal v2 with gain noise, rendered by the C++ engine): **not identified**
  (the owner took the emulation for the tape, "had to go on intuition"). One trial. v2 differs from v1 by
  the gain noise, the refit of flicker and jitter around it, and the engine; the gain noise is the change
  aimed at that tell, so it is the likely cause, not a proven one.
- The owner asked for a blind test on Shallow, the song they know best.

### The I Miss You profile on Shallow, unchanged: too clean
`wmd6c_metalxr_v2` (fitted on MB3) rendered on MB2 with only the record level changed
(`out/signature_MB2_xsong_v2.txt`), tape against emulation:

| | 1 kHz | 2 kHz | 4 kHz | 8 kHz | 13 kHz |
|---|---|---|---|---|---|
| residual, tape, L / R dB | −21.9 / −21.9 | −17.2 / −17.4 | −10.3 / −10.5 | −4.4 / −4.5 | +0.9 / +0.6 |
| residual, emulation | −23.3 / −23.6 | −19.0 / −19.2 | −12.1 / −12.0 | −6.4 / −6.4 | −1.9 / −2.0 |

Shallow's stretch simply wobbles more than I Miss You's, which follows it on the same side: timing
at 6-12 Hz 5.42 against 3.25 µs (the capstan's line, 1.7 times), fast jitter 1.3-1.7 times, treble AM about
twice. The static response differs a little too (0.2-0.8 dB at 30 Hz and 14 kHz; the delay between the
channels 31.4 µs against 19.8). So, as on the chrome tape, wobble depth belongs to a stretch of tape, not
to the tape.

### A profile for Shallow's stretch, and where the fit got stuck
`calibrate.py --init --base P` (new) starts a profile from the song's own response, levels, slow wobble
and dropouts, and takes fast jitter, flicker, gain noise, noise and tones from a fitted profile of the same
tape. Five rounds through the engine left the emulation 0.5-0.9 dB rougher than the tape at 1-4 kHz and
0.3-0.7 dB cleaner at 13 kHz, with the flicker depth at 13 kHz climbing to 39%.
Ingredients switched off one at a time (same draw): the gain noise is worth 0.1-0.2 dB of the residual at
1 kHz and the fast jitter 0.2-0.4 dB. The rest is slow wobble left after the alignment's warp.

### The slow flutter in fine steps
The signature's timing bands are 2.9 Hz bins: "3-6 Hz" and "6-12 Hz" are both mostly the capstan's 7.5 Hz
line, seen through the analysis window. `signature.py` now also keeps the timing left after the warp in
0.125 Hz steps (1, 2 and 4 kHz octaves). Tape against the emulation of round 5, µs RMS at 1 kHz:

| band, Hz | 3-4 | 5-6 | 7.2-7.8 | 8.4-10 | 10-12 | 14.5-15.7 | 18-21 | 31-36 | 48-60 | 60-80 |
|---|---|---|---|---|---|---|---|---|---|---|
| tape | 1.50 | 1.68 | 6.18 | 1.51 | 1.72 | 1.81 | 1.40 | 0.96 | 1.99 | 1.12 |
| emulation | 1.89 | 1.91 | 7.00 | 1.34 | 1.41 | 1.41 | 1.58 | 1.12 | 1.42 | 1.66 |

The octave-wide rule had traded a capstan line that was 9-13% too strong against too little beside it. The
calibration now corrects the transport from 6 Hz up in fine steps (quarter-octave smoothing, on the 1-4 kHz
octaves), adds tracked and left-over timing at 3-6 Hz, and uses the tracked speed deviation below 3 Hz.
One round brought the mids within 0.2 dB. (48-96 Hz belongs to the jitter table, which has one point per
octave there and cannot follow this: in round 5 the 48-60 Hz band was 29% low and 60-80 Hz 48% high. Open.)

### The flutter lines fade in the emulation and hold steady on the tape
A second draw of the same profile (seed 4) then measured 1.2-1.5 dB cleaner than the tape at 8-13 kHz
while the draw used for fitting matched. With the transport alone (no jitter, flicker or noise) the slow
timing already read differently by octave, in µs at 3-6 Hz:

| | 1 kHz | 2 kHz | 4 kHz | 8 kHz | 13 kHz |
|---|---|---|---|---|---|
| tape | 4.88 | 4.37 | 4.49 | 4.30 | 4.06 |
| emulation, transport only, seed 4 | 4.80 | 3.95 | 3.89 | 3.03 | 2.37 |

A time shift is the same number of microseconds at every frequency, so that fall is the measurement
saturating: at 13 kHz a shift of 20 µs is 1.6 radians. It saturates when the wobble comes in bursts. The
7.5 Hz line's level in 10 s steps through the song (2 kHz octave, µs peak):

| | first 80 s | the loud second half |
|---|---|---|
| tape | 1.1 2.1 1.5 2.2 1.4 0.8 2.5 2.1 | 4.2 5.1 7.8 6.8 5.9 4.1 6.6 8.2 7.9 8.0 7.4 |
| emulation, seed 4 | 0.4 1.1 0.6 1.1 0.6 0.3 3.1 1.2 | 0.7 2.8 7.8 2.4 2.2 2.7 11.1 11.5 7.8 1.6 1.4 |
| emulation, seed 1 | 0.3 0.9 1.6 0.5 0.5 0.3 1.1 1.7 | 2.0 2.3 3.5 4.6 9.8 6.1 5.7 11.9 10.8 3.4 1.8 |

On the tape the capstan's flutter is steady. In the emulation it swings between nothing and one and a
half times the tape's, differently in every draw. The cause is how a line is made: as a narrow peak in a
noise spectrum. Narrow-band noise has a level that wanders (over the peak's width in the model, over each
44 s block in the engine), and the peak's width in the table is the measurement's resolution, not the
deck's. The fit had been making up for it with flicker: 41% at 13 kHz.
(The low readings in the first 80 s are the measurement following the music's level: the steady-line
emulation below shows them too.)

### Model v0.6: steady lines (`transport.lines`)
A profile can list the wobble's lines apart from the noise table, each a frequency and an RMS level; the
model and the engine generate them as sines of constant level with a random starting phase.
`calibrate.py --lines` moves the table's narrow peaks into lines (a peak 20 times above the spectrum around
it, at most 0.45 Hz wide, at least 0.5 µs; peaks closer than 0.12 Hz are one line) and corrects each line
with the table's correction at its frequency. Shallow's stretch: 17 lines, among them the pinch roller at
1.67 Hz (14.3 µs) with harmonics at 3.34 and 5.01 Hz, the capstan at 7.53 Hz (11.6 µs) with 15.05,
22.58, 30.10 and 37.63 Hz, and 18.25, 25.54, 32.84 and 43.58 Hz from the motor.
After four rounds (`profiles/wmd6c_metalxr_v2_MB2.json`), tape against emulation:

| | 1 kHz | 2 kHz | 4 kHz | 8 kHz | 13 kHz |
|---|---|---|---|---|---|
| timing 3-6 Hz, µs: tape | 4.88 | 4.37 | 4.49 | 4.30 | 4.06 |
| the draw fitted on (seed 1) | 4.98 | 4.47 | 4.55 | 4.18 | 3.92 |
| another draw (seed 4, the listening set) | 4.55 | 4.02 | 4.20 | 4.02 | 3.86 |
| residual, L / R dB: tape | −21.9 / −21.9 | −17.2 / −17.4 | −10.3 / −10.5 | −4.4 / −4.5 | +0.9 / +0.6 |
| seed 1 | −21.9 / −21.8 | −17.1 / −17.1 | −10.2 / −10.1 | −4.5 / −4.5 | +1.0 / +1.1 |
| seed 4 | −22.4 / −22.4 | −17.6 / −17.9 | −10.6 / −10.6 | −4.5 / −4.6 | +1.0 / +0.8 |

The timing now reads alike at every octave, the two draws sit within 0.5 dB of the tape on either side,
and the flicker depth fell back to 1.8 / 0.6 / 3.2 / 5.7% at 2 / 4 / 8 / 13 kHz (gain noise 1.9% left,
1.0% right). The 7.5 Hz line through the song, seed 4: 0.9 1.9 1.6 1.9 1.4 0.9 2.2 1.5 | 3.6 4.2 6.8 5.7
5.1 3.9 5.5 7.2 6.4 8.2 7.0, the tape's course about 12% lower.
`verify_engine.py` on this profile: the engine against the Python chain run with the engine's own control
signals, −151.9 dB as before; the wobble per band (table plus lines, against 20 minutes of the engine's
transport) 17.59 / 13.32 / 3.78 / 2.99 µs against 17.18 / 13.38 / 3.78 / 2.98 at 0.5-3 / 3-12 / 12-30 /
30-45 Hz; the strongest lines at 1.66, 7.52, 30.11 and 43.58 Hz (profile: 1.67, 7.53, 30.10, 43.58).
Not done: the other profiles still carry their lines as noise peaks (`--lines` and a few rounds each);
the left-right wobble's lines; whether the lines' level really is constant or drifts slowly (the tape's
10 s means vary by about 15%, some of it the music).

### The engine's bass response: not a matter of filter length
The engine's response filter differs from the profile's table by −18 to −27 dB at 20-30 Hz. Doubling or
quadrupling its length changes nothing; reproducing the table there needs hundreds of milliseconds
*before* time zero (500 ms for −39 dB). That part of the table is ripple between its measured points, not
the deck, which cannot answer before it is asked. The engine stays as it is.

A profile fitted through the engine can absorb the difference, but only as a smooth trend. The first such
fit corrected every 1/24-octave point: the filter cannot take up detail that fine in the bass, so each
round asked for it again and added it again (the largest correction stayed at 0.3-0.6 dB for 13 rounds).
The table ended up to 3-4 dB off the song's own measurement at single points below 100 Hz, with the
engine's output still right (it ignores the ripple) and `emulator.py`, which applies the table exactly,
11.5 dB down on the engine in the 20-60 Hz band instead of the usual 28 (`verify_engine.py`, check 4).
The calibration now smooths its response corrections over half an octave below 150 Hz
(`smooth_response_step`). This profile's table was reset to the measurement there and refitted for three
rounds: it is within 0.2 dB of the measurement from 30 Hz up (1 dB lower at 20-30 Hz on the left), and
the engine's output is within 0.2 dB of the tape from 30 Hz to 14 kHz (the I Miss You set: 0.4-0.5 dB at
30 Hz).

### Listening set
`out/listening/MB2/` (seed 4, engine render, README with the figures above; blind pair). The capture
clipped in three moments of this song (23 samples, left); `render.py` now gives the emulated files the
same ceiling at the capture's level for tracks marked `clipped` (28 samples cut). An earlier set with
fading lines is kept as `out/listening/MB2_INVALID_fading_flutter_lines/`.
