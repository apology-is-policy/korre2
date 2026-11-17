"""Distortion driven by the bass alone, in the low band (run align.py first)

    python bassdist.py B3 B3emu

2nd- and 3rd-order FIR-Hammerstein fits of the source below 150 Hz (and, for comparison, the cube of the
full signal) to the residual at a 3 kHz rate, trained on even seconds and tested on odd seconds, in the
loudest-bass 30% of blocks. Per band 20-100 / 100-300 / 300-1000 Hz: share of the residual explained and
the predicted distortion relative to the signal. The emulation is the reference.
"""
import sys
import numpy as np
from scipy import signal
from investigate import load, fit_fir_multi, predict
from residual import fit_windows
from common import db
SR = 3000
def run(tid):
    sr, src, tape, z, trim = load(tid)
    q = sr // SR
    out = []
    for c, name in ((0, "L"), (1, "R")):
        x = signal.resample_poly(src[:, c], 1, q); y = signal.resample_poly(tape[:, c], 1, q)
        f, Pxx = signal.welch(x, SR, nperseg=8192); _, Pxy = signal.csd(x, y, SR, nperseg=8192)
        H = Pxy / Pxx
        n = 1 << int(np.ceil(np.log2(len(x) + 8192)))
        fine = np.fft.rfftfreq(n, 1 / SR)
        yhat = np.fft.irfft(np.fft.rfft(x, n) * (np.interp(fine, f, H.real) + 1j * np.interp(fine, f, H.imag)), n)[: len(x)]
        r = y - yhat
        dy = np.gradient(yhat) * SR
        W = 128
        *_, tau, g, loud, lvl = fit_windows(r, yhat, dy, x, W)
        m = len(tau) * W
        clean = r[:m] - np.repeat(g, W) * yhat[:m] - np.repeat(tau, W) * dy[:m]
        x, yh = x[:m], yhat[:m]
        lp = signal.butter(4, 150, "low", fs=SR, output="sos")
        ub = signal.sosfiltfilt(lp, x); ub = ub / np.std(ub)
        u = x / np.std(x)
        sec = (np.arange(m) // SR) % 2
        B = 1024; nb = m // B
        bass_lvl = db((signal.sosfiltfilt(lp, yh)[: nb * B] ** 2).reshape(nb, B).mean(1))
        loudbass = np.repeat(bass_lvl > np.percentile(bass_lvl, 70), B)
        test = (sec[: nb * B] == 1) & loudbass
        row = {}
        for label, feats in (("bass^2", [ub ** 2 - np.mean(ub ** 2)]), ("bass^3", [ub ** 3]), ("bass^2+^3", [ub ** 2 - np.mean(ub ** 2), ub ** 3]),
                             ("full^3", [u ** 3])):
            hs = fit_fir_multi([ft * (sec == 0) for ft in feats], clean * (sec == 0), 64)
            pred = predict(feats, hs)
            cells = []
            for lo, hi in ((20, 100), (100, 300), (300, 1000)):
                bp = signal.butter(4, [lo, hi], "bandpass", fs=SR, output="sos")
                cb, pb, sb = (signal.sosfiltfilt(bp, v)[: nb * B] for v in (clean, pred, yh))
                expl = 1 - np.sum((cb[test] - pb[test]) ** 2) / np.sum(cb[test] ** 2)
                cells.append((expl * 100, db(np.sum(pb[test] ** 2) / np.sum(sb[test] ** 2)), db(np.sum(cb[test] ** 2) / np.sum(sb[test] ** 2))))
            row[label] = cells
        out.append((name, row))
    return out
for tid in sys.argv[1:]:
    print(f"== {tid}: distortion fitted on even seconds, tested on odd seconds, in the loudest-bass 30% of blocks")
    print("   per band 20-100 / 100-300 / 300-1000 Hz: explained share of the residual, predicted distortion re signal [dB] (whole residual re signal)")
    for name, row in run(tid):
        for label, cells in row.items():
            print(f"   {name} {label:10}: " + " | ".join(f"{e:5.1f}%  {p:6.1f} dB  ({w:6.1f})" for e, p, w in cells))
