"""Sanity-check a candidate source file before using it as the model input.

Flags signs that a file is not a plain digital master - e.g. a vinyl needle drop
(strong subsonic warp/rumble, bass folded toward mono, no digital silence).

    python sourcecheck.py <file>
"""
from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
from scipy import signal

from common import bandpow, db, decode


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:format_tags:stream=sample_rate,channels,bits_per_raw_sample",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main(path):
    info = probe(path)
    st, fmt = info["streams"][0], info["format"]
    sr = int(st["sample_rate"])
    print(f"{path}\n  {sr} Hz, {st.get('bits_per_raw_sample', '?')}-bit, {st['channels']} ch, "
          f"{float(fmt['duration']):.2f} s")
    tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
    for key in ("title", "artist", "album", "date"):
        if key in tags:
            print(f"  {key}: {tags[key]}")
    gear_words = ("turntable", "cartridge", "phono", "tonearm", "needle", "vinyl", "lp ")
    blob = " ".join(tags.values()).lower()
    if any(w in blob for w in gear_words):
        print("  ! tags mention playback gear (turntable/cartridge/phono...) - likely a needle drop")

    x = decode(path).astype(np.float64)
    f, P = signal.welch(x, sr, nperseg=1 << 18, axis=0)
    Pm = P.mean(axis=1)
    music = bandpow(f, Pm, 20, 20000)
    head = x[: int(0.2 * sr)]
    print(f"  first 0.2 s: {db(np.mean(head ** 2)):.1f} dBFS, exact digital zeros {np.mean(head == 0) * 100:.0f}%")
    # Record warp shows up at the rotation rate (0.55 Hz at 33 1/3 rpm) and its first
    # harmonics; mixes themselves have essentially nothing there. Content at 5-20 Hz is
    # NOT diagnostic: live recordings and big low ends put real energy there.
    rel = {band: db(bandpow(f, Pm, *band)) - db(music) for band in [(0.3, 2), (2, 5), (5, 20)]}
    print("  sub-audio vs music: " + "  ".join(f"{a:g}-{b:g} Hz {v:+.1f} dB" for (a, b), v in rel.items()))
    if rel[(0.3, 2)] > -40:
        print("  ! strong energy at record-warp frequencies - possibly a needle drop")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
