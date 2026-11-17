"""Noise floor of the tape capture: leader vs blank tape, plus how far a song rises above it.

    python noise.py            # noise segments + spectrum margin for B3 (Shallow)
    python noise.py --track A3 # margin for another track
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy import signal

from common import OCTAVES, bandpow, data_file, db, decode, fmt_t, octave_edges, psd
from tracks import CAPTURE_SR, NOISE_SEGMENTS, SIDE_FILES, track


def spectral_lines(x, sr, min_prominence_db=8, max_lines=12):
    f, P = psd(x, sr, 65536)
    Pm = P.mean(axis=1)
    prominence = db(Pm) - signal.medfilt(db(Pm), 151)
    idx, _ = signal.find_peaks(prominence, height=min_prominence_db, distance=5)
    idx = sorted(idx, key=lambda k: -prominence[k])[:max_lines]
    return [(f[k], prominence[k], db(bandpow(f, Pm, f[k] - 9, f[k] + 9))) for k in sorted(idx, key=lambda k: f[k])]


def report_noise():
    blank = {}
    for name, side, a, b in NOISE_SEGMENTS:
        x = decode(data_file(SIDE_FILES[side]), a, b).astype(np.float64)
        f, P = psd(x, CAPTURE_SR, 32768)
        if name.endswith("blank tape"):
            blank[side] = (f, P.mean(axis=1))
        audio = [db(bandpow(f, P[:, c], 20, 20000)) for c in (0, 1)]
        ultra = [db(bandpow(f, P[:, c], 20000, 95000)) for c in (0, 1)]
        fc, C = signal.coherence(x[:, 0], x[:, 1], CAPTURE_SR, nperseg=8192)
        print(f"\n{name} [{side} {fmt_t(a)}-{fmt_t(b)}]")
        print(f"  20 Hz-20 kHz: L {audio[0]:6.1f}  R {audio[1]:6.1f} dBFS  |  20-95 kHz: L {ultra[0]:6.1f}  R {ultra[1]:6.1f} dBFS")
        print(f"  L/R coherence 20-500 Hz {C[(fc > 20) & (fc < 500)].mean():.2f}, 2-16 kHz "
              f"{C[(fc > 2000) & (fc < 16000)].mean():.2f}  (0 = independent per channel)")
        bands = [db(bandpow(f, P.mean(axis=1), *octave_edges(c))) for c in OCTAVES]
        print("  octaves (L+R avg, dBFS): " + "  ".join(f"{c:g}:{v:.0f}" for c, v in zip(OCTAVES, bands)))
        if name.endswith("blank tape"):
            for freq, prom, lvl in spectral_lines(x, CAPTURE_SR):
                print(f"    line {freq:9.1f} Hz  +{prom:4.1f} dB above floor, {lvl:6.1f} dBFS")
    return blank


def report_margin(t, blank):
    print(f"\n{t.id} {t.title or ''}: song spectrum vs blank-tape noise (side {t.side})")
    x = decode(t.path, t.start, t.end).astype(np.float64)
    f, P = psd(x, CAPTURE_SR, 32768)
    Pm = P.mean(axis=1)
    fn, Pn = blank[t.side]
    Pn = np.interp(f, fn, Pn)
    for lo, hi in [(2800, 5600), (5600, 11200), (11200, 16000), (16000, 20000),
                   (20000, 24000), (24000, 48000), (48000, 95000)]:
        s, n = db(bandpow(f, Pm, lo, hi)), db(bandpow(f, Pn, lo, hi))
        print(f"  {lo / 1000:5.1f}-{hi / 1000:5.1f} kHz: song {s:6.1f}, noise {n:6.1f} dBFS, margin {s - n:5.1f} dB")
    thirds = [1000 * 2 ** (k / 3) for k in range(22)]
    above = [c for c in thirds
             if db(bandpow(f, Pm, c / 2 ** (1 / 6), c * 2 ** (1 / 6)))
             - db(bandpow(f, Pn, c / 2 ** (1 / 6), c * 2 ** (1 / 6))) > 10]
    if above:
        print(f"  highest 1/3-octave band with the song >10 dB above hiss: {max(above) / 1000:.1f} kHz")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--track", default="B3")
    args = ap.parse_args()
    report_margin(track(args.track), report_noise())
