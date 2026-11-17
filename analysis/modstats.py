"""Per-octave fast modulation of an aligned song: the numbers calibrate.py matches.

Works on the residual left after the linear prediction and the ~11 ms timing+gain fits
(investigate.decompose / fitprofile). In each octave band it refits gain and timing per short
window, against a null (same fit with the target shifted by 1 s), and reports:
  g_rms / g_null      amplitude flicker in that band (fraction RMS), and its estimator floor
  tau_rms / tau_null  timing jitter in that band (us RMS), and its floor
  shares              gain / timing / rest share of the band's leftover (louder half)
  rest_rel_db         what neither explains, re the band's signal (loud windows)
  left_rel_db         the whole leftover re the band's signal (loud windows)
  g_by_level          flicker excess (sqrt(raw^2 - null^2)) per source-level quartile
plus the flicker time series of each band, so cross-band correlation can be checked.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

from common import db
from investigate import band
from residual import fit_windows

# (lo, hi, window): octaves 1k..8k and the top band; the 1k band gets a longer window
BANDS = [(707, 1414, 128), (1414, 2828, 64), (2828, 5657, 64), (5657, 11314, 64), (11314, 16000, 64)]
CENTRES = [1000, 2000, 4000, 8000, 13000]


def excess(raw, null):
    return float(np.sqrt(max(raw ** 2 - null ** 2, 0.0)))


def octave_mod_stats(x, yhat, clean, sr):
    rows, series = [], []
    for (lo, hi, W), fc in zip(BANDS, CENTRES):
        hi = min(hi, 0.45 * sr)
        yb, rb, xb = band(yhat, sr, lo, hi), band(clean, sr, lo, hi), band(x, sr, lo, hi)
        dyb = np.gradient(yb) * sr
        sg, st, srest, tau, g, loud, lvl = fit_windows(rb, yb, dyb, xb, W)
        *_, taun, gn, _, _ = fit_windows(np.roll(rb, sr), yb, dyb, xb, W)
        n = len(g) * W
        rest = rb[:n] - np.repeat(g, W) * yb[:n] - np.repeat(tau, W) * dyb[:n]
        P = lambda v: (v[:n] ** 2).reshape(-1, W).sum(1)
        Yp, Rp, Lp = P(yb), P(rest), P(rb)
        rms = lambda v, m: float(np.sqrt(np.mean(v[m] ** 2)))
        g_raw, g_nul = rms(g, loud), rms(gn, loud)
        t_raw, t_nul = rms(tau, loud) * 1e6, rms(taun, loud) * 1e6
        q = np.percentile(lvl, [30, 50, 70, 85, 100])
        g_lv = []
        for a, b in zip(q[:-1], q[1:]):
            m = (lvl > a) & (lvl <= b)
            g_lv.append((float((a + b) / 2), excess(rms(g, m), rms(gn, m))))
        rows.append(dict(fc=fc, lo=lo, hi=hi, W=W, g_rms=g_raw, g_null=g_nul, g_exc=excess(g_raw, g_nul),
                         tau_rms=t_raw, tau_null=t_nul, tau_exc=excess(t_raw, t_nul),
                         share_g=sg, share_t=st, share_rest=srest,
                         rest_rel_db=float(db(Rp[loud].sum() / Yp[loud].sum())),
                         left_rel_db=float(db(Lp[loud].sum() / Yp[loud].sum())),
                         g_by_level=g_lv))
        series.append(dict(fc=fc, W=W, g=g, loud=loud))
    # cross-band: correlation of flicker between neighbouring bands with the same window
    for a, b in ((2000, 4000), (4000, 8000), (8000, 13000)):
        sa = next(s for s in series if s["fc"] == a)
        sb = next(s for s in series if s["fc"] == b)
        m = sa["loud"] & sb["loud"]
        rows[CENTRES.index(b)][f"corr_g_{a}"] = float(np.corrcoef(sa["g"][m], sb["g"][m])[0, 1])
    return rows, series


def print_rows(rows, label=""):
    print(f"  {label}octave  W    flicker% (null) exc   jitter us (null) exc   gain/timing/rest share   rest re sig  left re sig")
    for r in rows:
        print(f"  {r['fc']:6d} {r['W']:4d}   {r['g_rms'] * 100:5.1f} ({r['g_null'] * 100:4.1f}) {r['g_exc'] * 100:5.1f}"
              f"    {r['tau_rms']:5.2f} ({r['tau_null']:4.2f}) {r['tau_exc']:5.2f}"
              f"     {r['share_g'] * 100:4.0f} /{r['share_t'] * 100:4.0f} /{r['share_rest'] * 100:4.0f} %"
              f"      {r['rest_rel_db']:6.1f}     {r['left_rel_db']:6.1f}")


# ---------------------------------------------------------------- complex demodulation
def demod_spectra(yhat, r, sr, lo, hi, nper=16384, eps_rel=0.25):
    """Amplitude and phase modulation of the tape relative to the linear prediction, at full rate.

    In the band, with analytic signals Yh (prediction) and Rr (residual = tape - prediction):
        c(t) = Rr * conj(Yh) / (|Yh|^2 + eps)  ~  a(t) + j p(t)
    a = amplitude modulation (fraction), p = phase modulation (rad); p / (2 pi fc) is timing.
    Each is weighted by w = |Yh|^2 / (|Yh|^2 + eps), so quiet moments don't blow up, and its PSD is
    divided by mean(w^2). The null shifts the residual by 1 s: what an unrelated residual of the
    same level gives (hiss, estimator floor). Returns rate frequencies and PSDs (raw, null)."""
    hi = min(hi, 0.45 * sr)
    Yh = signal.hilbert(band(yhat, sr, lo, hi))
    Rr = signal.hilbert(band(r, sr, lo, hi))
    p2 = np.abs(Yh) ** 2
    eps = eps_rel * np.median(p2[p2 > np.median(p2)])
    out = {}
    for tag, rr in (("raw", Rr), ("null", np.roll(Rr, sr))):
        c = rr * np.conj(Yh) / (p2 + eps)
        w = p2 / (p2 + eps)
        norm = np.mean(w ** 2)
        f, Pa = signal.welch(c.real * w, sr, nperseg=nper)
        _, Pp = signal.welch(c.imag * w, sr, nperseg=nper)
        out[tag] = (Pa / norm, Pp / norm)
    keep = f <= (hi - lo) / 2  # beyond half the band width the estimate is aliasing band edges
    return f[keep], {k: (a[keep], p[keep]) for k, (a, p) in out.items()}


def demod_all(yhat, r, sr):
    """demod_spectra for every band in BANDS. Timing PSD in us^2/Hz via the band's centre."""
    res = []
    for (lo, hi, _), fc in zip(BANDS, CENTRES):
        f, d = demod_spectra(yhat, r, sr, lo, hi)
        k = (1e6 / (2 * np.pi * np.sqrt(lo * min(hi, 0.45 * sr)))) ** 2
        res.append(dict(fc=fc, f=f, am=d["raw"][0], am_null=d["null"][0],
                        tim=d["raw"][1] * k, tim_null=d["null"][1] * k))
    return res


RATE_BANDS = [(0.5, 4), (4, 20), (20, 45), (45, 120), (120, 350), (350, 800), (800, 2000)]


def demod_table(res):
    """Band-integrated excess (raw - null) RMS: AM in %, timing in us, per modulation-rate band."""
    rows = []
    for d in res:
        f = d["f"]
        cells = []
        for a, b in RATE_BANDS:
            m = (f >= a) & (f < b)
            if m.sum() < 1 or b > f[-1] * 1.01:
                cells.append((np.nan, np.nan, np.nan, np.nan))
                continue
            df = f[1] - f[0]
            am, am0 = d["am"][m].sum() * df, d["am_null"][m].sum() * df
            tm, tm0 = d["tim"][m].sum() * df, d["tim_null"][m].sum() * df
            cells.append((np.sqrt(max(am - am0, 0)) * 100, np.sqrt(am0) * 100,
                          np.sqrt(max(tm - tm0, 0)), np.sqrt(tm0)))
        rows.append((d["fc"], cells))
    return rows


def print_demod(rows, label=""):
    hdr = "  ".join(f"{a:g}-{b:g}".center(13) for a, b in RATE_BANDS)
    print(f"  {label}AM excess % (floor) per modulation-rate band [Hz]\n  octave  {hdr}")
    for fc, cells in rows:
        print(f"  {fc:6d}  " + "  ".join(("     -       " if np.isnan(c[0]) else f"{c[0]:5.1f} ({c[1]:4.1f})").center(13) for c in cells))
    print(f"  {label}timing excess us (floor)\n  octave  {hdr}")
    for fc, cells in rows:
        print(f"  {fc:6d}  " + "  ".join(("     -       " if np.isnan(c[2]) else f"{c[2]:5.2f} ({c[3]:4.2f})").center(13) for c in cells))
