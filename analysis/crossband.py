"""Is a channel's amplitude modulation one gain wobble for all frequencies, or separate in each band?

    python crossband.py MB3 [MB3emu]

Coherence of the demodulated AM between octave bands of the same channel, per modulation rate.
One gain that multiplies the whole signal (level changes of an edge track, a slow flicker) moves all
bands together: coherence near the share of the AM that it accounts for. Noise around each
component separately (true modulation noise, added hiss) leaves the bands unrelated: coherence ~ 0.
The emulation's flicker is one process per channel, so it shows what "together" looks like here.
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy import signal

from investigate import band, load
from measure import apply_H, cross_spectra
from signature import EPS_REL, NPER, OCT

RATE_BANDS = [(3, 12), (12, 48), (48, 96), (96, 192), (192, 340)]
PAIRS = [(1000, 2000), (2000, 4000), (1000, 4000), (4000, 8000)]


def demod(tid):
    sr, src, tape, z, trim = load(tid)
    out = {}
    for c, ch in enumerate("LR"):
        x, y = src[:, c], tape[:, c]
        f, Pxx, _, Pxy = cross_spectra(x, y, sr)
        yhat = apply_H(x, f, Pxy / Pxx)
        r = y - yhat
        for lo, hi, fc in OCT[:4]:
            Yh, Rr = signal.hilbert(band(yhat, sr, lo, hi)), signal.hilbert(band(r, sr, lo, hi))
            p2 = np.abs(Yh) ** 2
            eps = EPS_REL * np.median(p2[p2 > np.median(p2)])
            w = p2 / (p2 + eps)
            d = Rr * np.conj(Yh) / (p2 + eps) * w
            out[(ch, fc)] = (d.real.astype(np.float32), d.imag.astype(np.float32))
    return sr, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    args = ap.parse_args()
    print("coherence between octaves, per modulation rate band [Hz]:  " + " ".join(f"{a}-{b}".rjust(8) for a, b in RATE_BANDS))
    for tid in args.tracks:
        sr, d = demod(tid)
        for kind, part in (("AM", 0), ("timing", 1)):
            for ch in "LR":
                for a, b in PAIRS:
                    f, C = signal.coherence(d[(ch, a)][part], d[(ch, b)][part], sr, nperseg=NPER)
                    row = " ".join(f"{C[(f >= lo) & (f < hi)].mean():8.2f}" for lo, hi in RATE_BANDS)
                    print(f"  {tid:<7} {kind:<6} {ch}  {a:5d} with {b:5d} Hz:             {row}")
            # the two channels' AM in the same octave, for scale
        for fc in (1000, 2000, 4000):
            f, C = signal.coherence(d[("L", fc)][0], d[("R", fc)][0], sr, nperseg=NPER)
            print(f"  {tid:<7} AM     L with R at {fc:5d} Hz:              " + " ".join(f"{C[(f >= lo) & (f < hi)].mean():8.2f}" for lo, hi in RATE_BANDS))


if __name__ == "__main__":
    main()
