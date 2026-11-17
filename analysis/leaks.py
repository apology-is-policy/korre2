"""Does signal leak into a tape channel from somewhere else? (run align.py first)

    python leaks.py B3 [B3emu A6 ...]

Everything else here predicts each tape channel from the same source channel at the same moment.
Tape has three classic leaks that such a model misses, each tested against a null:
  1. crosstalk    the other channel: 2-input fit  tape_L = H_LL * src_L + H_LR * src_R  per frequency.
                  Reported per octave: leak level re the direct path, its phase, and how much of the
                  single-channel residual it explains. Unreliable where the source channels are
                  nearly identical (inter-channel coherence > 0.9): flagged with *.
                  Null: the same fit with the other channel shifted by 1 s.
  2. print-through  other moments of the same song (neighbouring tape layers): correlation of the
                  residual with the source at lags of +-0.3..6 s, in the 300 Hz-3 kHz band.
                  Null: the spread of the correlation over all those lags (a real echo stands out).
  3. low band     what is left below 700 Hz after the linear prediction, per octave, loud and quiet
                  blocks, re the signal and absolute, next to the blank-tape hiss.
An emulation (no leaks by construction) run through the same script is the reference.
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy import signal

from common import db
from investigate import band, load
from measure import apply_H, cross_spectra
from signature import hiss_psd
from tracks import track

OCTS = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 12500]
NPER = 1 << 15


def crosstalk(src, tape, sr, shift=0):
    """2x2 least squares per frequency. Returns per octave, for each output channel:
    leak level dB re direct, leak phase re direct (deg), share of the single-input residual
    explained by adding the other channel, and the source inter-channel coherence."""
    x = [src[:, 0], src[:, 1]]
    if shift:
        x_other = [np.roll(x[1], shift), np.roll(x[0], shift)]
    S = lambda a, b: signal.csd(a, b, sr, nperseg=NPER)[1]  # conj(A) * B
    f = np.fft.rfftfreq(NPER, 1 / sr)
    rows = {}
    for c, name in ((0, "L"), (1, "R")):
        own = x[c]
        oth = x_other[c] if shift else x[1 - c]
        y = tape[:, c]
        Saa, Sbb, Sab = S(own, own).real, S(oth, oth).real, S(own, oth)
        Say, Sby, Syy = S(own, y), S(oth, y), S(y, y).real
        det = Saa * Sbb - np.abs(Sab) ** 2
        Hd = (Sbb * Say - Sab * Sby) / det          # direct path
        Hx = (Saa * Sby - np.conj(Sab) * Say) / det  # leak from the other channel
        res1 = Syy - np.abs(Say) ** 2 / Saa          # residual power, single input
        res2 = Syy - (np.conj(Hd) * Say + np.conj(Hx) * Sby).real  # residual power, two inputs
        coh_src = np.abs(Sab) ** 2 / (Saa * Sbb)
        out = []
        for fc in OCTS:
            m = (f >= fc / 2 ** 0.5) & (f < min(fc * 2 ** 0.5, 0.45 * sr))
            # power-weighted: the leak as it actually arrives, |Hx|^2 * S_other vs |Hd|^2 * S_own
            leak = db((np.abs(Hx[m]) ** 2 * Sbb[m]).sum() / (np.abs(Hd[m]) ** 2 * Saa[m]).sum())
            ratio = db((np.abs(Hx[m]) ** 2).mean() / (np.abs(Hd[m]) ** 2).mean())
            ph = np.degrees(np.angle((Hx[m] * np.conj(Hd[m]) * Sbb[m]).sum()))
            expl = 1 - res2[m].sum() / res1[m].sum()
            out.append(dict(fc=fc, ratio_db=float(ratio), leak_db=float(leak), phase=float(ph),
                            explained=float(expl), coh_src=float(np.average(coh_src[m], weights=Saa[m]))))
        rows[name] = out
    return rows


def print_through(src, tape, sr, max_lag_s=6.0, min_lag_s=0.3, dec=8):
    """Normalised correlation of the residual with the source at long lags (300 Hz-3 kHz)."""
    res = {}
    for c, name in ((0, "L"), (1, "R")):
        x, y = src[:, c], tape[:, c]
        f, Pxx, _, Pxy = cross_spectra(x, y, sr)
        r = y - apply_H(x, f, Pxy / Pxx)
        xb = signal.decimate(band(x, sr, 300, 3000), dec, ftype="fir", zero_phase=True)
        rb = signal.decimate(band(r, sr, 300, 3000), dec, ftype="fir", zero_phase=True)
        fs = sr / dec
        n = 1 << int(np.ceil(np.log2(2 * len(xb))))
        cc = np.fft.irfft(np.fft.rfft(rb, n) * np.conj(np.fft.rfft(xb, n)), n)
        cc /= np.sqrt(np.sum(xb ** 2) * np.sum(rb ** 2))
        L = int(max_lag_s * fs)
        lags = np.arange(-L, L + 1) / fs  # positive: the residual repeats the source later (post-echo)
        v = np.concatenate((cc[-L:], cc[: L + 1]))
        env = np.abs(signal.hilbert(v))
        far = np.abs(lags) >= min_lag_s
        spread = np.std(v[far])
        k = np.argsort(env * far)[::-1]
        peaks = []
        for i in k:  # strongest envelope peaks at least 50 ms apart
            if all(abs(lags[i] - p[0]) > 0.05 for p in peaks):
                peaks.append((float(lags[i]), float(env[i]), float(env[i] / spread)))
            if len(peaks) == 4:
                break
        # echo level: correlation coefficient * residual RMS / source RMS = echo amplitude re source
        gain = np.sqrt(np.sum(rb ** 2) / np.sum(xb ** 2))
        res[name] = dict(spread=float(spread), peaks=[(l, db((e * gain) ** 2), s) for l, e, s in peaks])
    return res


def low_band(src, tape, sr, hiss):
    fh, Ph = hiss
    out = {}
    for c, name in ((0, "L"), (1, "R")):
        x, y = src[:, c], tape[:, c]
        f, Pxx = signal.welch(x, sr, nperseg=1 << 16)
        _, Pxy = signal.csd(x, y, sr, nperseg=1 << 16)
        yhat = apply_H(x, f, Pxy / Pxx)  # 0.7 Hz resolution: the bass phase is steep
        r = y - yhat
        rows = []
        for fc in (31.5, 63, 125, 250, 500):
            lo, hi = fc / 2 ** 0.5, fc * 2 ** 0.5
            yb, rb = band(yhat, sr, lo, hi, order=2), band(r, sr, lo, hi, order=2)
            B = 8192
            nb = len(yb) // B
            py = (yb[: nb * B] ** 2).reshape(nb, B).mean(1)
            pr = (rb[: nb * B] ** 2).reshape(nb, B).mean(1)
            loud, quiet = py > np.percentile(py, 75), py < np.percentile(py, 15)
            mh = (fh >= lo) & (fh < hi)
            rows.append(dict(fc=fc, sig_loud=float(db(py[loud].mean())), res_loud=float(db(pr[loud].mean())),
                             rel_loud=float(db(pr[loud].sum() / py[loud].sum())),
                             sig_quiet=float(db(py[quiet].mean())), res_quiet=float(db(np.median(pr[quiet]))),
                             hiss=float(db(np.trapezoid(Ph[mh, c], fh[mh])))))
        out[name] = rows
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    args = ap.parse_args()
    for tid in args.tracks:
        t = track(tid)
        sr, src, tape, z, trim = load(t.id)
        print("=" * 100)
        print(f"{t.id} {t.title or ''}")
        print("1. crosstalk: leak from the other channel, per octave (* = source channels too alike to tell)")
        real, null = crosstalk(src, tape, sr), crosstalk(src, tape, sr, shift=sr)
        print("   octave   " + "  ".join(f"{fc:g}".rjust(7) for fc in OCTS))
        for name in "LR":
            other = "R" if name == "L" else "L"
            print(f"   into {name} from {other}: path gain re direct [dB] "
                  + " ".join(f"{r['ratio_db']:7.1f}{'*' if r['coh_src'] > 0.9 else ' '}" for r in real[name]))
            print(f"                  phase re direct [deg]   "
                  + " ".join(f"{r['phase']:+7.0f} " for r in real[name]))
            print(f"                  residual explained [%]  "
                  + " ".join(f"{r['explained'] * 100:7.1f} " for r in real[name]))
            print(f"                  null: path gain [dB]    "
                  + " ".join(f"{r['ratio_db']:7.1f} " for r in null[name]))
            print(f"                  null: explained [%]     "
                  + " ".join(f"{r['explained'] * 100:7.1f} " for r in null[name]))
        print("2. print-through: strongest correlations of the residual with the source at |lag| 0.3-6 s (300 Hz-3 kHz)")
        for name, v in print_through(src, tape, sr).items():
            print(f"   {name}: " + " | ".join(f"lag {l:+.2f} s: {lev:6.1f} dB re source ({s:.1f}x the spread)"
                                           for l, lev, s in v["peaks"]))
        print("3. low band: residual after the linear prediction (dBFS; re signal in loud blocks)")
        print("   ch  octave  signal(loud)  residual(loud)  re signal   signal(quiet)  residual(quiet)  blank hiss")
        for name, rows in low_band(src, tape, sr, hiss_psd(t, sr)).items():
            for r in rows:
                print(f"   {name}  {r['fc']:6g}    {r['sig_loud']:7.1f}       {r['res_loud']:7.1f}       {r['rel_loud']:6.1f}"
                      f"        {r['sig_quiet']:7.1f}        {r['res_quiet']:7.1f}       {r['hiss']:7.1f}")


if __name__ == "__main__":
    main()
