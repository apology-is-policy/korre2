"""Deeper look at how the tape chain behaves, from aligned music (run align.py first).

    python investigate.py B3 A4 A6 [A5 ...]

Without test signals these are hypothesis tests on music, each with a null comparison:
  A. timing wobble: common to both channels (transport) or differing between them (tape skew)?
  B. does the music's loudness move the tape speed (e.g. battery sag under load)?
  C. treble gain vs level: memory (time constant) and cross-band coupling (does bass
     change the treble beyond the treble's own level?)
  D. harmonic distortion: 2nd/3rd-order Hammerstein fit on top of linear + timing + gain
  E. what is left: hiss vs noise that rides on the signal (modulation noise)
  F. dropouts: short gain dips
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy import signal

from common import bandpow, data_file, db, decode
from measure import OUT, apply_H, cross_spectra
from residual import fit_windows
from tracks import SIDE_FILES, track

RNG = np.random.default_rng(7)
W = 512  # samples per timing/gain window (~11 ms)
BLOCK = 1024  # samples per level block (~23 ms)


def load(tid):
    z = np.load(OUT / f"{tid}_aligned.npz")
    sr = int(z["sr"])
    trim = 3 * sr
    return sr, z["src"][trim:-trim].astype(np.float64), z["tape"][trim:-trim].astype(np.float64), z, trim


def blocks(x, n=BLOCK):
    m = len(x) // n
    return x[: m * n].reshape(m, n)


def band(x, sr, lo, hi, order=4):
    sos = signal.butter(order, [lo, min(hi, 0.45 * sr)], "bandpass", fs=sr, output="sos")
    return signal.sosfiltfilt(sos, x)


def lowpass(x, sr, fc, order=4):
    return signal.sosfiltfilt(signal.butter(order, fc, "lowpass", fs=sr, output="sos"), x)


def level_db(x, n=BLOCK):
    return db(np.mean(blocks(x, n) ** 2, axis=1))


def interp_over(mask, v):
    i = np.arange(len(v))
    return np.interp(i, i[mask], v[mask])


def null_max_abs_corr(a, b, lags, shifts=300, min_shift=None):
    """95th percentile of max |corr| over lags when b is circularly shifted at random."""
    n = len(a)
    min_shift = min_shift or n // 10
    out = []
    for _ in range(shifts):
        s = int(RNG.integers(min_shift, n - min_shift))
        out.append(np.max(np.abs(lagged_corr(a, np.roll(b, s), lags))))
    return float(np.percentile(out, 95))


def lagged_corr(a, b, lags):
    a = (a - a.mean()) / (a.std() + 1e-20)
    b = (b - b.mean()) / (b.std() + 1e-20)
    n = len(a)
    return np.array([np.mean(a[max(0, -k): n - max(0, k)] * b[max(0, k): n - max(0, -k)]) for k in lags])


# ---------------------------------------------------------------- per-channel decomposition
def decompose(src, tape, sr):
    """Linear prediction, residual, and per-window gain/timing fits for both channels."""
    out = {}
    for c, name in ((0, "L"), (1, "R")):
        x, y = src[:, c], tape[:, c]
        f, Pxx, _, Pxy = cross_spectra(x, y, sr)
        yhat = apply_H(x, f, Pxy / Pxx)
        r = y - yhat
        dy = np.gradient(yhat) * sr
        *_, tau, g, loud, lvl = fit_windows(r, yhat, dy, x, W)
        *_, tau0, _, _, _ = fit_windows(r, yhat, np.roll(dy, sr), x, W)
        n = len(tau) * W
        clean = r[:n] - np.repeat(g, W) * yhat[:n] - np.repeat(tau, W) * dy[:n]
        out[name] = dict(x=x[:n], y=y[:n], yhat=yhat[:n], r=r[:n], clean=clean, tau=tau, tau_null=tau0,
                         g=g, lvl=lvl)
    return out


# ---------------------------------------------------------------- A. common vs differential timing
def timing_common_vs_diff(d, sr):
    L, R = d["L"], d["R"]
    ok = (L["lvl"] > np.percentile(L["lvl"], 40)) & (R["lvl"] > np.percentile(R["lvl"], 40))
    tl, tr = L["tau"] * 1e6, R["tau"] * 1e6
    com, dif = (tl + tr) / 2, tl - tr
    dif_null = (L["tau_null"] - R["tau_null"]) * 1e6
    fs = sr / W
    lim = lambda v: np.clip(interp_over(ok, v), -150, 150)
    f, C = signal.coherence(lim(tl), lim(tr), fs, nperseg=1024)
    res = dict(rms_common=np.std(com[ok]), rms_diff=np.std(dif[ok]), rms_diff_null=np.std(dif_null[ok]),
               corr_LR=np.corrcoef(tl[ok], tr[ok])[0, 1])
    res["coh_bands"] = {f"{lo}-{hi}": float(C[(f >= lo) & (f < hi)].mean()) for lo, hi in [(1, 4), (4, 10), (10, 30), (30, 80)]}
    res["coh_peaks"] = {p: float(C[np.argmin(np.abs(f - p))]) for p in (7.5, 25.5, 30.1, 43.6)}
    fd, Pd = signal.welch(lim(dif), fs, nperseg=1024)
    prom = 10 * np.log10(Pd + 1e-30) - signal.medfilt(10 * np.log10(Pd + 1e-30), 31)
    pk, _ = signal.find_peaks(prom, height=8, distance=3)
    res["diff_peaks"] = [round(float(fd[k]), 1) for k in pk if 1 < fd[k] < 80][:8]
    return res


# ---------------------------------------------------------------- B. speed vs loudness
def speed_vs_loudness(z, sr):
    dev_t, dev = z["dev_t"], z["dev"]
    src = z["src"].astype(np.float64).mean(axis=1)
    keep = (dev_t > 3) & (dev_t < len(src) / sr - 3)
    dev_t, dev = dev_t[keep], dev[keep]
    half = 1024
    idx = (dev_t * sr).astype(int)
    bass = lowpass(src, sr, 150)
    env = np.array([db(np.mean(src[i - half:i + half] ** 2)) for i in idx])
    benv = np.array([db(np.mean(bass[i - half:i + half] ** 2)) for i in idx])
    fs = 1 / np.median(np.diff(dev_t))
    lags = np.arange(-int(2 * fs), int(2 * fs) + 1)
    res = {}
    for name, e in (("broadband", env), ("bass<150Hz", benv)):
        cc = lagged_corr(dev, e, lags)
        k = int(np.argmax(np.abs(cc)))
        res[name] = dict(max_r=float(cc[k]), lag_s=float(lags[k] / fs), null95=null_max_abs_corr(dev, e, lags))
    return res


# ---------------------------------------------------------------- C. treble gain: memory and cross-band
def binned_r2(G, X, bins=12):
    edges = np.percentile(X, np.linspace(0, 100, bins + 1))
    idx = np.clip(np.searchsorted(edges, X, side="right") - 1, 0, bins - 1)
    means = np.array([G[idx == i].mean() if (idx == i).any() else 0 for i in range(bins)])
    fit = means[idx]
    return 1 - np.var(G - fit) / np.var(G), G - fit


def ema_db(level_db, block_s, tau_s):
    if tau_s <= 0:
        return level_db
    p = 10 ** (level_db / 10)
    a = np.exp(-block_s / tau_s)
    out = signal.lfilter([1 - a], [1, -a], p)
    return db(out)


def treble_behaviour(src, tape, sr):
    res = {}
    block_s = BLOCK / sr
    for fc in (6300, 10000):
        lo, hi = fc / 2 ** (1 / 6), fc * 2 ** (1 / 6)
        Lt, Yt, Lb, Lm, Lall = [], [], [], [], []
        for c in (0, 1):
            Lt.append(level_db(band(src[:, c], sr, lo, hi)))
            Yt.append(level_db(band(tape[:, c], sr, lo, hi)))
            Lb.append(level_db(band(src[:, c], sr, 40, 150, order=2)))
            Lm.append(level_db(band(src[:, c], sr, 300, 2000, order=2)))
            Lall.append(level_db(src[:, c]))
        out = {}
        G_all = []
        for c in (0, 1):
            ok = Lt[c] > np.percentile(Lt[c], 30)
            G = (Yt[c] - Lt[c])
            scan = {}
            for tau in (0, 0.05, 0.2, 1.0, 5.0):
                X = ema_db(Lt[c], block_s, tau)
                scan[tau], _ = binned_r2(G[ok], X[ok])
            r2_0, resid = binned_r2(G[ok], Lt[c][ok])
            cross = {}
            for name, other in (("bass", Lb[c]), ("mid", Lm[c]), ("broadband", Lall[c])):
                o = other[ok]
                r = np.corrcoef(resid, o)[0, 1]
                null = np.percentile([abs(np.corrcoef(resid, np.roll(o, int(RNG.integers(len(o) // 10, len(o) * 9 // 10))))[0, 1])
                                      for _ in range(200)], 95)
                slope = np.polyfit(o, resid, 1)[0] * 10
                cross[name] = dict(r=float(r), null95=float(null), db_per_10db=float(slope))
            top = ok & (Lt[c] > np.percentile(Lt[c][ok], 50))
            slope_top = np.polyfit(Lt[c][top], G[top], 1)[0]
            out["LR"[c]] = dict(r2_by_tau=scan, cross=cross, slope_top_half=float(slope_top))
            G_all.append(G[ok])
        res[fc] = out
    return res


# ---------------------------------------------------------------- D. Hammerstein 2nd/3rd order
def xcorr_lags(a, b, maxlag):
    """c[k] = sum_n a[n] b[n+k] for k in -maxlag..maxlag."""
    n = 1 << int(np.ceil(np.log2(len(a) + maxlag + 1)))
    c = np.fft.irfft(np.conj(np.fft.rfft(a, n)) * np.fft.rfft(b, n), n)
    return np.concatenate((c[-maxlag:], c[: maxlag + 1]))


def fit_fir_multi(feats, target, K):
    """Least squares sum_i h_i * feat_i ~ target with K-tap causal FIRs, via correlations."""
    m = len(feats)
    A = np.zeros((m * K, m * K))
    bvec = np.zeros(m * K)
    for i in range(m):
        cr = xcorr_lags(feats[i], target, K - 1)
        bvec[i * K:(i + 1) * K] = cr[K - 1:]  # E[f_i(n-k) y(n)] = c_{f_i,y}[k]
        for j in range(m):
            cij = xcorr_lags(feats[i], feats[j], K - 1)  # E[f_i(n-a) f_j(n-b)] = c_ij[a-b]
            for a_ in range(K):
                A[i * K + a_, j * K:(j + 1) * K] = cij[K - 1 + a_ - np.arange(K)]
    h = np.linalg.solve(A + 1e-9 * np.trace(A) / len(A) * np.eye(len(A)), bvec)
    return [h[i * K:(i + 1) * K] for i in range(m)]


def predict(feats, hs):
    return sum(signal.lfilter(h, [1.0], f) for f, h in zip(feats, hs))


def preemph(x, sr, t1=70e-6, gain_db=12):
    """First-order high shelf as a stand-in for the record pre-emphasis."""
    t2 = t1 / 10 ** (gain_db / 20)
    b, a = signal.bilinear([t1, 1], [t2, 1], fs=sr)
    return signal.lfilter(b, a, x)


def hammerstein(d, sr, K=32):
    res = {}
    for name in ("L", "R"):
        ch = d[name]
        target = ch["clean"]
        n = len(target)
        half = n // 2
        lvl = level_db(ch["x"])
        loud_blocks = lvl > np.median(lvl)
        loud = np.repeat(loud_blocks, BLOCK)[:n]
        loud = np.pad(loud, (0, n - len(loud)))
        out = {}
        for variant in ("flat", "pre-emphasised"):
            u = ch["x"] if variant == "flat" else preemph(ch["x"], sr)
            u = u / (np.std(u) + 1e-20)
            p2, p3 = u ** 2 - np.mean(u ** 2), u ** 3
            for terms, feats in (("2nd", [p2]), ("3rd", [p3]), ("2nd+3rd", [p2, p3])):
                hs = fit_fir_multi([f[:half] for f in feats], target[:half], K)
                pred = predict([f[half:] for f in feats], hs)
                tt = target[half:]
                expl = 1 - np.sum((tt - pred) ** 2) / np.sum(tt ** 2)
                lh = loud[half:].astype(bool)
                expl_loud = 1 - np.sum((tt[lh] - pred[lh]) ** 2) / np.sum(tt[lh] ** 2)
                # level of the predicted distortion relative to the tape signal in loud blocks
                rel = db(np.sum(pred[lh] ** 2) / np.sum(ch["y"][half:][lh] ** 2))
                out[f"{variant} {terms}"] = dict(explained=float(expl), explained_loud=float(expl_loud), rel_db_loud=float(rel))
        res[name] = out
    return res


# ---------------------------------------------------------------- E. what is left
def leftover(d, sr, hiss_psd):
    fh, Ph = hiss_psd
    res = {}
    for fc in (500, 1000, 2000, 4000, 8000):
        lo, hi = fc / 2 ** 0.5, fc * 2 ** 0.5
        hiss_db = db(bandpow(fh, Ph, lo, hi))
        S, Rr = [], []
        for name in ("L", "R"):
            S.append(level_db(band(d[name]["x"], sr, lo, hi, order=2)))
            Rr.append(level_db(band(d[name]["clean"], sr, lo, hi, order=2)))
        S, Rr = np.concatenate(S), np.concatenate(Rr)
        top = S > np.percentile(S, 50)
        slope = np.polyfit(S[top], Rr[top], 1)[0]
        q = np.percentile(S, [10, 90])
        res[fc] = dict(hiss_db=float(hiss_db), quiet_left_db=float(np.median(Rr[S < q[0]])),
                       loud_left_db=float(np.median(Rr[S > q[1]])), loud_src_db=float(np.median(S[S > q[1]])),
                       slope_top_half=float(slope))
    return res


def treble_fast(d, sr, lo=3000, hi=10000):
    """Refit what is left in the treble band with very short windows: is it fast timing
    jitter (scrape flutter), fast amplitude flicker (head contact), or neither?"""
    res = {}
    for name in ("L", "R"):
        ch = d[name]
        yb = band(ch["yhat"], sr, lo, hi)
        rb = band(ch["clean"], sr, lo, hi)
        dyb = np.gradient(yb) * sr
        xb = band(ch["x"], sr, lo, hi)
        row = {}
        for Wf in (256, 64, 16):
            sg, st, srest, tau, g, loud, _ = fit_windows(rb, yb, dyb, xb, Wf)
            _, st0, *_ = fit_windows(rb, yb, np.roll(dyb, sr), xb, Wf)
            sg0, *_ = fit_windows(rb, np.roll(yb, sr), dyb, xb, Wf)
            row[Wf] = dict(gain=sg, timing=st, rest=srest, timing_null=st0, gain_null=sg0,
                           tau_rms=float(np.sqrt(np.mean(tau[loud] ** 2)) * 1e6),
                           g_rms=float(np.sqrt(np.mean(g[loud] ** 2)) * 100))
        res[name] = row
    return res


# ---------------------------------------------------------------- F. dropouts
def dropouts(d, sr):
    res = {}
    minutes = len(d["L"]["g"]) * W / sr / 60
    gl, gr = d["L"]["g"], d["R"]["g"]
    loud = (d["L"]["lvl"] > np.percentile(d["L"]["lvl"], 50)) & (d["R"]["lvl"] > np.percentile(d["R"]["lvl"], 50))
    for thr_db in (-1.0, -2.0, -3.0):
        thr = 10 ** (thr_db / 20) - 1
        dl, dr = loud & (gl < thr), loud & (gr < thr)
        res[thr_db] = dict(L_per_min=dl.sum() / minutes, R_per_min=dr.sum() / minutes,
                           both_per_min=(dl & dr).sum() / minutes)
    return res


# ---------------------------------------------------------------- report
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    args = ap.parse_args()
    for tid in args.tracks:
        t = track(tid)
        sr, src, tape, z, trim = load(t.id)
        from signature import hiss_psd
        fh, Ph = hiss_psd(t, sr)  # the recorded tape's background noise (gaps between songs)
        print("=" * 90)
        print(f"{t.id} {t.title or ''}  ({len(src) / sr:.0f} s, {sr} Hz)")
        print("=" * 90)
        d = decompose(src, tape, sr)

        a = timing_common_vs_diff(d, sr)
        print("A. timing wobble (per ~11 ms window, loud windows):")
        print(f"   common (both channels) {a['rms_common']:.1f} us RMS | L-R difference {a['rms_diff']:.1f} us RMS"
              f" (null-test floor {a['rms_diff_null']:.1f}) | corr(L,R) {a['corr_LR']:.2f}")
        print("   L/R coherence of the wobble by band: " + ", ".join(f"{k} Hz {v:.2f}" for k, v in a["coh_bands"].items()))
        print("   ... at the mechanical peaks: " + ", ".join(f"{k} Hz {v:.2f}" for k, v in a["coh_peaks"].items()))
        print(f"   peaks in the L-R difference: {a['diff_peaks'] or 'none'}")

        b = speed_vs_loudness(z, sr)
        print("B. speed vs loudness (speed deviation vs source level, lags +-2 s):")
        for k, v in b.items():
            print(f"   {k:11}: max r {v['max_r']:+.3f} at {v['lag_s']:+.2f} s  (95% null {v['null95']:.3f})"
                  f"  {'<- above null' if abs(v['max_r']) > v['null95'] else ''}")

        c = treble_behaviour(src, tape, sr)
        print("C. treble gain vs level (1/3-octave, 23 ms blocks):")
        for fc, chs in c.items():
            for chn, v in chs.items():
                scan = "  ".join(f"{tau:g}s:{r2:.3f}" for tau, r2 in v["r2_by_tau"].items())
                print(f"   {fc:5d} Hz {chn}: slope in loud half {v['slope_top_half']:+.3f} dB/dB | R2 vs level smoothed over {scan}")
                print("              after own level, residual vs " + " | ".join(
                    f"{k} r {w['r']:+.3f} (null {w['null95']:.3f}) {w['db_per_10db']:+.2f} dB/10dB" for k, w in v["cross"].items()))

        h = hammerstein(d, sr)
        print("D. harmonic distortion (FIR-Hammerstein, fit on 1st half, tested on 2nd half):")
        for chn, v in h.items():
            for k, w in v.items():
                print(f"   {chn} {k:24}: explains {w['explained'] * 100:5.1f}% of the cleaned residual"
                      f" ({w['explained_loud'] * 100:5.1f}% in loud blocks); level re tape (loud) {w['rel_db_loud']:6.1f} dB")

        e = leftover(d, sr, (fh, Ph.mean(axis=1)))
        print("E. what is left after linear + timing + gain (octave bands, dBFS):")
        print("    band   hiss   left(quiet)  left(loud)  src(loud)  slope(loud half, dB/dB: 0 = hiss, 1 = rides on signal)")
        for fc, v in e.items():
            print(f"   {fc:5d}  {v['hiss_db']:6.1f}   {v['quiet_left_db']:6.1f}     {v['loud_left_db']:6.1f}    "
                  f"{v['loud_src_db']:6.1f}     {v['slope_top_half']:+.2f}")

        e2 = treble_fast(d, sr)
        print("E2. what is left in 3-10 kHz, refit with short windows (shares over the louder half; null in brackets):")
        for chn, rows in e2.items():
            for Wf, v in rows.items():
                print(f"   {chn} {Wf:4d} ({Wf / sr * 1e3:4.2f} ms): timing {v['timing'] * 100:5.1f}% [{v['timing_null'] * 100:4.1f}]"
                      f"  gain {v['gain'] * 100:5.1f}% [{v['gain_null'] * 100:4.1f}]  rest {v['rest'] * 100:5.1f}%"
                      f"  | timing {v['tau_rms']:.2f} us RMS, gain {v['g_rms']:.1f}% RMS")

        f_ = dropouts(d, sr)
        print("F. dropouts (loud windows with gain dips; per minute):")
        print("   " + " | ".join(f"<{k:+.0f} dB: L {v['L_per_min']:.1f}, R {v['R_per_min']:.1f}, both {v['both_per_min']:.1f}"
                                 for k, v in f_.items()))


if __name__ == "__main__":
    main()
