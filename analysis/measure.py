"""Measure the tape chain from an aligned source/tape pair (run align.py first).

    python measure.py B3

  * linear part: frequency response per channel, coherence (how much of the tape
    output a linear filter of the source explains), per-channel delay vs the source.
    The response is given two ways: H1 = Pxy/Pxx (phase-sensitive, so residual timing
    jitter drags it down in the treble) and power-only = (Pyy - hiss)/Pxx (insensitive to
    jitter, slightly inflated by distortion). The truth is close to power-only here.
  * what's left after the linear part (residual = tape - H*source): level vs source
    level, spectrum in loud vs quiet passages, compared with the blank-tape hiss
  * gain vs level in narrow bands (compression); broadband bands would mix in the
    spectral-tilt difference between loud and quiet passages
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy import signal

from common import bandpow, data_file, db, decode
from tracks import SIDE_FILES, track

OUT = Path(__file__).resolve().parent / "out"
NPER = 8192
BLOCK = 4096
THIRDS = [25 * 2 ** (k / 3) for k in range(0, 30)]  # 25 Hz .. ~16 kHz
THIRDS = [f for f in THIRDS if f < 20500]


def cross_spectra(x, y, sr):
    f, Pxx = signal.welch(x, sr, nperseg=NPER)
    _, Pyy = signal.welch(y, sr, nperseg=NPER)
    _, Pxy = signal.csd(x, y, sr, nperseg=NPER)  # conj(X) * Y
    return f, Pxx, Pyy, Pxy


def band_avg(f, v, lo, hi):
    m = (f >= lo) & (f < hi)
    return v[m].mean() if m.any() else np.nan


def phase_delay(f, H, coh, lo=1000, hi=8000):
    """Weighted linear fit of unwrapped phase -> delay in microseconds (positive = tape late)."""
    m = (f >= lo) & (f <= hi)
    ph = np.unwrap(np.angle(H[m]))
    w = coh[m]
    A = np.vstack([f[m], np.ones(m.sum())]).T * w[:, None]
    slope, _ = np.linalg.lstsq(A, ph * w, rcond=None)[0]
    return -slope / (2 * np.pi) * 1e6


def apply_H(x, f, H):
    n = 1 << int(np.ceil(np.log2(len(x) + NPER)))
    fine = np.fft.rfftfreq(n, 1 / (2 * f[-1]))
    Hf = np.interp(fine, f, H.real) + 1j * np.interp(fine, f, H.imag)
    return np.fft.irfft(np.fft.rfft(x, n) * Hf, n)[: len(x)]


def blocks_db(x):
    n = len(x) // BLOCK
    return db(np.mean(x[: n * BLOCK].reshape(n, BLOCK) ** 2, axis=1))


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

    hiss = decode(data_file(SIDE_FILES[t.side]), 3.6 if t.side == "B" else 3.2,
                  10.0 if t.side == "B" else 9.8, sr=sr).astype(np.float64)
    fh, Ph = signal.welch(hiss, sr, nperseg=NPER, axis=0)
    Ph = Ph.mean(axis=1)

    res = {}
    for c, name in ((0, "L"), (1, "R")):
        f, Pxx, Pyy, Pxy = cross_spectra(src[:, c], tape[:, c], sr)
        H = Pxy / Pxx
        coh = np.abs(Pxy) ** 2 / (Pxx * Pyy)
        yhat = apply_H(src[:, c], f, H)
        res[name] = dict(f=f, H=H, coh=coh, Pxx=Pxx, Pyy=Pyy, resid=tape[:, c] - yhat, yhat=yhat)

    f = res["L"]["f"]
    g1k = {k: 20 * np.log10(np.abs(band_avg(f, v["H"], 900, 1100))) for k, v in res.items()}
    print(f"{t.id} {t.title or ''}: {len(src) / sr:.1f} s analysed (3 s trimmed each end)")
    print(f"\nGAIN at 1 kHz (tape vs source): L {g1k['L']:+.2f} dB, R {g1k['R']:+.2f} dB, L-R {g1k['L'] - g1k['R']:+.2f} dB")
    dl = phase_delay(f, res["L"]["H"], res["L"]["coh"])
    dr = phase_delay(f, res["R"]["H"], res["R"]["coh"])
    print(f"DELAY vs source after warping (1-8 kHz phase fit): L {dl:+.1f} us, R {dr:+.1f} us, "
          f"L-R {dl - dr:+.1f} us (+ = left later)")

    Ph_f = np.interp(f, fh, Ph)
    for v in res.values():
        v["Hpow"] = np.maximum(v["Pyy"] - Ph_f, 1e-30) / v["Pxx"]

    def pow_db(v, lo, hi, ref):
        """Power-only response in a band, in dB (re its 1 kHz value when ref=True)."""
        level = 10 * np.log10(band_avg(f, v["Hpow"], lo, hi))
        return level - 10 * np.log10(band_avg(f, v["Hpow"], 900, 1100)) if ref else level

    print("\nLINEAR PART per 1/3 octave: response re 1 kHz [dB] (H1 and power-only), coherence, unexplained share")
    print("   freq    H1 L    H1 R   pow L   pow R  L-R(pow)  coh L  coh R   unexplained L/R [dB]")
    for fc in THIRDS:
        lo, hi = fc / 2 ** (1 / 6), fc * 2 ** (1 / 6)
        rL = 20 * np.log10(np.abs(band_avg(f, res["L"]["H"], lo, hi))) - g1k["L"]
        rR = 20 * np.log10(np.abs(band_avg(f, res["R"]["H"], lo, hi))) - g1k["R"]
        pL, pR = pow_db(res["L"], lo, hi, True), pow_db(res["R"], lo, hi, True)
        lr = pow_db(res["L"], lo, hi, False) - pow_db(res["R"], lo, hi, False)
        cL, cR = band_avg(f, res["L"]["coh"], lo, hi), band_avg(f, res["R"]["coh"], lo, hi)
        uL, uR = db(1 - min(cL, 0.99999)), db(1 - min(cR, 0.99999))
        print(f"  {fc:7.0f}  {rL:+6.2f}  {rR:+6.2f}  {pL:+6.2f}  {pR:+6.2f}  {lr:+6.2f}    {cL:.3f}  {cR:.3f}   {uL:6.1f} / {uR:6.1f}")

    # ---- residual vs level
    print("\nRESIDUAL (tape minus linear prediction) vs SOURCE LEVEL, 93 ms blocks, L+R pooled")
    print(f"  blank-tape hiss for reference: {db(bandpow(fh, Ph, 20, 20000)):.1f} dBFS (20 Hz-20 kHz)")
    print("  source level   blocks   tape level   residual   residual re tape   residual 4-16 kHz")
    sos_hf = signal.butter(4, [4000, 16000], "bandpass", fs=sr, output="sos")
    S, Y, R, RH = [], [], [], []
    for name in ("L", "R"):
        c = 0 if name == "L" else 1
        S.append(blocks_db(src[:, c]))
        Y.append(blocks_db(tape[:, c]))
        R.append(blocks_db(res[name]["resid"]))
        RH.append(blocks_db(signal.sosfiltfilt(sos_hf, res[name]["resid"])))
    S, Y, R, RH = map(np.concatenate, (S, Y, R, RH))
    for lo in range(-60, 0, 6):
        m = (S >= lo) & (S < lo + 6)
        if m.sum() < 10:
            continue
        print(f"  {lo:4d}..{lo + 6:4d} dB   {m.sum():6d}   {np.mean(Y[m]):8.1f}   {np.mean(R[m]):8.1f}"
              f"       {np.mean(R[m] - Y[m]):+7.1f} dB        {np.mean(RH[m]):7.1f}")

    # ---- residual spectrum: loud vs quiet blocks vs hiss
    print("\nRESIDUAL SPECTRUM per octave [dBFS], loudest vs quietest quarter of blocks, vs blank-tape hiss")
    q_lo, q_hi = np.percentile(S, [25, 75])
    rows = {"quiet": [], "loud": []}
    for name in ("L", "R"):
        c = 0 if name == "L" else 1
        sb = blocks_db(src[:, c])
        r = res[name]["resid"]
        nb = len(sb)
        blk = r[: nb * BLOCK].reshape(nb, BLOCK)
        for key, sel in (("quiet", sb < q_lo), ("loud", sb > q_hi)):
            rows[key].append(blk[sel].reshape(-1))
    print("  octave   " + "  ".join(f"{c:>7g}" for c in [63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]))
    for key in ("quiet", "loud"):
        fr, Pr = signal.welch(np.concatenate(rows[key]), sr, nperseg=NPER)
        vals = [db(bandpow(fr, Pr, c / 2 ** 0.5, c * 2 ** 0.5)) for c in [63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]]
        print(f"  {key:7}  " + "  ".join(f"{v:7.1f}" for v in vals))
    vals = [db(bandpow(fh, Ph, c / 2 ** 0.5, c * 2 ** 0.5)) for c in [63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]]
    print(f"  {'hiss':7}  " + "  ".join(f"{v:7.1f}" for v in vals))

    # ---- compression: gain vs level within narrow bands
    print("\nGAIN vs LEVEL per 1/3-octave band (tape minus source, 93 ms blocks, L+R pooled, re median gain)")
    print("  source band level quintiles -> gain; a drop at the top = compression")
    for fc in (250, 1000, 3150, 6300, 10000):
        lo, hi = fc / 2 ** (1 / 6), fc * 2 ** (1 / 6)
        sos = signal.butter(4, [lo, hi], "bandpass", fs=sr, output="sos")
        S, G = [], []
        for c in (0, 1):
            sb = blocks_db(signal.sosfiltfilt(sos, src[:, c]))
            yb = blocks_db(signal.sosfiltfilt(sos, tape[:, c]))
            S.append(sb); G.append(yb - sb)
        S, G = np.concatenate(S), np.concatenate(G)
        ok = S > np.percentile(S, 10)
        G = G - np.median(G[ok])
        edges = np.percentile(S[ok], [0, 20, 40, 60, 80, 95, 100])
        cells = []
        for a, b in zip(edges[:-1], edges[1:]):
            m = ok & (S >= a) & (S <= b)
            cells.append(f"{(a + b) / 2:6.1f} dB: {np.median(G[m]):+5.2f}")
        print(f"  {fc:5d} Hz   " + "   ".join(cells))

    np.savez(OUT / f"{t.id}_linear.npz", sr=sr, f=f, HL=res["L"]["H"], HR=res["R"]["H"],
             cohL=res["L"]["coh"], cohR=res["R"]["coh"])


if __name__ == "__main__":
    main()
