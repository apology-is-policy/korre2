"""Is the fast amplitude modulation in a band multiplicative or additive?

    python levelsplit.py MB3 MB3emu [--octaves 1000 2000 4000]

Per octave and channel: the demodulated AM (the part of the residual in phase with the predicted
signal, relative to it) in the 96-384 Hz rate range, in 85 ms blocks sorted by the band's own level.
A modulation that multiplies the signal (flicker, modulation noise) gives the same percentage at every
level. Noise that is simply added gives a percentage that falls as the signal rises: 6 dB more signal,
half the percentage. Run it on the emulation too: its flicker and noise are known, so it shows what
each looks like through this estimator.
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy import signal

from investigate import band, load
from measure import apply_H, cross_spectra
from signature import OCT

CLASSES = [(5, 20), (20, 40), (40, 60), (60, 80), (80, 95), (95, 100)]
B = 4096


LOW_OCT = [(177, 354, 250), (354, 707, 500)]  # below signature.py's octaves; use a lower --rate with them


def split(tid, octaves, rate=(96.0, 384.0)):
    sr, src, tape, z, trim = load(tid)
    out = {}
    sos = signal.butter(4, rate, "bandpass", fs=sr, output="sos")
    for lo, hi, fc in LOW_OCT + OCT:
        if fc not in octaves:
            continue
        for c, ch in enumerate("LR"):
            x, y = src[:, c], tape[:, c]
            f, Pxx, _, Pxy = cross_spectra(x, y, sr)
            yhat = apply_H(x, f, Pxy / Pxx)
            yb, rb = band(yhat, sr, lo, hi), band(y - yhat, sr, lo, hi)
            Yh, Rr = signal.hilbert(yb), signal.hilbert(rb)
            p2 = np.abs(Yh) ** 2
            # in-phase part of the residual, in signal units; divided by the block's own level below
            inphase = signal.sosfiltfilt(sos, (Rr * np.conj(Yh)).real / np.sqrt(p2 + 1e-30))
            quad = signal.sosfiltfilt(sos, (Rr * np.conj(Yh)).imag / np.sqrt(p2 + 1e-30))
            nb = len(yb) // B
            lvl = p2[: nb * B].reshape(nb, B).mean(1) / 2          # mean square of the band's signal
            ai = (inphase[: nb * B] ** 2).reshape(nb, B).mean(1)   # mean square of the in-phase residual
            aq = (quad[: nb * B] ** 2).reshape(nb, B).mean(1)
            edges = np.percentile(lvl, [a for a, _ in CLASSES] + [100])
            rows = []
            for a, b in zip(edges[:-1], edges[1:]):
                m = (lvl >= a) & (lvl <= b)
                rows.append((10 * np.log10(lvl[m].mean()), 100 * np.sqrt(ai[m].sum() / (2 * lvl[m].sum())),
                             100 * np.sqrt(aq[m].sum() / (2 * lvl[m].sum())), 10 * np.log10(ai[m].mean() + 1e-30)))
            out[(fc, ch)] = rows
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    ap.add_argument("--octaves", nargs="+", type=int, default=[1000, 2000, 4000])
    ap.add_argument("--rate", nargs=2, type=float, default=[96.0, 384.0],
                    help="modulation rates looked at, Hz (keep the top below a quarter of the octave's width)")
    args = ap.parse_args()
    res = {t: split(t, args.octaves, tuple(args.rate)) for t in args.tracks}
    print("level classes (percentiles of the band's level in 85 ms blocks): " + " ".join(f"{a}-{b}" for a, b in CLASSES))
    for fc in args.octaves:
        for ch in "LR":
            print(f"\n{fc} Hz octave, {ch}: band level dBFS | AM % at {args.rate[0]:g}-{args.rate[1]:g} Hz | same for the quadrature (timing) part | in-phase residual dBFS")
            for t in args.tracks:
                rows = res[t][(fc, ch)]
                print(f"  {t:<8} " + " ".join(f"{r[0]:6.1f}" for r in rows) + " | " + " ".join(f"{r[1]:5.2f}" for r in rows)
                      + " | " + " ".join(f"{r[2]:5.2f}" for r in rows) + " | " + " ".join(f"{r[3]:6.1f}" for r in rows))


if __name__ == "__main__":
    main()
