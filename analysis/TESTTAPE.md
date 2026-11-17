# Test-tape session (v2)

Goal: measure the WM-D6C + metal tape the way you actually listen to it (headphone out
driving the DT 770 Pro 32 Ω), with battery type as a controlled variable.

The signal: `analysis/out/testtape_v2.wav` (7.4 min, 24-bit/96 kHz; regenerate with
`python testsignal.py`). Its sections and exact timings are in `out/testtape_v2.json`:

| time | section | measures |
|---|---|---|
| 0:05 | 3 chirps | start marker (alignment, average speed) |
| 0:09 | 1 kHz, 20 s | **read the record meter here** |
| 0:30 | 20 s silence | hiss with bias on |
| 0:50 | 3150 Hz, 60 s | wow & flutter (standard test tone), incl. fast flutter |
| 1:51 | 10 kHz, 30 s, -20 dBFS | treble flicker (head contact) and scrape flutter, seen directly |
| 2:23 | 7 sweeps, -36 → -1 dBFS | frequency response + distortion at each level |
| 3:33 | sweep L only, R only | per-channel response, crosstalk |
| 3:53 | stepped tones 100 Hz–12.5 kHz, -30 → -1 dBFS | compression and distortion vs level |
| 5:07 | bass bursts under a quiet 3150 Hz tone | does loud bass (current draw, battery sag) wobble everything else? |
| 5:45 | two-tone tests | intermodulation |
| 6:07 | pink noise, 4 levels, independent per channel | full L/R transfer, treble compression on a music-like spectrum |
| 7:15 | 3 chirps | end marker |

## You need

- **Recording path (same as the 2023 songs):** Mac → USB → Yamaha A-S801 (tone controls
  bypassed) → Yamaha headphone out → Walkman **LINE IN**, with a Bespeco ROCKIT stereo cable
  (6.3 mm TRS → 3.5 mm TRS, 1.5 m). Set the Yamaha's USB input to **96 kHz** in Audio MIDI Setup.
- **Capture path:** the USB interface (Behringer UMC202HD), **96 kHz / 24-bit**. Both input
  switches on **LINE** (not INST), pad off, direct monitoring off. Walkman headphone out →
  Bespeco AD140 splitter (3.5 mm male → 2× 3.5 mm female) → DT 770 on one branch, Klotz
  AY5-0200 (3.5 mm stereo → 2× 6.3 mm TS, 2 m) into inputs 1/2 on the other.
- Adam Hall 4 STAR A MF3 JM3 adapter (6.3 mm stereo male → 3.5 mm stereo female), for the
  Yamaha loopback in step 0 and the Yamaha headphone-impedance test.
- A USB-C ↔ USB-B cable (or a USB-C → USB-A adapter) for the MacBook Air
- DT 770 Pro 32 Ω (as the load, see the safety note)
- A spare **metal** tape (one side of a C60 holds both copies)
- **Two battery sets:** fresh standard Duracell alkalines and charged NiMH
- A multimeter, if you have one
- Audacity (or anything that can play one file while recording another)

**Safety:** the sweeps, stepped tones and bass bursts are loud and unpleasant. Keep the
headphones plugged into the splitter as the load, but **don't wear them** during the
session. Hold a cup near your ear briefly if you want to check.

**Mac hygiene:** route alert sounds to the built-in speakers (System Settings → Sound →
"Play sound effects through"), turn on Do Not Disturb, quit other audio apps. Otherwise a
notification ping can end up on the tape.

## Walkman settings

Tape type **METAL**, Dolby **OFF**, record level on **manual**, any limiter or auto-level
**off**. If you usually repack tapes (fast-forward and rewind once before recording), do it.

## Steps

**0. Yamaha loopback (do it after step 1, when the Yamaha volume is set).** Yamaha
headphone out → adapter → splitter → DT 770 + Klotz into the interface. Play the test file
through the Yamaha and record it → `yamaha_loaded.wav`. Then unplug the DT 770 from the
splitter and repeat → `yamaha_noload.wav`. This gives the recording path's own sound,
which we subtract from the tape measurements (and shows whether the ~1 dB L/R imbalance is
the Yamaha's volume control). The loaded/unloaded pair tests the Yamaha + DT 770
impedance hypothesis.

**1. Set levels with music, then don't touch the knobs.** Alkalines in. Play a loud
passage of a song (e.g. the end of Shallow) from the Mac through the Yamaha. Set the
Yamaha's volume and the Walkman's record level the way you'd normally record music. **Write
both positions down.**

Also set the Walkman's **headphone volume** to your normal listening level and mark it.
Set the interface **input gain** so the loudest parts (sweeps near -1 dBFS, bass bursts)
peak below about -3 dBFS on the capture. Keep all of these fixed for the whole session.

**2. Record copy A (alkaline).** Measure each cell's voltage before inserting. Start
recording on the Walkman, then in Audacity play the test file while recording the
interface inputs (Audacity: playback device = the Yamaha, recording device = the interface). During recording the Walkman's headphone out should carry the input
signal through its electronics, without the tape, so this capture is free data
→ `rec_monitor_alk.wav`. Note the meter reading during the 1 kHz tone.

**3. Record copy B (NiMH).** Leave ~5 s of gap, swap to the NiMH set (measure voltages),
same knobs, record the test file again → `rec_monitor_nimh.wav`.

**4. Playback, loaded.** Rewind. With **fresh alkalines**, play back the whole side
(copy A + copy B) while capturing the headphone out with the DT 770 on the splitter →
`play_alk.wav`. Then the same with **NiMH** → `play_nimh.wav`. Same headphone volume.

**5. Playback, unloaded.** Alkalines, **headphones unplugged** from the splitter, play
copy A only → `play_alk_noload.wav`. Compared with step 4, this shows how the headphone amp
reacts to the 32 Ω load.

**6. The songs.** Your metal tape with the mixtape: capture both sides with alkalines,
loaded → `songs_metal_A.wav`, `songs_metal_B.wav`.

**7. Batteries out:** measure each cell again.

Save captures as WAV, 96 kHz, 24-bit or 32-bit float, stereo, into a folder outside the
repo (e.g. next to the old capture, `tears/session2/`). They get linked into `data/`.

## Log sheet

```
date / time:
tape (brand, type, length):
Yamaha volume:                    Walkman REC level:         Walkman headphone volume:
interface input gain:
meter reading during 1 kHz tone (copy A / copy B):
alkaline cell voltages  before: _____ _____ _____ _____   after: _____ _____ _____ _____
NiMH cell voltages      before: _____ _____ _____ _____   after: _____ _____ _____ _____
pack voltage during loud playback (if measured), alkaline / NiMH:
anything odd (clicks, dropouts, a capture redone):
```
