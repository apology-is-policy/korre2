"""Level- and time-dependent behaviour the first tests could miss (run align.py first).

    python dynamics.py B3 [B3emu A6 ...]

1. Distortion vs level: 2nd/3rd-order FIR-Hammerstein on the residual (after linear + timing
   + gain), trained on even seconds and tested on odd seconds, so both contain loud passages.
   (The earlier first-half/second-half split never trained on Shallow's climax.)
2. Noise floor vs time since sound: treble residual (6-16 kHz) in blocks where the music has
   nothing in that band, binned by time since the last loud block. A stationary hiss is flat.
3. Modulation vs level: demodulated timing jitter and AM (modstats/signature method) in the
   4 and 8 kHz octaves, slow (<100 Hz rates) and fast (>100 Hz), per source-loudness class.
   Pure tape-transport effects don't depend on level; a level dependence would point at the
   tape itself (saturation, head contact under signal) or the electronics.
"""
from __future__ import annotations

import argparse

import numpy as np

from common import db
from investigate import BLOCK, band, decompose, fit_fir_multi, load, predict


def distortion_vs_level(d, sr, K=32):
    out = {}
    for name in ("L", "R"):
        ch = d[name]
        n = len(ch["clean"])
        sec = (np.arange(n) // sr) % 2
        u = ch["x"] / np.std(ch["x"])
        feats = [u ** 2 - np.mean(u ** 2), u ** 3]
        train = sec == 0
        hs = fit_fir_multi([f * train for f in feats], ch["clean"] * train, K)
        pred = predict(feats, hs)
        nb = n // BLOCK
        lvl = db(np.mean(ch["x"][: nb * BLOCK].reshape(nb, BLOCK) ** 2, axis=1))
        test_b = (np.arange(nb) * BLOCK // sr) % 2 == 1
        P = pred[: nb * BLOCK].reshape(nb, BLOCK)
        C = ch["clean"][: nb * BLOCK].reshape(nb, BLOCK)
        Y = ch["y"][: nb * BLOCK].reshape(nb, BLOCK)
        rows = []
        for lo, hi in zip(*np.percentile(lvl[test_b], [[0, 50, 75, 90, 97], [50, 75, 90, 97, 100]])):
            m = test_b & (lvl >= lo) & (lvl <= hi)
            expl = 1 - np.sum((C[m] - P[m]) ** 2) / np.sum(C[m] ** 2)
            rows.append(((lo + hi) / 2, float(expl), float(db(np.sum(P[m] ** 2) / np.sum(Y[m] ** 2)))))
        out[name] = rows
    return out


def noise_after_sound(d, sr, hiss_db):
    yh = sum(band(d[c]["yhat"], sr, 6000, 16000) ** 2 for c in "LR") / 2
    rr = sum(band(d[c]["clean"], sr, 6000, 16000) ** 2 for c in "LR") / 2
    full = sum(d[c]["yhat"] ** 2 for c in "LR") / 2
    nb = len(yh) // BLOCK
    yb, rb, fb = (db(v[: nb * BLOCK].reshape(nb, BLOCK).mean(axis=1)) for v in (yh, rr, full))
    quiet = yb < hiss_db - 10  # music contributes <10% of the hiss power in this band
    loud = fb > np.percentile(fb, 60)
    since = np.full(nb, np.inf)
    last = -np.inf
    for i in range(nb):
        if loud[i]:
            last = i
        since[i] = (i - last) * BLOCK / sr
    rows = []
    for lo, hi in [(0, 0.1), (0.1, 0.3), (0.3, 1), (1, 3), (3, np.inf)]:
        m = quiet & (since >= lo) & (since < hi)
        rows.append((lo, hi, int(m.sum()), float(np.median(rb[m])) if m.sum() >= 5 else np.nan))
    return rows


def modulation_vs_level(d, sr, classes=((20, 50), (50, 75), (75, 90), (90, 97), (97, 100))):
    from scipy import signal as sg
    lvl_src = sum(d[c]["x"] ** 2 for c in "LR") / 2
    B = 4096
    nb = len(lvl_src) // B
    lv = db(lvl_src[: nb * B].reshape(nb, B).mean(1))
    edges = np.percentile(lv, [q for pair in classes for q in pair])
    out = {}
    for lo, hi, fc in ((2828, 5657, 4000), (5657, 11314, 8000)):
        rows = {c: [] for c in "LR"}
        for name in "LR":
            Yh = sg.hilbert(band(d[name]["yhat"], sr, lo, hi))
            Rr = sg.hilbert(band(d[name]["y"] - d[name]["yhat"], sr, lo, hi))
            p2 = np.abs(Yh) ** 2
            eps = 0.25 * np.median(p2[p2 > np.median(p2)])
            w = p2 / (p2 + eps)
            cm = Rr * np.conj(Yh) / (p2 + eps) * w
            k_us = 1e6 / (2 * np.pi * np.sqrt(lo * hi))
            hp = sg.butter(4, 100, "highpass", fs=sr, output="sos")
            lp = sg.butter(4, 100, "lowpass", fs=sr, output="sos")
            parts = {}
            for tag, sos in (("slow", lp), ("fast", hp)):
                v = sg.sosfiltfilt(sos, cm.real), sg.sosfiltfilt(sos, cm.imag)
                parts[tag] = [(u[: nb * B] ** 2).reshape(nb, B).mean(1) for u in v]
            wb = (w[: nb * B] ** 2).reshape(nb, B).mean(1)
            for k, (a, b) in enumerate(classes):
                m = (lv >= edges[2 * k]) & (lv <= edges[2 * k + 1])
                norm = wb[m].mean()
                cell = {}
                for tag in ("slow", "fast"):
                    am, pm = (parts[tag][i][m].mean() / norm for i in (0, 1))
                    cell[tag] = (np.sqrt(am) * 100, np.sqrt(pm) * k_us)
                rows[name].append((float(np.median(lv[m])), cell))
        out[fc] = rows
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    args = ap.parse_args()
    from scipy import signal
    from common import bandpow, data_file, decode
    from signature import hiss_psd
    from tracks import track
    for tid in args.tracks:
        t = track(tid)
        sr, src, tape, _, _ = load(t.id)
        fh, Ph = hiss_psd(t, sr)  # the recorded tape's background noise (gaps between songs)
        hiss_db = db(bandpow(fh, Ph.mean(axis=1), 6000, 16000))
        d = decompose(src, tape, sr)
        print(f"== {t.id} {t.title}")
        print("  1. distortion vs level (test seconds): source level band -> explained share of residual, "
              "predicted distortion re tape")
        for name, rows in distortion_vs_level(d, sr).items():
            print(f"     {name}: " + " | ".join(f"{lv:5.1f} dB: {e * 100:+5.1f}% {rel:6.1f} dB" for lv, e, rel in rows))
        print(f"  2. treble residual (6-16 kHz) in silences vs time since the last loud block "
              f"(recorded-gap noise {hiss_db:.1f} dBFS):")
        print("     " + " | ".join(f"{lo:g}-{hi:g}s: {v:6.1f} dB (n={n})" for lo, hi, n, v in noise_after_sound(d, sr, hiss_db)))
        print("  3. modulation vs source level (4096-sample blocks; AM % / timing us, slow <100 Hz | fast >100 Hz rates):")
        for fc, rows in modulation_vs_level(d, sr).items():
            for name in "LR":
                print(f"     {fc:5d} {name}: " + " | ".join(
                    f"{lv:5.1f} dB: {c['slow'][0]:4.1f}%/{c['slow'][1]:4.2f}us  {c['fast'][0]:4.1f}%/{c['fast'][1]:4.2f}us"
                    for lv, c in rows[name]))


if __name__ == "__main__":
    main()
