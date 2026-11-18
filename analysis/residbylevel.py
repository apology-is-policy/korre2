"""What is left after the best linear fit, per octave and by how loud the music is (run align.py first).

    python residbylevel.py MB2 MB2emu

For each track: the residual (capture minus the linear prediction from the source) relative to the
signal, in octave bands, over blocks of 85 ms sorted into classes by the loudness of the whole signal:
the quietest quarter of the blocks, the two middle quarters, the loudest quarter, and the loudest tenth.
With two ids (tape, emulation) the difference is printed too: where the emulation is cleaner or
rougher than the tape, and whether that depends on level. A tape whose roughness grows with level
faster than the emulation's is "level-dependent modulation" that the model does not have.
"""
from __future__ import annotations

import argparse

import numpy as np

from common import db
from investigate import load
from measure import apply_H, cross_spectra
from signature import band
from tracks import track

BANDS = [(177, 354, 250), (354, 707, 500), (707, 1414, 1000), (1414, 2828, 2000), (2828, 5657, 4000), (5657, 11314, 8000),
         (9192, 18385, 13000)]
CLASSES = ["quietest 1/4", "second 1/4", "third 1/4", "loudest 1/4", "loudest 1/10"]
B = 4096


def by_level(tid: str) -> np.ndarray:
    """Residual re signal in dB: (class, band), both channels together."""
    t = track(tid)
    sr, src, tape, z, trim = load(t.id)
    yh, rr = [], []
    for c in range(2):
        f, Pxx, _, Pxy = cross_spectra(src[:, c], tape[:, c], sr)
        yhat = apply_H(src[:, c], f, Pxy / Pxx)
        yh.append(yhat)
        rr.append(tape[:, c] - yhat)
    nb = len(yh[0]) // B
    loud = sum((y[: nb * B] ** 2).reshape(nb, B).mean(1) for y in yh)  # whole signal, both channels
    order = np.argsort(loud)
    q = nb // 4
    sets = [order[:q], order[q:2 * q], order[2 * q:3 * q], order[3 * q:], order[nb - nb // 10:]]
    out = np.zeros((len(sets), len(BANDS)))
    for k, (lo, hi, _) in enumerate(BANDS):
        py = pr = 0
        for c in range(2):
            yb, rb = band(yh[c], sr, lo, min(hi, 0.45 * sr)), band(rr[c], sr, lo, min(hi, 0.45 * sr))
            py = py + (yb[: nb * B] ** 2).reshape(nb, B).mean(1)
            pr = pr + (rb[: nb * B] ** 2).reshape(nb, B).mean(1)
        for j, s in enumerate(sets):
            out[j, k] = db(pr[s].sum() / py[s].sum())
    return out


def show(label: str, table: np.ndarray):
    print(f"  {label}")
    print("    " + " " * 14 + " ".join(f"{fc:>7d}" for _, _, fc in BANDS) + "  Hz")
    for name, row in zip(CLASSES, table):
        print(f"    {name:<14s}" + " ".join(f"{v:7.1f}" for v in row))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    args = ap.parse_args()
    tables = {}
    for tid in args.tracks:
        tables[tid] = by_level(tid)
        show(f"{tid}: residual re signal, dB", tables[tid])
    if len(args.tracks) == 2:
        a, b = args.tracks
        show(f"{b} minus {a}, dB (negative: {b} is cleaner)", tables[b] - tables[a])


if __name__ == "__main__":
    main()
