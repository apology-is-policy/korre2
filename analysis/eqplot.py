"""Static response of the tape and of its emulation against the source, overlaid (run align.py on both).

    python eqplot.py B3            tape B3 vs emulation B3emu -> out/listening/B3/response.png

Four rows, left and right channel side by side:
  1  magnitude re 1 kHz (power-only estimate, the tape's background noise subtracted), tape and emulation
  2  emulation minus tape on an expanded scale
  3  phase with the 1-8 kHz delay removed, tape and emulation
  4  loud passages minus quiet passages: how the response itself changes with level, tape and emulation
     (a long-term average hides this; the emulation's response does not depend on level by construction,
     so its curve shows what the estimator alone produces)
Also prints the numbers at standard frequencies.
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy import signal

from fitprofile import EQ_GRID, EQ_TOP_HZ
from investigate import load
from measure import OUT
from signature import hiss_psd, signature
from tracks import track

BLUE, ORANGE, INK, INK2, GRID, SURFACE = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#dddcd6", "#fcfcfb"
NPER = 1 << 16
PTS = [31.5, 50, 100, 200, 500, 1000, 2000, 4000, 6000, 8000, 10000, 12500, 16000]


def level_split(tid):
    """Power response re 1 kHz per channel in the loud and the quiet third of 1.4 s windows (by source level)."""
    t = track(tid)
    sr, src, tape, z, trim = load(t.id)
    fh, Ph = hiss_psd(t, sr)
    hop = NPER // 2
    starts = np.arange(0, len(src) - NPER + 1, hop)
    lvl = np.array([np.mean(src[s:s + NPER] ** 2) for s in starts])
    sets = dict(quiet=lvl <= np.quantile(lvl, 1 / 3), loud=lvl >= np.quantile(lvl, 2 / 3))
    win = np.hanning(NPER)
    f = np.fft.rfftfreq(NPER, 1 / sr)
    grid = np.array(EQ_GRID)
    out = {}
    for c, name in ((0, "L"), (1, "R")):
        Pn = np.interp(f, fh, Ph[:, c]) * (win ** 2).sum() * sr / 2  # noise PSD in |FFT|^2 units
        acc = {k: [np.zeros(len(f)), np.zeros(len(f)), 0] for k in sets}
        for i, s in enumerate(starts):
            X = np.abs(np.fft.rfft(src[s:s + NPER, c] * win)) ** 2
            Y = np.abs(np.fft.rfft(tape[s:s + NPER, c] * win)) ** 2
            for k, m in sets.items():
                if m[i]:
                    acc[k][0] += X
                    acc[k][1] += Y
                    acc[k][2] += 1
        res = {}
        for k, (Sx, Sy, n) in acc.items():
            m1 = (f >= 900) & (f <= 1100)
            ref = np.maximum(Sy[m1] - n * Pn[m1], 1e-30).sum() / Sx[m1].sum()
            eq = np.full(len(grid), np.nan)
            for j, fc in enumerate(grid):
                m = (f >= fc / 2 ** (1 / 12)) & (f < fc * 2 ** (1 / 12))
                if m.sum() >= 2 and fc <= EQ_TOP_HZ:
                    eq[j] = 10 * np.log10(max((Sy[m] - n * Pn[m]).sum(), 1e-30) / Sx[m].sum() / ref)
            res[k] = eq
        out[name] = res
    return out


def detrend_phase(ph, grid):
    m = (grid >= 1000) & (grid <= 8000)
    slope = np.polyfit(grid[m], ph[m], 1)[0]
    return np.degrees(ph - slope * grid)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("track")
    args = ap.parse_args()
    tid, eid = args.track, f"{args.track}emu"
    st, se = signature(tid), signature(eid, cache=False)
    lt, le = level_split(tid), level_split(eid)
    grid = np.array(EQ_GRID)
    show = grid <= 20000

    print(f"static response re 1 kHz [dB], {tid} tape / emulation / difference; then phase [deg] tape / emulation")
    print("   Hz    " + "  ".join(f"{p:g}".rjust(7) for p in PTS))
    for ch in "LR":
        idx = [int(np.argmin(np.abs(grid - p))) for p in PTS]
        e_t, e_e = np.array(st["eq"][ch]), np.array(se["eq"][ch])
        p_t, p_e = detrend_phase(np.array(st["phase"][ch]), grid), detrend_phase(np.array(se["phase"][ch]), grid)
        print(f"   {ch} tape   " + "  ".join(f"{e_t[i]:+7.2f}" for i in idx))
        print(f"   {ch} emu    " + "  ".join(f"{e_e[i]:+7.2f}" for i in idx))
        print(f"   {ch} diff   " + "  ".join(f"{e_e[i] - e_t[i]:+7.2f}" for i in idx))
        print(f"   {ch} phase  " + "  ".join(f"{p_t[i]:+7.0f}" for i in idx))
        print(f"   {ch} ph emu " + "  ".join(f"{p_e[i]:+7.0f}" for i in idx))
        d_t, d_e = lt[ch]["loud"] - lt[ch]["quiet"], le[ch]["loud"] - le[ch]["quiet"]
        print(f"   {ch} loud-quiet tape " + "  ".join(f"{d_t[i]:+7.2f}" for i in idx))
        print(f"   {ch} loud-quiet emu  " + "  ".join(f"{d_e[i]:+7.2f}" for i in idx))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2,
                         "ytick.color": INK2, "text.color": INK, "axes.linewidth": 0.6, "font.family": "sans-serif"})
    fig, ax = plt.subplots(4, 2, figsize=(15, 13.5), dpi=130, facecolor=SURFACE, constrained_layout=True, sharex=True)
    rows = ("magnitude re 1 kHz, dB", "emulation minus tape, dB", "phase (1-8 kHz delay removed), degrees",
            "loud passages minus quiet passages, dB")
    for k, ch in enumerate("LR"):
        name = "left" if ch == "L" else "right"
        e_t, e_e = np.array(st["eq"][ch]), np.array(se["eq"][ch])
        p_t, p_e = detrend_phase(np.array(st["phase"][ch]), grid), detrend_phase(np.array(se["phase"][ch]), grid)
        a = ax[0, k]
        a.plot(grid[show], e_t[show], color=BLUE, lw=2, label="tape")
        a.plot(grid[show], e_e[show], color=ORANGE, lw=2, ls=(0, (4, 2)), label="emulation")
        a.set_ylim(-9, 3)
        a.set_title(f"{name} channel: response against the source", loc="left", fontsize=11)
        a = ax[1, k]
        a.plot(grid[show], (e_e - e_t)[show], color=INK2, lw=2)
        a.set_ylim(-1.5, 1.5)
        a.set_title(f"{name}: emulation minus tape (expanded scale)", loc="left", fontsize=11)
        a = ax[2, k]
        a.plot(grid[show], p_t[show], color=BLUE, lw=2, label="tape")
        a.plot(grid[show], p_e[show], color=ORANGE, lw=2, ls=(0, (4, 2)), label="emulation")
        a.set_ylim(-60, 300)
        a.set_title(f"{name}: phase", loc="left", fontsize=11)
        a = ax[3, k]
        lv = (grid >= 45) & (grid <= 14000)  # outside this the quiet passages hold no music to measure with
        a.plot(grid[lv], (lt[ch]["loud"] - lt[ch]["quiet"])[lv], color=BLUE, lw=2, label="tape")
        a.plot(grid[lv], (le[ch]["loud"] - le[ch]["quiet"])[lv], color=ORANGE, lw=2, ls=(0, (4, 2)), label="emulation")
        a.set_ylim(-1.5, 1.5)
        a.set_title(f"{name}: does the response change with level? (45 Hz-14 kHz)", loc="left", fontsize=11)
        a.set_xlabel("Hz")
    for r in range(4):
        for k in range(2):
            a = ax[r, k]
            a.set_xscale("log")
            a.set_xlim(20, 20000)
            a.set_xticks([31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000],
                         ["31", "63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"])
            a.minorticks_off()
            a.grid(True, color=GRID, lw=0.6)
            a.axhline(0, color=INK2, lw=0.6)
            a.set_facecolor(SURFACE)
            for s in ("top", "right"):
                a.spines[s].set_visible(False)
            if k == 0:
                a.set_ylabel(rows[r])
            if r != 1:
                a.legend(loc="lower left", frameon=False)
    out = OUT / "listening" / tid / "response.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
