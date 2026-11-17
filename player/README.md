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
│ █ DRP    █ HISS  │     JIT  fast timing jitter            FLK  amplitude flicker
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
| `spectrum.*` | the spectrum display's numbers: 100 columns from 20 Hz to 20 kHz on a dB scale (tested) |
| `frame.*` | the double-line window frame |

## What changed from the original, on purpose

- **The spectrum** is on a fixed decibel scale (0 on the plot is -78 dBFS in a band, 1 is -6 dBFS)
  with a Hann window and bands evenly spaced in pitch, matching the printed axis. The original
  normalised every frame to its own strongest bin on a linear scale, without a window (the code had
  one, switched off), so quiet and loud passages looked the same; and with its plot geometry a column
  at zero lands on the axis labels.
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
