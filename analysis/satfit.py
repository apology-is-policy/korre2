"""Fit the treble saturation stage from music (run align.py on the tape and on its emulation first).

    python satfit.py B3 [--apply ../profiles/wmd6c_xlii_sideB.json] [--check A5]

The deck records a treble-boosted signal (record pre-emphasis), so the tape saturates on loud treble
first: the treble dips a little in loud, bright moments. Measured as the power gain of each treble band
by that band's own level in 11.6 ms blocks, tape minus emulation (the emulation has no such stage, so
its curve is the estimator's own baseline).
Model, between the flat cubic and the static response:
    u = pre-emphasis(x)      first-order high shelf, corner from a time constant, gain G dB
    u = u - c * u^3
    y = de-emphasis(u)       the exact inverse shelf, so quiet signals pass unchanged
The effect is linear in c while it is small, so for each G one evaluation with a reference c gives the
least-squares c; G and the corner are picked from a small grid. The stage is evaluated on the source
alone (seconds per try) rather than through a full render.
--apply writes the stage into a profile (saturation.hf); --check predicts the curve for another song with
the fitted stage and compares it with that song's tape (a different recording level tests the level law).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import signal

from common import db
from emulator import hf_stage
from investigate import band, load
from signature import hiss_psd
from tracks import track

BANDS = [(1414, 2828), (2828, 5657), (5657, 8000), (8000, 11314), (11314, 16000)]
CLASSES = [(0, 50), (50, 75), (75, 90), (90, 97), (97, 99.5), (99.5, 100)]
REF = 2  # class the gains are referred to (75-90%)
W = 512
GRID_G = (6.0, 9.0, 12.0, 15.0, 18.0)
GRID_TAU = (70e-6, 120e-6)  # pre-emphasis corner: 2274 Hz, 1326 Hz
C_REF = 0.05


def gain_by_level(x, y, sr, noise=None):
    """Power gain of y on x per treble band and level class of x (dB re class REF), channels averaged."""
    out = []
    for lo, hi in BANDS:
        rows = []
        for c in range(x.shape[1]):
            xb, yb = band(x[:, c], sr, lo, hi), band(y[:, c], sr, lo, hi)
            n = len(xb) // W
            px = (xb[: n * W] ** 2).reshape(n, W).mean(1)
            py = (yb[: n * W] ** 2).reshape(n, W).mean(1)
            nz = 0.0 if noise is None else noise[(lo, hi)][c]
            edges = np.percentile(px, [a for a, _ in CLASSES] + [100])
            rows.append([(py[k].sum() - nz * k.sum()) / px[k].sum()
                         for k in ((px >= a) & (px <= b) for a, b in zip(edges[:-1], edges[1:]))])
        g = np.mean(rows, axis=0)
        out.append(10 * np.log10(g / g[REF]))
    return np.array(out)  # (band, class)


def measured(tid):
    t = track(tid)
    sr, src, tape, z, trim = load(t.id)
    fh, Ph = hiss_psd(t, sr)
    noise = {(lo, hi): [np.trapezoid(Ph[(fh >= lo) & (fh < hi), c], fh[(fh >= lo) & (fh < hi)]) for c in (0, 1)]
             for lo, hi in BANDS}
    return gain_by_level(src, tape, sr, noise), sr, src


def table(title, M):
    print(f"  {title}")
    for (lo, hi), row in zip(BANDS, M):
        print(f"    {lo:5d}-{hi:5d} Hz  " + " ".join(f"{v:+7.2f}" for v in row))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("track")
    ap.add_argument("--apply", help="profile to write the fitted stage into")
    ap.add_argument("--check", help="another song (with its emulation aligned) to test the fitted stage on")
    ap.add_argument("--gains", help="profile whose record gains apply to the fitted song (default: --apply)")
    ap.add_argument("--check-gains", help="profile whose record gains apply to the --check song (default: as --gains)")
    args = ap.parse_args()
    prof_path = Path(args.gains or args.apply) if (args.gains or args.apply) else None
    prof = json.loads(prof_path.read_text()) if prof_path else None

    def target(tid):
        T, sr, src = measured(tid)
        E, _, _ = measured(f"{tid}emu")
        return T - E, sr, src

    def record_gain(tid):
        nonlocal prof
        if prof is None:
            return np.array([1.0, 1.0])
        song = next((s for s in prof["songs"] if s["id"] == tid), None)
        g = song["gain_db"] if song else prof["gain_db"]
        return np.array([10 ** (g[c] / 20) for c in "LR"])

    D, sr, src = target(args.track)
    print(f"{args.track}: treble band gain by band level, classes " + " ".join(f"{a:g}-{b:g}%" for a, b in CLASSES))
    table("tape minus emulation (what the stage should add), dB", D)
    x = src * record_gain(args.track)
    best = None
    wts = np.ones_like(D)
    wts[:, :REF] = 0.0  # the quiet classes are noise-dominated (and saturation acts on the loud ones)
    for tau in GRID_TAU:
        for G in GRID_G:
            M0 = gain_by_level(x, hf_stage(x, sr, tau, G, C_REF), sr)
            k = float(np.sum(wts * M0 * D) / np.sum(wts * M0 * M0))
            err = float(np.sqrt(np.mean(wts * (k * M0 - D) ** 2)))
            print(f"  corner {1 / (2 * np.pi * tau):5.0f} Hz, shelf +{G:4.1f} dB: c = {k * C_REF:8.4f}, rms error {err:.3f} dB")
            if k > 0 and (best is None or err < best[0]):
                best = (err, tau, G, k * C_REF)
    err, tau, G, c = best
    M = gain_by_level(x, hf_stage(x, sr, tau, G, c), sr)
    print(f"best: corner {1 / (2 * np.pi * tau):.0f} Hz, shelf +{G:.1f} dB, c = {c:.4f} (rms error {err:.3f} dB)")
    table("the fitted stage alone, dB", M)
    stage = dict(tau_s=tau, shelf_db=G, c=c, fitted_on=args.track, rms_error_db=err)
    if args.check:
        D2, sr2, src2 = target(args.check)
        if args.check_gains:
            prof = json.loads(Path(args.check_gains).read_text())
        x2 = src2 * record_gain(args.check)
        M2 = gain_by_level(x2, hf_stage(x2, sr2, tau, G, c), sr2)
        table(f"{args.check}: tape minus emulation, dB", D2)
        table(f"{args.check}: predicted by the stage fitted on {args.track}, dB", M2)
        print(f"  rms difference over the loud classes {np.sqrt(np.mean((M2 - D2)[:, REF:] ** 2)):.3f} dB")
    if args.apply:
        p = json.loads(Path(args.apply).read_text())
        p["saturation"]["hf"] = stage
        Path(args.apply).write_text(json.dumps(p, separators=(",", ":")))
        print(f"wrote saturation.hf into {args.apply}")


if __name__ == "__main__":
    main()
