# The player

`kora`: the terminal interface. It keeps the look of the original korre and sits on the playback
core (`../playback/`), which does the decoding, the tape engine and the audio.

```
kora [options] [file or playlist ...]

  --play              start playing the first track at once
  --profile NAME      the tape to play through: a file in the profiles folder (with or without
                      .json), a path to a profile, or "none"
  --profiles DIR      the folder of tape profiles (default: ./profiles, or the one next to the program)
  --dir DIR           the folder the file selector opens in (default: the current folder)
  --device NAME       the output device: its number, or part of its name; "none" plays to nowhere
  --list-devices      print the output devices and exit
```

The mouse works everywhere; `q` quits.

## The tape controls

They are in the DSP panel of the player window:

```
╒══╡DSP╞═══════════╕
│ wmd6c_xlii_sideB │   the profile in the deck ("no tape": the file as it is)
│  ◀  TAPE 4/4  ▶  │   step through the profiles; also in the Tape menu
│ █ EQ     █ SAT   │   the parts of the model, each with a lamp (green: on)
│ █ WOW    █ L-R   │     EQ   static response and phase     SAT  saturation
│ █ JIT    █ FLK   │     WOW  slow transport wobble         L-R  slow left-right timing difference
│ █ DRP    █ HISS  │     JIT  fast timing jitter            FLK  amplitude flicker and gain noise
│ pk -17.9 dB      │     DRP  dropouts                      HISS noise and the deck's steady tones
╘═══════╡ Bypass╞══╛   the level going out, and CLIP when a sample hit full scale
```

Bypass plays the file as it is at the same level and in the same place, for comparing. With a tape
in the deck both paths are 6 dB down, because the tape's phase rotation raises the peaks of loud
masters (see `../playback/README.md`).

## Files

| file | what |
|---|---|
| `main.cpp` | the command line |
| `app.*` | the application: menu bar, the frame loop, what happens when a track ends or will not open |
| `player_window.*` | the main window: track details, tape controls, transport, position, spectrum |
| `queue_window.*`, `play_queue.*` | the queue window, and the order of play behind it (no interface code, tested) |
| `file_window.*` | the file selector |
| `tape_shelf.*` | the profiles on offer and which one is in the deck |
| `spectrum.*` | the spectrum display's numbers: 152 points from 20 Hz to 20 kHz on a dB scale, each analysed with the shortest window that resolves it (tested) |
| `braille.*` | a curve drawn in Braille dots, 2 x 4 per character cell (tested) |
| `frame.*` | the double-line window frame |

## What changed from the original, on purpose

- **The spectrum** is on a fixed decibel scale (0 on the plot is -72 dB in a point's band, 1 is -12 dB,
  a full-scale sine being 0 dB), on points evenly spaced in pitch, matching the printed axis. The
  original normalised every frame to its own strongest bin on a linear scale, without a window (the
  code had one, switched off), so quiet and loud passages looked the same.
  - *Each point has its own window length*: about 5 ms at the top of the treble, where a point is
    hundreds of Hz wide, up to a sixth of a second in the bass, where it is a few Hz wide. So the
    treble follows the music at once and each point there moves on its own, while the bass moves
    slowly and several points together (below about 190 Hz a point is narrower than any window of
    that length can resolve). There is no hold and no smoothing over time.
  - *It is drawn in Braille dots*, two points per character cell across and four per row: 152 x 68
    in the 76 x 17 box, where the plot widget drew one thick cell per point.
  - The first version of this rewrite used one window of a sixth of a second for every point, let
    the points fall at 36 dB per second and spanned 72 dB with the band's whole power: the treble
    was as slow as the bass, everything stayed up, and the picture was a broad arc. The owner
    spotted it on first use (2026-11-18).
- **Shuffle** reorders the tracks to come and leaves the one that is playing alone; switching it off
  puts the remaining tracks back in the order they were added. The original reloaded the first track,
  which stopped the music, and restored a snapshot that forgot what had been played or added since.
- **A file that will not open** is reported in the menu bar and skipped. The original ended with an
  uncaught exception.
- **The file selector** opens in the current folder (or `--dir`), sorted; the original had one
  person's folder written into it and stopped at start-up when that folder did not exist.
- **Normalize** scans the file for its peak when the track is loaded, since tracks are no longer
  decoded into memory first.
- Changing the output device no longer stops playback.
- Data size and duration are shown with two decimals.
