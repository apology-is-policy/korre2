"""Diagnostic blind pairs: where does a difference between tape and emulation live?

    python diagset.py B3        from out/listening/B3/{tape,6_full}.flac -> out/listening/B3/diagnostic/

When the ear tells tape from emulation but the measurements agree, the ear can at least say WHERE the
difference is. Each folder holds one blind pair (X.wav / Y.wav, tape and emulation in a random order
drawn separately per folder) after the same treatment of both files:
  1_below_150Hz      2_150Hz-1300Hz      3_1300Hz-6kHz      4_above_6kHz     the four bands on their own
  5_mono_L+R         what both ears share, played identically in both ears
  6_difference_L-R   what differs between the ears, played identically in both ears
A pair in which the tape can still be picked out contains (part of) the tell; one in which it can't, doesn't.
Band filters are zero-phase and identical for both files; each pair gets one common gain (so quiet bands
are loud enough to hear), which leaves the level relation between the two files untouched.
KEY_dont_peek.txt lists all the answers.
"""
from __future__ import annotations

import argparse
import random

import numpy as np
from scipy import signal

from common import decode
from measure import OUT
from render import write_wav

SR = 48000
BANDS = [("1_below_150Hz", None, 150.0), ("2_150Hz-1300Hz", 150.0, 1300.0),
         ("3_1300Hz-6kHz", 1300.0, 6000.0), ("4_above_6kHz", 6000.0, None)]


def band_filter(x, lo, hi):
    if lo is None:
        sos = signal.butter(8, hi, "lowpass", fs=SR, output="sos")
    elif hi is None:
        sos = signal.butter(8, lo, "highpass", fs=SR, output="sos")
    else:
        sos = signal.butter(8, [lo, hi], "bandpass", fs=SR, output="sos")
    return signal.sosfiltfilt(sos, x, axis=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("track")
    ap.add_argument("--seed", default="1")
    args = ap.parse_args()
    folder = OUT / "listening" / args.track
    tape, emu = (decode(folder / f"{name}.flac", sr=SR).astype(np.float64) for name in ("tape", "6_full"))
    n = min(len(tape), len(emu))
    tape, emu = tape[:n], emu[:n]
    sets = [(name, lambda x, lo=lo, hi=hi: band_filter(x, lo, hi)) for name, lo, hi in BANDS]
    sets.append(("5_mono_L+R", lambda x: np.repeat(x.mean(axis=1, keepdims=True), 2, axis=1)))
    sets.append(("6_difference_L-R", lambda x: np.repeat((x[:, :1] - x[:, 1:]) / 2, 2, axis=1)))
    key = []
    for name, fn in sets:
        pair = {"tape": fn(tape), "emulation": fn(emu)}
        gain = 0.9 / max(np.abs(v).max() for v in pair.values())
        order = ["tape", "emulation"]
        random.Random(f"{args.track}-{args.seed}-{name}-{n}").shuffle(order)
        for label, which in zip("XY", order):
            write_wav(pair[which] * gain, SR, folder / "diagnostic" / name / f"{label}.wav")
        key.append(f"{name}: X = {order[0]}, Y = {order[1]}")
        print(f"  {name}: common gain {20 * np.log10(gain):+.1f} dB")
    (folder / "diagnostic" / "KEY_dont_peek.txt").write_text("\n".join(key) + "\n")
    (folder / "diagnostic" / "README.txt").write_text(__doc__.split("\n\n", 2)[2])
    print(f"wrote {folder / 'diagnostic'}/")


if __name__ == "__main__":
    main()
