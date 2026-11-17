"""Cut the metal tape's long Tidal capture into one source file per song.

    python splitsource.py            -> data/sources/MA1.flac ... MB7.flac (24-bit, 48 kHz)

The capture (tracks.METAL_SOURCE) is 44.1 kHz material recorded at 96 kHz, so 48 kHz loses nothing and
keeps the analysis at the rate used for the chrome tape. Each file gets up to 0.3 s of the neighbouring
silence on either side; songs that run into each other are cut at the joint.
"""
from __future__ import annotations

import subprocess

from common import DATA, data_file
from tracks import METAL_SOURCE, METAL_SOURCE_SEGMENTS


def main():
    src = data_file(METAL_SOURCE)
    ids = list(METAL_SOURCE_SEGMENTS)
    for k, tid in enumerate(ids):
        a, b = METAL_SOURCE_SEGMENTS[tid]
        before = a - METAL_SOURCE_SEGMENTS[ids[k - 1]][1] if k else 1.0
        after = METAL_SOURCE_SEGMENTS[ids[k + 1]][0] - b if k + 1 < len(ids) else 1.0
        a, b = a - min(0.3, max(before, 0) / 2), b + min(0.3, max(after, 0) / 2)
        out = DATA / "sources" / f"{tid}.flac"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}",
                        "-i", str(src), "-af", "aresample=48000:resampler=soxr:precision=28",
                        "-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24", str(out)], check=True)
        print(f"{tid}: {a:8.2f} - {b:8.2f} s -> {out.name}")


if __name__ == "__main__":
    main()
