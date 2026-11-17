"""The "You Don't Get to See the Tears" mixtape capture (Dec 2023, Maxell XLII 90, WM-D6C).

Song boundaries were found from level gaps in the surviving part of each side; the
damaged copies on the Mac end at A 28:38 / B 27:08 (see FINDINGS.md). Titles come
from the tape label; None = not looked up yet.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from common import data_file

# Renders registered by render.py so the analysis scripts can treat them like a capture.
VIRTUAL = Path(__file__).resolve().parent / "out" / "virtual_tracks.json"

SIDE_FILES = {"A": "side_a.flac", "B": "side_b.flac",
              "MA": "metal-tape.flac", "MB": "metal-tape.flac"}
CAPTURE_SR = 192000


@dataclass(frozen=True)
class Track:
    id: str
    side: str
    start: float  # seconds into the side
    end: float
    title: str | None = None
    clipped: bool = False  # the capture hits full scale somewhere in the track
    partial: bool = False  # cut off by the file damage
    path_override: str | None = None  # virtual tracks: a rendered file instead of the capture
    source_override: str | None = None

    @property
    def path(self):
        return Path(self.path_override) if self.path_override else data_file(SIDE_FILES[self.side])

    @property
    def source_path(self):
        """The digital source of this song: data/sources/<id>.<flac|mp3|...> (see README)."""
        if self.source_override:
            return Path(self.source_override)
        for ext in ("flac", "wav", "mp3", "m4a"):
            try:
                return data_file(f"sources/{self.id}.{ext}")
            except FileNotFoundError:
                continue
        raise FileNotFoundError(f"no source for {self.id} in data/sources/ - see analysis/README.md")


TRACKS = [
    Track("A1", "A", 10.0, 204.5, clipped=True),
    Track("A2", "A", 209.0, 421.5, "H.I.M. - Join Me in Death"),
    Track("A3", "A", 427.5, 709.5, "Goo Goo Dolls - Iris"),
    Track("A4", "A", 717.0, 975.5, "No Doubt - Don't Speak"),
    Track("A5", "A", 979.5, 1203.0, "Blink-182 - I Miss You"),
    Track("A6", "A", 1209.0, 1540.5, "Angel Olsen - Forever Young"),
    Track("A7", "A", 1546.5, 1718.0, clipped=True, partial=True),
    Track("B1", "B", 10.5, 232.0),
    Track("B2", "B", 235.0, 460.0),
    Track("B3", "B", 462.0, 676.0, "Lady Gaga & Bradley Cooper - Shallow"),
    Track("B4", "B", 678.0, 903.0),
    Track("B5", "B", 909.5, 1157.0),
    Track("B6", "B", 1160.5, 1421.5),
    Track("B7", "B", 1423.5, 1628.0, partial=True),
]

# The metal tape: Sony Metal XR 60 (Type IV, 70 us), recorded hotter than the chrome. Captured 2026-11-17
# as ONE file holding both sides, from the Walkman's headphone jack through a Y splitter with the
# DT 770 as load (Linux line in, 24/96), heads and roller freshly cleaned, Varta alkalines.
# Track times are seconds into that file, found by correlating each song with the capture
# (out/metal_locate.json). The capture clips at full scale in MB1 (33 short moments) and MB2 (3).
METAL_TRACKS = [
    Track("MA1", "MA", 18.33, 214.03, "Kelly Clarkson - Behind These Hazel Eyes"),
    Track("MA2", "MA", 217.23, 436.78, "Kelly Clarkson - Because of You"),
    Track("MA3", "MA", 436.86, 654.61, "H.I.M. - Join Me in Death"),
    Track("MA4", "MA", 655.50, 923.80, "H.I.M. - The Funeral of Hearts"),
    Track("MA5", "MA", 923.91, 1213.61, "Goo Goo Dolls - Iris"),
    Track("MA6", "MA", 1214.14, 1436.34, "Avril Lavigne - Breakaway"),
    Track("MA7", "MA", 1438.19, 1660.79, "Avril Lavigne - I'm with You"),
    Track("MB1", "MB", 1704.96, 1915.32, "Lady Gaga - Always Remember Us This Way", clipped=True),
    Track("MB2", "MB", 1915.25, 2130.99, "Lady Gaga & Bradley Cooper - Shallow", clipped=True),
    Track("MB3", "MB", 2134.43, 2361.23, "Blink-182 - I Miss You"),
    Track("MB4", "MB", 2363.60, 2616.50, "Dido - Here with Me"),
    Track("MB5", "MB", 2618.35, 2825.65, "The Calling - Wherever You Will Go"),
    Track("MB6", "MB", 2826.90, 3037.40, "Avril Lavigne - Mobile"),
    Track("MB7", "MB", 3038.76, 3370.56, "Angel Olsen - Forever Young"),
]
TRACKS += METAL_TRACKS

# The metal tape's digital sources: one long Tidal capture of the playlist (data/sources/metal_source.flac,
# 44.1 kHz material at 96 kHz); seconds into it per song. splitsource.py cuts it into data/sources/<id>.flac.
METAL_SOURCE = "sources/metal_source.flac"
METAL_SOURCE_SEGMENTS = {
    "MA1": (7.00, 202.70),
    "MA2": (205.90, 425.45),
    "MA3": (425.45, 643.20),
    "MA4": (644.00, 912.30),
    "MA5": (912.30, 1202.00),
    "MA6": (1202.50, 1424.70),
    "MA7": (1426.50, 1649.10),
    "MB1": (1666.10, 1876.47),
    "MB2": (1876.47, 2092.20),
    "MB3": (2092.50, 2319.30),
    "MB4": (2321.40, 2574.30),
    "MB5": (2576.20, 2783.50),
    "MB6": (2784.80, 2995.30),
    "MB7": (2996.60, 3328.40),
}
# the same song on the chrome tape (its id there)
METAL_SAME_AS = {"MA3": "A2", "MA5": "A3", "MB2": "B3", "MB3": "A5", "MB7": "A6"}

# Recorded silence that is not a gap between two songs: (start, end) seconds in the side's file.
EXTRA_SILENCE = {"MB": [(3370.6, 3373.0)]}  # after the last song, before the transport stops
# Sides whose recorded silence is pooled for the noise estimate: the metal tape's gaps are short and few,
# and both sides were recorded in one session on the same head channels.
NOISE_POOL = {"MA": ("MA", "MB"), "MB": ("MA", "MB")}

# Stretches with no music. The first ~2.5 s of each side is clear leader passing
# the head (no tape hiss); then comes blank tape before the first song.
NOISE_SEGMENTS = [
    ("B leader", "B", 0.2, 2.3),
    ("B blank tape", "B", 3.6, 10.0),
    ("A leader", "A", 0.2, 2.3),
    ("A blank tape", "A", 3.2, 9.8),
]


def register_virtual(track_id: str, base_id: str, path, duration_s: float, title: str):
    """Make a rendered file analysable under its own id (e.g. B3emu), with the base song's source."""
    reg = json.loads(VIRTUAL.read_text()) if VIRTUAL.exists() else {}
    base = track(base_id)
    reg[track_id] = dict(base=base.id, path=str(path), duration_s=duration_s, title=title,
                         source=str(base.source_path))
    VIRTUAL.parent.mkdir(exist_ok=True)
    VIRTUAL.write_text(json.dumps(reg, indent=1))


def track(track_id: str) -> Track:
    for t in TRACKS:
        if t.id == track_id.upper():
            return t
    reg = json.loads(VIRTUAL.read_text()) if VIRTUAL.exists() else {}
    if track_id in reg:
        v = reg[track_id]
        base = next(t for t in TRACKS if t.id == v["base"])
        return replace(base, id=track_id, start=0.0, end=v["duration_s"], title=v["title"],
                       path_override=v["path"], source_override=v["source"], clipped=False, partial=False)
    raise KeyError(f"unknown track {track_id!r}; known: {', '.join(t.id for t in TRACKS)}")


def recorded_gaps(side: str, min_s: float = 2.3) -> list[tuple[float, float]]:
    """Silent stretches between consecutive songs on a side (seconds in the capture), at least min_s
    long. The deck was recording there with silence going in, so they hold the noise a recorded tape
    really has; the blank leader before the first song (NOISE_SEGMENTS) is 3-5 dB quieter in the mids
    and presence region (FINDINGS, 2026-11-16 v0.3)."""
    tr = [t for t in TRACKS if t.side == side]
    gaps = [(a.end, b.start) for a, b in zip(tr[:-1], tr[1:]) if b.start - a.end >= min_s]
    return gaps + [g for g in EXTRA_SILENCE.get(side, []) if g[1] - g[0] >= min_s]


def clean_tracks() -> list[Track]:
    """Tracks without capture clipping (includes the partial B7)."""
    return [t for t in TRACKS if not t.clipped]
