"""Does the deck round off peaks? (run align.py first)

    python peaks.py B3 B3emu

Gain of the tape output on its linear prediction, conditional on how high the predicted amplitude is
(percentile classes of the instantaneous amplitude, and of the envelope in four bands). Distortion fits
average over all samples, where peaks are rare; this looks at the peaks alone. A deck that compresses
transients shows the gain falling toward the highest classes. The emulation is the reference.

A second table gives the power gain of each treble band by how loud that band is in the source, in
11.6 ms blocks (insensitive to jitter, unlike the first): treble saturation shows as a gain that falls
with the band's level; with two ids the last row is their difference.
"""
import sys
import numpy as np
from scipy import signal
from investigate import load, band
from measure import cross_spectra, apply_H
from common import db
PCT = [50, 75, 90, 97, 99, 99.7, 99.9, 99.97]
def run(tid):
    sr, src, tape, z, trim = load(tid)
    out = {}
    for c, name in ((0, "L"), (1, "R")):
        x, y = src[:, c], tape[:, c]
        f, Pxx, _, Pxy = cross_spectra(x, y, sr)
        yhat = apply_H(x, f, Pxy / Pxx)
        rows = {}
        # broadband: output vs predicted output, conditional on |predicted| percentile class (signed regression slope per class)
        edges = np.percentile(np.abs(yhat), PCT + [100])
        cells = []
        for a, b in zip(edges[:-1], edges[1:]):
            m = (np.abs(yhat) >= a) & (np.abs(yhat) < b)
            cells.append(20 * np.log10(np.sum(y[m] * yhat[m]) / np.sum(yhat[m] ** 2)))   # gain of y on yhat within the class
        rows["broadband"] = cells
        for lo, hi, fc in ((177, 707, 350), (707, 2828, 1400), (2828, 5657, 4000), (5657, 11314, 8000)):
            Yh, Y = signal.hilbert(band(yhat, sr, lo, hi)), signal.hilbert(band(y, sr, lo, hi))
            e = np.abs(Yh)
            edges = np.percentile(e, PCT + [100])
            cells = []
            for a, b in zip(edges[:-1], edges[1:]):
                m = (e >= a) & (e < b)
                cells.append(20 * np.log10(np.real(np.sum(Y[m] * np.conj(Yh[m]))) / np.sum(e[m] ** 2)))  # coherent gain in the class
            rows[fc] = cells
        out[name] = rows
    return out
res = {tid: run(tid) for tid in sys.argv[1:]}
print("gain of the output on its linear prediction, by how high the predicted amplitude is (percentile class of instantaneous amplitude / band envelope) [dB]")
print("   a deck that rounds off peaks shows the gain falling toward the right; L and R averaged")
print("   band        track    " + " ".join(f">{p:g}%".rjust(8) for p in PCT))
for key in ("broadband", 350, 1400, 4000, 8000):
    for tid in sys.argv[1:]:
        v = np.mean([res[tid][ch][key] for ch in "LR"], axis=0)
        print(f"   {str(key):10}  {tid:6}   " + " ".join(f"{x:+8.2f}" for x in v))


# ---------------------------------------------------------------- treble band gain by band level
from signature import hiss_psd
from tracks import track
BANDS = [(1414, 2828), (2828, 5657), (5657, 8000), (8000, 11314), (11314, 16000)]
CLASSES = [(0, 50), (50, 75), (75, 90), (90, 97), (97, 99.5), (99.5, 100)]
W = 512
def run_power(tid):
    t = track(tid)
    sr, src, tape, z, trim = load(t.id)
    fh, Ph = hiss_psd(t, sr)
    out = {}
    for lo, hi in BANDS:
        rows = []
        for c in (0, 1):
            m = (fh >= lo) & (fh < hi)
            noise = np.trapezoid(Ph[m, c], fh[m])
            xb, yb = band(src[:, c], sr, lo, hi), band(tape[:, c], sr, lo, hi)
            n = len(xb) // W
            px = (xb[: n * W] ** 2).reshape(n, W).mean(1); py = (yb[: n * W] ** 2).reshape(n, W).mean(1)
            edges = np.percentile(px, [a for a, _ in CLASSES] + [100])
            g = []
            for a, b in zip(edges[:-1], edges[1:]):
                k = (px >= a) & (px <= b)
                g.append(((py[k].sum() - noise * k.sum()) / px[k].sum(), db(px[k].mean())))
            rows.append(g)
        gain = np.mean([[v[0] for v in r] for r in rows], axis=0)
        lvl = np.mean([[v[1] for v in r] for r in rows], axis=0)
        out[(lo, hi)] = (10 * np.log10(gain / gain[2]), lvl)   # re the 75-90% class
    return out
ids = sys.argv[1:]
res = {tid: run_power(tid) for tid in ids}
print("power gain of each treble band by how loud that band is in the source (11.6 ms blocks), dB re the 75-90% class; L,R averaged")
print("   band            track    " + " ".join(f"{a:g}-{b:g}%".rjust(10) for a, b in CLASSES) + "    source level of the top class")
for bnd in BANDS:
    for tid in ids:
        g, lvl = res[tid][bnd]
        print(f"   {bnd[0]:5d}-{bnd[1]:5d}  {tid:6}   " + " ".join(f"{v:+10.2f}" for v in g) + f"    {lvl[-1]:6.1f} dBFS")
    if len(ids) == 2:
        d = res[ids[0]][bnd][0] - res[ids[1]][bnd][0]
        print(f"   {'':11}  tape-emu " + " ".join(f"{v:+10.2f}" for v in d))
