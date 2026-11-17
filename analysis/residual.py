"""What is the residual (tape minus linear prediction) made of? Run align.py first.

    python residual.py B3

Per short window, fits  residual = g(t) * yhat + tau(t) * d(yhat)/dt + rest:
  g   = gain wobble (amplitude modulation)
  tau = timing wobble left after the warp (fast flutter + whatever the warp smoothed over)
A null test repeats the fit with the derivative taken 1 s earlier; it should explain ~nothing.
Then prints the spectrum of tau(t): mechanical periodicities show up as peaks.
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy import signal

from common import db
from measure import OUT, apply_H, blocks_db, cross_spectra
from tracks import track


def fit_windows(r, yhat, dy, x, W):
    """Per-window 2-parameter least squares. Returns (gain share, timing share, rest share,
    tau per window [s], gain per window, loud-window mask) - shares over the louder half."""
    n = len(r) // W
    R, Yh, D = (v[: n * W].reshape(n, W) for v in (r, yhat, dy))
    lvl = db(np.mean(x[: n * W].reshape(n, W) ** 2, axis=1))
    loud = lvl > np.median(lvl)
    a11, a22, a12 = (Yh * Yh).sum(1), (D * D).sum(1), (Yh * D).sum(1)
    b1, b2 = (Yh * R).sum(1), (D * R).sum(1)
    det = a11 * a22 - a12 ** 2 + 1e-30
    g = (a22 * b1 - a12 * b2) / det
    tau = (a11 * b2 - a12 * b1) / det
    Eg, Et = g[:, None] * Yh, tau[:, None] * D
    tot = (R[loud] ** 2).sum()
    shares = [(Eg[loud] ** 2).sum() / tot, (Et[loud] ** 2).sum() / tot,
              ((R - Eg - Et)[loud] ** 2).sum() / tot]
    return (*shares, tau, g, loud, lvl)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("track")
    args = ap.parse_args()
    t = track(args.track)
    z = np.load(OUT / f"{t.id}_aligned.npz")
    sr = int(z["sr"])
    trim = 3 * sr
    src = z["src"][trim:-trim].astype(np.float64)
    tape = z["tape"][trim:-trim].astype(np.float64)

    print(f"{t.id} {t.title or ''}: residual = gain wobble + timing wobble + rest (shares over the louder half)")
    print("  ch  window          gain   timing   rest    timing RMS  gain RMS   | null test: timing share")
    for c, name in ((0, "L"), (1, "R")):
        x, y = src[:, c], tape[:, c]
        f, Pxx, _, Pxy = cross_spectra(x, y, sr)
        yhat = apply_H(x, f, Pxy / Pxx)
        r = y - yhat
        dy = np.gradient(yhat) * sr
        for W in (2048, 512, 128):
            sg, st, sr_, tau, g, loud, _ = fit_windows(r, yhat, dy, x, W)
            _, st_null, *_ = fit_windows(r, yhat, np.roll(dy, sr), x, W)
            print(f"  {name}  {W:5d} ({W / sr * 1e3:4.1f} ms)  {sg * 100:5.1f}%  {st * 100:5.1f}%  {sr_ * 100:5.1f}%"
                  f"    {np.sqrt(np.mean(tau[loud] ** 2)) * 1e6:5.1f} us   {np.sqrt(np.mean(g[loud] ** 2)) * 100:5.2f}%"
                  f"   |  {st_null * 100:4.1f}%")
        if name == "L":
            W = 256
            *_, tau, g, loud, lvl = fit_windows(r, yhat, dy, x, W)
            fs = sr / W
            good = lvl > np.percentile(lvl, 30)
            i = np.arange(len(tau))
            tau_us = np.clip(np.interp(i, i[good], tau[good] * 1e6), -80, 80)
            ff, P = signal.welch(tau_us, fs, nperseg=4096)
            jitter = [(lo, hi, np.sqrt(np.trapezoid(P[(ff >= lo) & (ff < hi)], ff[(ff >= lo) & (ff < hi)])))
                      for lo, hi in [(0.5, 4), (4, 10), (10, 30), (30, 80)]]
            prom = 10 * np.log10(P + 1e-30) - signal.medfilt(10 * np.log10(P + 1e-30), 31)
            pk, _ = signal.find_peaks(prom, height=6, distance=3)
            pk = sorted([k for k in pk if 1 < ff[k] < 85], key=lambda k: -prom[k])[:8]

    print(f"\nTiming wobble left after the warp, left channel ({fs:.0f} Hz sampling of tau):")
    for lo, hi, rms in jitter:
        mid = np.sqrt(lo * hi)
        print(f"  {lo:4.1f}-{hi:3.0f} Hz: {rms:5.1f} us RMS  (~{2 * np.pi * mid * rms * 1e-4:.3f}% speed deviation around {mid:.0f} Hz)")
    print("  peaks: " + ", ".join(f"{ff[k]:.1f} Hz (+{prom[k]:.0f} dB)" for k in sorted(pk, key=lambda k: ff[k])))


if __name__ == "__main__":
    main()
