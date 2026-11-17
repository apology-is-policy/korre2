"""Left/right differences in the tape capture: inter-channel delay and level balance.

    python channels.py               # delay + balance for every unclipped track
    python channels.py --detail B3   # delay over time within one track

Delay: band-limited GCC-PHAT on 0.5 s windows, the weakest 25% of windows (by
correlation peak) dropped. Positive = LEFT lags RIGHT.
Balance: L-R band power in dB, per octave, from the capture resampled to 48 kHz.
"""
from __future__ import annotations

import argparse

import numpy as np

from common import OCTAVES, bandpow, db, decode, octave_edges, psd, windowed_delays
from tracks import CAPTURE_SR, clean_tracks, track


def robust_delays(x, fmin=300, fmax=16000, hop_s=0.5):
    times, delays, peaks = windowed_delays(x, CAPTURE_SR, hop_s=hop_s, fmin=fmin, fmax=fmax)
    keep = peaks > np.percentile(peaks, 25)
    return times[keep], delays[keep]


def delay_table():
    print("Inter-channel delay [us, + = left lags right]")
    print("track   300 Hz-16 kHz median (IQR)    300 Hz-3 kHz   3-16 kHz")
    medians = []
    for t in clean_tracks():
        x = decode(t.path, t.start, t.end)
        _, full = robust_delays(x)
        _, low = robust_delays(x, 300, 3000)
        _, high = robust_delays(x, 3000, 16000)
        medians.append(np.median(full))
        print(f"{t.id:5}   {np.median(full):+6.1f} ({np.percentile(full, 25):+5.1f}..{np.percentile(full, 75):+5.1f})"
              f"          {np.median(low):+6.1f}        {np.median(high):+6.1f}    {t.title or ''}")
    print(f"mean    {np.mean(medians):+6.1f}   std across tracks {np.std(medians):.1f}")


def delay_detail(t):
    times, d = robust_delays(decode(t.path, t.start, t.end), hop_s=0.25)
    order = np.argsort(times)
    times, d = times[order], d[order]
    slow = np.array([np.median(d[(times > s - 2.5) & (times < s + 2.5)]) for s in times])
    print(f"{t.id} {t.title or ''}: {len(d)} windows")
    print(f"  median {np.median(d):+.2f} us | IQR {np.percentile(d, 25):+.2f}..{np.percentile(d, 75):+.2f}"
          f" | 5-95% {np.percentile(d, 5):+.2f}..{np.percentile(d, 95):+.2f}")
    print(f"  slow wander (5 s moving median) {slow.min():+.2f}..{slow.max():+.2f} us;"
          f" fast jitter around it (std) {np.std(d - slow):.2f} us")
    print("  10 s medians: " + "  ".join(
        f"{s:d}s:{np.median(d[(times >= s) & (times < s + 10)]):+.1f}"
        for s in range(0, int(times.max()), 10) if ((times >= s) & (times < s + 10)).sum() > 3))


def balance_table():
    bands = [(20, 20000)] + [octave_edges(c) for c in OCTAVES[1:]]
    labels = ["broad"] + [f"{c:g}" for c in OCTAVES[1:]]
    rows = []
    tracks = clean_tracks()
    for t in tracks:
        x = decode(t.path, t.start, t.end, sr=48000).astype(np.float64)
        f, P = psd(x, 48000, 16384)
        rows.append([db(bandpow(f, P[:, 0], lo, hi)) - db(bandpow(f, P[:, 1], lo, hi)) for lo, hi in bands])
    D = np.array(rows)
    print("\nLevel balance, L minus R [dB]")
    print("track  " + " ".join(f"{s:>6}" for s in labels))
    for t, row in zip(tracks, D):
        print(f"{t.id:5}  " + " ".join(f"{v:+6.2f}" for v in row))
    print("mean   " + " ".join(f"{v:+6.2f}" for v in D.mean(axis=0)))
    print("std    " + " ".join(f"{v:6.2f}" for v in D.std(axis=0)))
    print("L>R    " + " ".join(f"{int((D[:, i] > 0).sum()):>3}/{len(D)}" for i in range(D.shape[1])))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--detail", metavar="TRACK", help="delay over time within one track")
    args = ap.parse_args()
    if args.detail:
        delay_detail(track(args.detail))
    else:
        delay_table()
        balance_table()
