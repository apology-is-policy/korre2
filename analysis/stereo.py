"""How alike are the two channels, source vs tape? (run align.py first)

    python stereo.py B3 A4 A6

Inter-channel coherence per octave band (1 = channels identical up to gain/delay, 0 =
unrelated) and inter-channel phase of the common content, for the source and the tape,
in loud and quiet passages. A drop from source to tape means the tape decorrelates the
channels (independent hiss, independent wobble); a phase shift means a time offset.
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy import signal

from common import db
from measure import OUT

BANDS = [125, 250, 500, 1000, 2000, 4000, 8000, 12000]


def ic_and_phase(x, sr):
    f, C = signal.coherence(x[:, 0], x[:, 1], sr, nperseg=4096)
    _, Pxy = signal.csd(x[:, 0], x[:, 1], sr, nperseg=4096)
    rows = []
    for fc in BANDS:
        m = (f >= fc / 2 ** 0.5) & (f < fc * 2 ** 0.5)
        rows.append((C[m].mean(), np.degrees(np.angle(Pxy[m].sum()))))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    args = ap.parse_args()
    print("inter-channel coherence (source -> tape) and phase of tape L re R [deg], per octave")
    print("track  part   " + "  ".join(f"{b / 1000:g}k".rjust(13) for b in BANDS))
    for tid in args.tracks:
        z = np.load(OUT / f"{tid}_aligned.npz")
        sr = int(z["sr"])
        src, tape = z["src"][3 * sr:-3 * sr].astype(np.float64), z["tape"][3 * sr:-3 * sr].astype(np.float64)
        blk = 8192
        nb = len(src) // blk
        lvl = db(np.mean(src[: nb * blk].reshape(nb, blk, 2) ** 2, axis=(1, 2)))
        for part, sel in (("loud", lvl > np.percentile(lvl, 60)), ("quiet", lvl < np.percentile(lvl, 25))):
            idx = np.repeat(sel, blk)
            s_rows = ic_and_phase(src[: nb * blk][idx], sr)
            t_rows = ic_and_phase(tape[: nb * blk][idx], sr)
            cells = [f"{s[0]:.2f}->{t[0]:.2f} {t[1]:+4.0f}" for s, t in zip(s_rows, t_rows)]
            print(f"{tid:5}  {part:5}  " + "  ".join(c.rjust(13) for c in cells))


if __name__ == "__main__":
    main()
