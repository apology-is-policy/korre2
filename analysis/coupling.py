"""Is the tape's modulation driven by the music, or independent of it? (run align.py first)

    python coupling.py B3 B3emu

signature.py matches how much the response fluctuates and how fast. This asks whether the fluctuation
is tied to the signal. Per octave band the residual is demodulated into amplitude modulation a(t) and
timing p(t) (modstats/signature method), then compared with drivers taken from the music:
  bass          the low-frequency waveform itself (below 200 Hz): cycle-by-cycle modulation of the band
  bass^2        its square: a dependence on the bass's magnitude regardless of sign
  level         the overall level in dB (30 Hz smoothing)
  own level     the band's own level in dB
Reported: coherence between a(t) / p(t) and each driver per modulation-rate band (0 = unrelated;
independent signals read ~0.01 here), and the mean a(t) and p(t) while the band's own level is
falling fast, steady, or rising fast (attack/decay asymmetry).
The emulation's modulation is random by construction, so its numbers show what the estimator produces
alone; only what the tape shows beyond them is real.
"""
from __future__ import annotations

import argparse
from math import gcd

import numpy as np
from scipy import signal

from common import db
from investigate import band, load
from measure import apply_H, cross_spectra
from tracks import track

FS = 2000  # rate the modulation and the drivers are compared at
OCT = [(707, 1414, 1000), (1414, 2828, 2000), (2828, 5657, 4000), (5657, 11314, 8000)]
RATES = [(1, 5), (5, 20), (20, 60), (60, 150), (150, 400)]
SLOPES = [(-np.inf, -80), (-80, -20), (-20, 20), (20, 80), (80, np.inf)]  # dB/s of the band's own level


def down(v, sr):
    g = gcd(FS, sr)
    return signal.resample_poly(v, FS // g, sr // g)


def level_db(p, sr, smooth_hz=30.0):
    sos = signal.butter(2, smooth_hz, "lowpass", fs=sr, output="sos")
    return 10 * np.log10(np.maximum(signal.sosfiltfilt(sos, p), 1e-12))


def analyse(tid):
    t = track(tid)
    sr, src, tape, z, trim = load(t.id)
    res = {}
    for c, name in ((0, "L"), (1, "R")):
        x, y = src[:, c], tape[:, c]
        f, Pxx, _, Pxy = cross_spectra(x, y, sr)
        yhat = apply_H(x, f, Pxy / Pxx)
        r = y - yhat
        bass = signal.sosfiltfilt(signal.butter(4, 200, "lowpass", fs=sr, output="sos"), yhat)
        drivers = {"bass": down(bass, sr), "bass^2": down(bass ** 2, sr), "level": down(level_db(yhat ** 2, sr), sr)}
        for lo, hi, fc in OCT:
            Yh, Rr = signal.hilbert(band(yhat, sr, lo, hi)), signal.hilbert(band(r, sr, lo, hi))
            p2 = np.abs(Yh) ** 2
            eps = 0.25 * np.median(p2[p2 > np.median(p2)])
            w = p2 / (p2 + eps)
            cm = Rr * np.conj(Yh) / (p2 + eps) * w
            k_us = 1e6 / (2 * np.pi * np.sqrt(lo * hi))
            a, p, wd = down(cm.real, sr), down(cm.imag, sr) * k_us, down(w, sr)
            own = down(level_db(p2, sr), sr)
            drv = dict(drivers, **{"own level": own})
            coh = {}
            for dn, d in drv.items():
                n = min(len(a), len(d))
                ff, Ca = signal.coherence(a[:n], d[:n] - d[:n].mean(), FS, nperseg=4096)
                _, Cp = signal.coherence(p[:n], d[:n] - d[:n].mean(), FS, nperseg=4096)
                coh[dn] = ([float(Ca[(ff >= lo_) & (ff < hi_)].mean()) for lo_, hi_ in RATES],
                           [float(Cp[(ff >= lo_) & (ff < hi_)].mean()) for lo_, hi_ in RATES])
            slope = np.gradient(own) * FS
            asym = []
            for s0, s1 in SLOPES:
                m = (slope >= s0) & (slope < s1) & (wd > 0.3)
                asym.append((float(a[m].sum() / wd[m].sum() * 100), float(p[m].sum() / wd[m].sum()), int(m.sum())))
            res[(name, fc)] = dict(coh=coh, asym=asym)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    args = ap.parse_args()
    results = {tid: analyse(tid) for tid in args.tracks}
    hdr = " ".join(f"{a}-{b}".rjust(7) for a, b in RATES)
    for fc in [o[2] for o in OCT]:
        print("=" * 110)
        print(f"{fc} Hz octave: coherence of the band's modulation with each driver, per modulation rate [Hz]   {hdr}")
        for kind, idx in (("AM    ", 0), ("timing", 1)):
            for dn in ("bass", "bass^2", "level", "own level"):
                for tid in args.tracks:
                    row = np.mean([results[tid][(ch, fc)]["coh"][dn][idx] for ch in "LR"], axis=0)
                    print(f"   {kind} vs {dn:9} {tid:6}                                                          "
                          + " ".join(f"{v:7.3f}" for v in row))
        print(f"   mean AM % / timing us while the band's own level is: falling fast | falling | steady | rising | rising fast")
        for tid in args.tracks:
            rows = [results[tid][(ch, fc)]["asym"] for ch in "LR"]
            print(f"   {tid:6} " + " | ".join(f"{np.mean([r[k][0] for r in rows]):+6.2f}% {np.mean([r[k][1] for r in rows]):+6.2f}us"
                                           for k in range(len(SLOPES))))


if __name__ == "__main__":
    main()
