# Playback

One track at a time from a file to the sound card, with the tape engine in the path.
No user interface in here, and the sound card sits behind a small interface (`korre::audio_output`),
so the whole path runs in tests without sound.

```
caller's thread          decoder thread                      audio thread
(the interface)          (inside korre::playback)            (the sound card's callback)

load / play / pause  ->  read 256 frames from the file
seek / set_profile       -> tape engine -> chunk         ->  copy chunks to the device
                              |                               apply the level, hold at full scale
position, levels   <----------+------ atomics <-------------  position, peak, clip count
spectrum samples   <------------------ lock-free queue <----  the samples just played
```

- **The audio thread only copies.** It never decodes, takes a lock or allocates, so a slow disk or a
  busy interface cannot make the sound stutter. In the original player the callback pulled every
  sample through a chain of virtual calls and ran the spectrum FFT itself.
- **The decoder thread stays about 150 ms ahead.** It reads the file in pieces (`audio/`), so a track
  starts at once and a long file never has to fit in memory. The original decoded the whole file first.
- **A seek is one atomic increment.** Every chunk in the queue carries the position in the track of
  its first frame and an epoch number. Seeking raises the epoch; the audio thread drops chunks from
  an older epoch as it meets them. No thread waits for another, and the position shown is always
  that of the audio really being played.
- **The engine's delay is hidden.** After a seek the engine's first 37 ms of output are dropped, and
  at the end of a file silence is fed in until the whole track has come out, so positions are the
  file's with or without a profile.
- **Level.** With a profile loaded the engine makes up the record gain, so tape and bypass are equally
  loud, and both are lowered by a headroom of 6 dB: the tape's phase rotation raises the peaks of
  loud modern masters by about 5 dB at the same loudness. Without a profile the file plays untouched.
  Samples over full scale are held there and counted.

| file | what |
|---|---|
| `include/korre/playback.h`, `src/playback.cpp` | the player core |
| `include/korre/audio_output.h` | the sound card as an interface; `manual_output` for tests |
| `include/korre/portaudio_output.h`, `src/portaudio_output.cpp` | the real one, through PortAudio |
| `include/korre/spsc_queue.h` | the lock-free queue between two threads |

`tests/test_playback.cpp` plays files through it with no sound card: the output equals the file sample
for sample (plain, after seeks, across pause and resume, bypassed through the engine), the track ends
exactly once, and a second thread acting as the sound card runs against a stream of random loads,
seeks and switches. It passes under the address and the thread sanitizer.
