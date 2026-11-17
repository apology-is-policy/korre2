"""Per-track peak, RMS and clipping of the tape capture.

Clipping = samples sitting at the 24-bit full-scale rail. Reports how many such
samples there are and the longest run of consecutive ones per channel.

    python levels.py
"""
from __future__ import annotations

import numpy as np

from common import db, stream
from tracks import TRACKS

RAIL = 1.0 - 2.0**-23  # anything at or beyond the last 24-bit code


def measure(t):
    peak = np.zeros(2)
    sumsq = np.zeros(2)
    frames = 0
    rail_count = np.zeros(2, dtype=int)
    longest = np.zeros(2, dtype=int)
    current = np.zeros(2, dtype=int)
    for chunk in stream(t.path, t.start, t.end):
        x = chunk.astype(np.float64)
        peak = np.maximum(peak, np.abs(x).max(axis=0))
        sumsq += (x**2).sum(axis=0)
        frames += len(x)
        at_rail = np.abs(x) >= RAIL
        rail_count += at_rail.sum(axis=0)
        for c in (0, 1):  # longest run of consecutive rail samples, across chunk borders
            col = at_rail[:, c]
            if not col.any():
                current[c] = 0
                continue
            edges = np.flatnonzero(np.diff(np.r_[0, col.astype(np.int8), 0]))
            starts, ends = edges[::2], edges[1::2]
            lengths = ends - starts
            if starts[0] == 0:
                lengths[0] += current[c]
            longest[c] = max(longest[c], lengths.max())
            current[c] = lengths[-1] if ends[-1] == len(col) else 0
    return 20 * np.log10(np.maximum(peak, 1e-12)), db(sumsq / frames), rail_count, longest


def main():
    print("track  peak L / R (dBFS)   RMS L / R (dBFS)   L-R RMS   rail samples L/R (longest run)  title")
    for t in TRACKS:
        pk, rms, rail, run = measure(t)
        flags = " [partial]" if t.partial else ""
        print(f"{t.id:5}  {pk[0]:6.2f} / {pk[1]:6.2f}    {rms[0]:6.2f} / {rms[1]:6.2f}    {rms[0] - rms[1]:+5.2f}"
              f"     {rail[0]:5d} / {rail[1]:5d} ({run[0]}/{run[1]})       {t.title or ''}{flags}")


if __name__ == "__main__":
    main()
