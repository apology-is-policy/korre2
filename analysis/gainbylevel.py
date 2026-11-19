"""Does the chain turn its gain down as the music gets louder? (run align.py first)

    python gainbylevel.py MB2 MB2emu [...]

A nonlinearity that bends the signal (y = x - a x^3) does two things: it adds distortion products, and
it lowers the gain of what passes, the more the louder. distfit.py measures the first; this measures
the second. The capture is fitted in 11 ms windows with a gain and a timing offset against its linear
prediction, whole and in two bands, and the window gains are set against the power of the source in
the same window (as a multiple of the song's mean power):
  by level   the mean gain in the quietest quarter of the windows ... the loudest tenth, and the slope:
             the change of gain per unit of power, from all windows
  fast       the same after the 2 s running means of gain and of power are taken away: the windows
             sorted by how far their power is from that of the seconds around them. A song that grows
             louder towards its end cannot tell compression from a drift of the tape's sensitivity
             along the reel (a few hundredths of a dB are enough); the fast part can.
Run it on the emulation too: its cubic is known, so its reading is what that much compression looks
like through this estimator (music in an 11 ms window is closer to a few sines than to noise, and the
gain a cubic takes off depends on that).
"""
from __future__ import annotations

import argparse

import numpy as np

from investigate import W, band, load
from measure import apply_H, cross_spectra
from residual import fit_windows
from tracks import track

BANDS = [("whole", None), ("177-707 Hz", (177, 707)), ("707-2828 Hz", (707, 2828))]
SLOW_S = 2.0


def running_mean(v: np.ndarray, weights: np.ndarray, n: int) -> np.ndarray:
    k = np.ones(n)
    return np.convolve(v * weights, k, "same") / np.maximum(np.convolve(weights, k, "same"), 1e-30)


def slope(g: np.ndarray, p: np.ndarray, w: np.ndarray) -> float:
    """Weighted least squares of g on p, with a constant."""
    pm, gm = np.sum(w * p) / np.sum(w), np.sum(w * g) / np.sum(w)
    return float(np.sum(w * (p - pm) * (g - gm)) / np.sum(w * (p - pm) ** 2))


def by_class(g: np.ndarray, w: np.ndarray, key: np.ndarray) -> list[float]:
    """Mean gain (weighted), in %, in the quarters of the windows sorted by `key` and in the top tenth."""
    n = len(key)
    order = np.argsort(key)
    q = n // 4
    sets = [order[:q], order[q:2 * q], order[2 * q:3 * q], order[3 * q:], order[n - n // 10:]]
    mean = np.sum(w * g) / np.sum(w)
    return [float(100 * (np.sum(w[s] * g[s]) / np.sum(w[s]) - mean)) for s in sets]


def measure(tid: str) -> dict:
    t = track(tid)
    sr, src, tape, z, trim = load(t.id)
    out = {}
    for c, name in ((0, "L"), (1, "R")):
        x, y = src[:, c], tape[:, c]
        f, Pxx, _, Pxy = cross_spectra(x, y, sr)
        yhat = apply_H(x, f, Pxy / Pxx)
        n = len(x) // W
        p = np.mean(x[: n * W].reshape(n, W) ** 2, axis=1)
        p = p / p.mean()  # the window's power, as a multiple of the song's mean
        m = max(3, int(round(SLOW_S * sr / W)) | 1)
        p_fast = p - running_mean(p, np.ones(n), m)
        rows = {}
        for label, edges in BANDS:
            yb, hb = (y, yhat) if edges is None else (band(y, sr, *edges), band(yhat, sr, *edges))
            *_, g, _, _ = fit_windows(yb - hb, hb, np.gradient(hb) * sr, x, W)
            w = np.sum(hb[: n * W].reshape(n, W) ** 2, axis=1)  # a window's gain is as sure as its signal is strong
            g_fast = g - running_mean(g, w, m)
            rows[label] = dict(level=by_class(g, w, p), slope=slope(g, p, w),
                               fast=by_class(g_fast, w, p_fast), fast_slope=slope(g_fast, p_fast, w))
        out[name] = rows
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    args = ap.parse_args()
    print("gain of the capture on its linear prediction in 11 ms windows, % re the song's mean gain:")
    print("  quietest quarter of the windows, second, third, loudest quarter, loudest tenth | slope, % per unit of power")
    for tid in args.tracks:
        res = measure(tid)
        print(f"== {tid}")
        for name in "LR":
            for label, _ in BANDS:
                row = res[name][label]
                print(f"   {name} {label:12s} by level " + " ".join(f"{v:+6.2f}" for v in row["level"]) + f" | {100 * row['slope']:+6.2f}"
                      + "   fast " + " ".join(f"{v:+6.2f}" for v in row["fast"]) + f" | {100 * row['fast_slope']:+6.2f}", flush=True)


if __name__ == "__main__":
    main()
