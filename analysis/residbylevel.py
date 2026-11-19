"""What is left after the best linear fit, per octave and by how loud the music is (run align.py first).

    python residbylevel.py MB2 MB2emu

For each track: the residual (capture minus the linear prediction from the source) relative to the
signal, in octave bands, over blocks of 85 ms sorted into classes by the loudness of the whole signal:
the quietest quarter of the blocks, the two middle quarters, the loudest quarter, and the loudest tenth.
With two ids (tape, emulation) the difference is printed too: where the emulation is cleaner or
rougher than the tape, and whether that depends on level. A tape whose roughness grows with level
faster than the emulation's is "level-dependent modulation" that the model does not have.

--slow-gain S   before the residual is taken, let the gain follow the S-second running mean of the gains
                fitted per 11 ms window. One linear fit for a whole song counts a level that sits a few
                hundredths of a dB off in the quiet passages as residual there (a chain that compresses,
                or a tape whose sensitivity drifts along the reel): a difference in level, not roughness.
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


def by_level(tid: str, slow_gain_s: float = 0.0) -> np.ndarray:
    """Residual re signal in dB: (class, band), both channels together."""
    t = track(tid)
    sr, src, tape, z, trim = load(t.id)
    yh, rr = [], []
    for c in range(2):
        f, Pxx, _, Pxy = cross_spectra(src[:, c], tape[:, c], sr)
        yhat = apply_H(src[:, c], f, Pxy / Pxx)
        r = tape[:, c] - yhat
        if slow_gain_s > 0:
            from gainbylevel import running_mean
            from investigate import W
            from residual import fit_windows
            *_, g, _, _ = fit_windows(r, yhat, np.gradient(yhat) * sr, src[:, c], W)
            n = len(g)
            w = np.sum(yhat[: n * W].reshape(n, W) ** 2, axis=1)
            slow = running_mean(g, w, max(3, int(round(slow_gain_s * sr / W)) | 1))
            r[: n * W] -= np.repeat(slow, W) * yhat[: n * W]
        yh.append(yhat)
        rr.append(r)
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
    ap.add_argument("--slow-gain", type=float, default=0.0, metavar="S",
                    help="let the gain follow the S-second running mean of the per-window gains first")
    args = ap.parse_args()
    tables = {}
    for tid in args.tracks:
        tables[tid] = by_level(tid, args.slow_gain)
        show(f"{tid}: residual re signal, dB" + (f" (gain free to move over {args.slow_gain:g} s)" if args.slow_gain else ""), tables[tid])
    if len(args.tracks) == 2:
        a, b = args.tracks
        show(f"{b} minus {a}, dB (negative: {b} is cleaner)", tables[b] - tables[a])


if __name__ == "__main__":
    main()
