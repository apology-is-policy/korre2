"""Spectrograms of two files side by side, and where they differ.

    python spectro.py B3                      tape vs emulation from out/listening/B3/ -> spectrograms.png there
    python spectro.py --a x.flac --b y.flac --out cmp.png [--labels "A" "B"]

Six panels:
  row 1  whole range, 20 Hz-22 kHz on a log axis (L+R), A | B, same colour scale
  row 2  the low end, 0-300 Hz on a linear axis with 1.5 Hz resolution, A | B
  row 3  A minus B in dB, 1 s blocks and 1/6-octave bands: what both ears share (L+R) | what differs
         between the ears (L-R). Red = A has more, blue = B has more.
Also prints the A-minus-B level per octave for L+R and L-R. The files need the same length and rough
alignment (the listening sets have both); 1 s blocks make the difference panels insensitive to wow.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy import signal

from common import db, decode
from measure import OUT

SR = 48000
# one hue, light -> dark, for level; blue <-> red around a neutral grey for differences
SEQ = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b", "#06203f"]
DIV = ["#0d366b", "#256abf", "#6da7ec", "#cde2fb", "#f0efec", "#f6c9c4", "#e98a85", "#c9403f", "#8a1f22"]
INK, INK2, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"


def stft_power(x, nper, hop):
    f, t, Z = signal.stft(x, SR, nperseg=nper, noverlap=nper - hop, boundary=None, padded=False)
    return f, t, np.abs(Z) ** 2


def log_bins(f, P, fmin=20.0, fmax=22000.0, per_octave=24):
    """Average power into log-spaced bands; returns band edges and power (bands x time)."""
    n = int(np.ceil(np.log2(fmax / fmin) * per_octave))
    edges = fmin * 2 ** (np.arange(n + 1) / per_octave)
    out = np.empty((n, P.shape[1]))
    for k in range(n):
        m = (f >= edges[k]) & (f < edges[k + 1])
        if not m.any():  # narrower than one FFT bin: take the nearest bin
            m = np.zeros(len(f), bool)
            m[np.argmin(np.abs(f - np.sqrt(edges[k] * edges[k + 1])))] = True
        out[k] = P[m].mean(axis=0)
    return edges, out


def t_edges(t):
    """Cell edges for a uniform time axis given as cell centres."""
    dt = t[1] - t[0]
    return np.concatenate((t - dt / 2, [t[-1] + dt / 2]))


def block_mean(P, t, block_s=1.0):
    step = max(1, int(round(block_s / (t[1] - t[0]))))
    nb = P.shape[1] // step
    return P[:, : nb * step].reshape(P.shape[0], nb, step).mean(axis=2), t[: nb * step: step]


def octave_table(edges, Pa, Pb):
    rows = []
    for fc in (31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000):
        c = np.sqrt(edges[:-1] * edges[1:])
        m = (c >= fc / 2 ** 0.5) & (c < fc * 2 ** 0.5)
        if m.any():
            rows.append((fc, float(db(Pa[m].sum() / Pb[m].sum())),
                         float(np.median(db(Pa[m].sum(axis=0) / Pb[m].sum(axis=0))))))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("track", nargs="?")
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--out")
    ap.add_argument("--labels", nargs=2, default=None)
    args = ap.parse_args()
    if args.track:
        folder = OUT / "listening" / args.track
        pa, pb, out = folder / "tape.flac", folder / "6_full.flac", folder / "spectrograms.png"
        labels = args.labels or ["tape (real capture)", "emulation (6_full)"]
    else:
        if not (args.a and args.b and args.out):
            ap.error("give a track id, or --a, --b and --out")
        pa, pb, out = Path(args.a), Path(args.b), Path(args.out)
        labels = args.labels or [pa.stem, pb.stem]
    a, b = (decode(p, sr=SR).astype(np.float64) for p in (pa, pb))
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    mid = lambda x: (x[:, 0] + x[:, 1]) / 2
    side = lambda x: (x[:, 0] - x[:, 1]) / 2

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    seq = LinearSegmentedColormap.from_list("level", SEQ)
    div = LinearSegmentedColormap.from_list("diff", DIV)
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2,
                         "ytick.color": INK2, "text.color": INK, "axes.linewidth": 0.6, "font.family": "sans-serif"})
    fig, ax = plt.subplots(3, 2, figsize=(17, 14), dpi=130, facecolor=SURFACE, constrained_layout=True)

    # row 1: whole range, log axis
    full = []
    for x in (a, b):
        f, t, P = stft_power(mid(x), 8192, 2048)
        edges, L = log_bins(f, P)
        full.append((edges, t, L))
    vmax = np.percentile(db(full[0][2]), 99.9)
    for k, (edges, t, L) in enumerate(full):
        im1 = ax[0, k].pcolormesh(t_edges(t), edges, db(L), cmap=seq, vmin=vmax - 85, vmax=vmax, shading="flat", rasterized=True)
        ax[0, k].set_yscale("log")
        ax[0, k].set_ylim(20, 22000)
        ax[0, k].set_yticks([31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000],
                            ["31", "63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"])
        ax[0, k].minorticks_off()
        ax[0, k].set_title(f"{labels[k]}: whole range (L+R)", loc="left", fontsize=11, color=INK)
    fig.colorbar(im1, ax=ax[0, :], pad=0.01, aspect=30, label="level per band, dB")

    # row 2: the low end, linear axis, long windows
    low = []
    for x in (a, b):
        f, t, P = stft_power(mid(x), 32768, 8192)
        m = f <= 300
        low.append((f[m], t, P[m]))
    vmax2 = np.percentile(db(low[0][2]), 99.9)
    for k, (f, t, P) in enumerate(low):
        im2 = ax[1, k].pcolormesh(t, f, db(P), cmap=seq, vmin=vmax2 - 85, vmax=vmax2, shading="nearest", rasterized=True)
        ax[1, k].set_ylim(0, 300)
        ax[1, k].set_title(f"{labels[k]}: low end, 0-300 Hz (L+R)", loc="left", fontsize=11, color=INK)
    fig.colorbar(im2, ax=ax[1, :], pad=0.01, aspect=30, label="level per 1.5 Hz, dB")

    # row 3: A minus B, what the ears share and what differs between them
    print(f"{labels[0]} minus {labels[1]}, level per octave [dB]: whole-song power ratio (median over 1 s blocks)")
    for k, (name, fn) in enumerate((("L+R (what both ears share)", mid), ("L-R (what differs between the ears)", side))):
        blocks = []
        for x in (a, b):
            f, t, P = stft_power(fn(x), 8192, 2048)
            edges, L = log_bins(f, P, per_octave=6)
            Lb, tb = block_mean(L, t)
            blocks.append(Lb)
        d = db(blocks[0] / blocks[1])
        im3 = ax[2, k].pcolormesh(t_edges(tb), edges, d, cmap=div, vmin=-9, vmax=9, shading="flat", rasterized=True)
        ax[2, k].set_yscale("log")
        ax[2, k].set_ylim(20, 22000)
        ax[2, k].set_yticks([31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000],
                            ["31", "63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"])
        ax[2, k].minorticks_off()
        ax[2, k].set_title(f"{labels[0]} minus {labels[1]}: {name}", loc="left", fontsize=11, color=INK)
        print(f"  {name}")
        print("    " + "  ".join(f"{fc:g}: {tot:+.1f} ({med:+.1f})" for fc, tot, med in octave_table(edges, *blocks)))
    fig.colorbar(im3, ax=ax[2, :], pad=0.01, aspect=30, label="dB (red: first has more, blue: second has more)")

    for r in range(3):
        for k in range(2):
            ax[r, k].set_facecolor(SURFACE)
            ax[r, k].set_ylabel("Hz")
            ax[r, k].tick_params(length=3, width=0.6)
            for s in ("top", "right"):
                ax[r, k].spines[s].set_visible(False)
    for k in range(2):
        ax[2, k].set_xlabel("time, s")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
