"""Generate the test-tape signal and its manifest (see TESTTAPE.md for the session protocol).

    python testsignal.py           # writes out/testtape_v2.wav (24-bit/96 kHz) + out/testtape_v2.json
    python testsignal.py --check   # re-reads the WAV and verifies every section's level

All levels are digital: sine levels are PEAK dBFS, noise levels are RMS dBFS. The record
level on the Walkman is set with music beforehand (see TESTTAPE.md), so these digital
levels relate directly to how loud your music hits the tape.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

SR = 96000
NAME = "testtape_v2"
OUT = Path(__file__).resolve().parent / "out"
MAX_PEAK_DBFS = -0.5


def amp(dbfs: float) -> float:
    return 10 ** (dbfs / 20)


def ramp_env(n: int, ramp_s: float) -> np.ndarray:
    """Raised-cosine fade in and out over ramp_s seconds."""
    env = np.ones(n)
    r = min(int(ramp_s * SR), n // 2)
    if r:
        up = 0.5 - 0.5 * np.cos(np.pi * np.arange(r) / r)
        env[:r] = up
        env[n - r:] = up[::-1]
    return env


def t_axis(sec: float) -> np.ndarray:
    return np.arange(int(round(sec * SR))) / SR


def stereo(mono: np.ndarray, ch: str = "both") -> np.ndarray:
    out = np.zeros((len(mono), 2))
    if ch in ("both", "L"):
        out[:, 0] = mono
    if ch in ("both", "R"):
        out[:, 1] = mono
    return out


def tone(freq, sec, dbfs, ramp=0.01):
    t = t_axis(sec)
    return amp(dbfs) * np.sin(2 * np.pi * freq * t) * ramp_env(len(t), ramp)


def log_sweep(f1, f2, sec, dbfs, fade_in=0.05, fade_out=0.01):
    """Exponential sine sweep (Farina). Deconvolve with the matching inverse filter."""
    t = t_axis(sec)
    L = sec / np.log(f2 / f1)
    x = np.sin(2 * np.pi * f1 * L * (np.exp(t / L) - 1))
    env = np.ones(len(t))
    a, b = int(fade_in * SR), int(fade_out * SR)
    env[:a] = 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)
    env[len(t) - b:] = 0.5 + 0.5 * np.cos(np.pi * np.arange(b) / b)
    return amp(dbfs) * x * env


def pink(sec, rms_dbfs, rng, lo=20.0, hi=20000.0):
    """Band-limited pink noise with the requested RMS."""
    n = int(round(sec * SR))
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    shape = np.zeros_like(f)
    band = (f >= lo) & (f <= hi)
    shape[band] = 1 / np.sqrt(f[band])
    x = np.fft.irfft(spec * shape, n)
    x *= amp(rms_dbfs) / np.sqrt(np.mean(x ** 2))
    return x * ramp_env(n, 0.05)


class Builder:
    def __init__(self):
        self.chunks: list[np.ndarray] = []
        self.pos = 0
        self.sections: list[dict] = []

    def add(self, x: np.ndarray, name: str | None = None, **params):
        start = self.pos
        self.chunks.append(x)
        self.pos += len(x)
        if name:
            self.sections.append(dict(name=name, start_s=start / SR, end_s=self.pos / SR, **params))
        return start / SR

    def gap(self, sec: float):
        self.add(np.zeros((int(round(sec * SR)), 2)))

    def signal(self) -> np.ndarray:
        return np.concatenate(self.chunks)


def marker(b: Builder, name: str):
    """Three short chirps with uneven gaps: easy to find, unambiguous to align."""
    chirp = log_sweep(300, 6000, 0.4, -12, fade_in=0.005, fade_out=0.005)
    parts = [chirp, np.zeros(int(0.3 * SR)), chirp, np.zeros(int(0.6 * SR)), chirp]
    b.add(stereo(np.concatenate(parts)), name, kind="marker", chirp=[300, 6000, 0.4], level_dbfs=-12,
          pattern_s=[0.4, 0.3, 0.4, 0.6, 0.4])


def build() -> Builder:
    rng = np.random.default_rng(20261115)
    b = Builder()
    b.gap(5)
    marker(b, "marker_start")
    b.gap(2)
    b.add(stereo(tone(1000, 20, -12, ramp=0.05)), "cal_1k", kind="tone", freq=1000, level_dbfs=-12,
          note="read the Walkman's record meter here")
    b.gap(1)
    b.add(np.zeros((20 * SR, 2)), "tape_noise", kind="silence", note="recorded silence: hiss with bias on")
    b.add(stereo(tone(3150, 60, -12, ramp=0.05)), "wow_flutter_3150", kind="tone", freq=3150, level_dbfs=-12)
    b.gap(1)
    # Head-to-tape contact flicker grows with frequency: a steady treble tone shows it directly
    # (amplitude sidebands), along with fast timing jitter (phase sidebands). Moderate level
    # so the tape's treble headroom is not the thing being measured.
    b.add(stereo(tone(10000, 30, -20, ramp=0.05)), "treble_flicker_10k", kind="tone", freq=10000, level_dbfs=-20)
    b.gap(2)

    sweep = dict(f1=20, f2=22000, dur=8.0, fade_in=0.05, fade_out=0.01)
    for lvl in (-36, -24, -18, -12, -6, -3, -1):
        b.add(stereo(log_sweep(sweep["f1"], sweep["f2"], sweep["dur"], lvl)), f"sweep_{lvl}",
              kind="sweep", level_dbfs=lvl, channels="both", **sweep)
        b.gap(2)
    for ch in ("L", "R"):
        b.add(stereo(log_sweep(sweep["f1"], sweep["f2"], sweep["dur"], -12), ch), f"sweep_-12_{ch}only",
              kind="sweep", level_dbfs=-12, channels=ch, **sweep)
        b.gap(2)

    levels = list(range(-30, -1, 2)) + [-1]
    for freq in (100, 315, 1000, 3150, 6300, 10000, 12500):
        steps = []
        for lvl in levels:
            s = b.add(stereo(tone(freq, 0.5, lvl)))
            steps.append(dict(level_dbfs=lvl, start_s=s, end_s=s + 0.5))
            b.gap(0.1)
        b.sections.append(dict(name=f"steps_{freq}", kind="stepped_tone", freq=freq, start_s=steps[0]["start_s"],
                               end_s=steps[-1]["end_s"], step_s=0.5, ramp_s=0.01, steps=steps))
        b.gap(1)

    # Bass bursts under a quiet treble probe: does a loud bass note (heavy current draw,
    # battery sag) modulate the level or timing of everything else?
    dur, probe_db = 36.0, -30
    probe = tone(3150, dur, probe_db, ramp=0.05)
    bass = np.zeros_like(probe)
    bursts = []
    for i, lvl in enumerate((-12, -12, -6, -6, -3, -3, -1.5, -1.5)):
        t0 = 2.0 + 4.0 * i
        a = int(t0 * SR)
        bass[a:a + 2 * SR] = tone(60, 2.0, lvl, ramp=0.02)
        bursts.append(dict(level_dbfs=lvl, start_s=t0, end_s=t0 + 2.0))
    start = b.add(stereo(probe + bass))
    b.sections.append(dict(name="bass_bursts", kind="bass_bursts", start_s=start, end_s=start + dur,
                           probe=dict(freq=3150, level_dbfs=probe_db), burst_freq=60,
                           bursts=[dict(x, start_s=start + x["start_s"], end_s=start + x["end_s"]) for x in bursts]))
    b.gap(2)

    for lvl in (-12, -6):  # SMPTE: 60 Hz + 7 kHz at 4:1, total peak = lvl
        t = t_axis(5)
        a = amp(lvl)
        x = (0.8 * a * np.sin(2 * np.pi * 60 * t) + 0.2 * a * np.sin(2 * np.pi * 7000 * t)) * ramp_env(len(t), 0.02)
        b.add(stereo(x), f"imd_smpte_{lvl}", kind="imd_smpte", freqs=[60, 7000], ratio="4:1", peak_dbfs=lvl)
        b.gap(0.5)
    for lvl in (-12, -6):  # twin tone 9 + 10 kHz, equal, total peak = lvl
        t = t_axis(5)
        a = amp(lvl) / 2
        x = (a * np.sin(2 * np.pi * 9000 * t) + a * np.sin(2 * np.pi * 10000 * t)) * ramp_env(len(t), 0.02)
        b.add(stereo(x), f"imd_twin_{lvl}", kind="imd_twin", freqs=[9000, 10000], peak_dbfs=lvl)
        b.gap(0.5)
    b.gap(0.5)

    # Independent pink noise per channel: full 2x2 transfer (incl. crosstalk) and
    # level-dependent treble compression on a music-like spectrum.
    for lvl in (-34, -26, -20, -16):  # -16 RMS ~ loud music; gaussian peaks reach ~ -2 dBFS
        x = np.stack([pink(15, lvl, rng), pink(15, lvl, rng)], axis=1)
        b.add(x, f"pink_{lvl}", kind="pink_noise", rms_dbfs=lvl, decorrelated=True, band=[20, 20000],
              peak_dbfs_actual=round(float(20 * np.log10(np.abs(x).max())), 2))
        b.gap(1)

    b.gap(4)
    marker(b, "marker_end")
    b.gap(5)
    return b


def write_wav(x: np.ndarray, path: Path):
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2",
         "-i", "-", "-c:a", "pcm_s24le", str(path)],
        input=x.astype(np.float32).tobytes(), check=True)
    return proc


def check(path: Path, manifest: dict):
    from common import decode
    x = decode(path).astype(np.float64)
    print(f"{path.name}: {len(x) / SR:.2f} s (manifest {manifest['duration_s']:.2f} s), "
          f"overall peak {20 * np.log10(np.abs(x).max()):.2f} dBFS")
    print("  section                 start    end   peak L/R dBFS      RMS L/R dBFS   expected")
    for s in manifest["sections"]:
        a, b = int(s["start_s"] * SR), int(s["end_s"] * SR)
        seg = x[a:b]
        pk = 20 * np.log10(np.maximum(np.abs(seg).max(axis=0), 1e-12))
        rms = 10 * np.log10(np.maximum(np.mean(seg ** 2, axis=0), 1e-24))
        exp = s.get("level_dbfs", s.get("peak_dbfs", s.get("rms_dbfs", "")))
        kind = "rms" if "rms_dbfs" in s else ("peak" if exp != "" else "")
        if s["kind"] == "stepped_tone":
            exp, kind = f"{s['steps'][0]['level_dbfs']}..{s['steps'][-1]['level_dbfs']}", "peak"
        print(f"  {s['name']:22} {s['start_s']:6.1f} {s['end_s']:6.1f}   {pk[0]:6.1f} {pk[1]:6.1f}     "
              f"{rms[0]:6.1f} {rms[1]:6.1f}     {exp} {kind}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    wav, js = OUT / f"{NAME}.wav", OUT / f"{NAME}.json"
    if args.check:
        check(wav, json.loads(js.read_text()))
        return
    b = build()
    x = b.signal()
    peak = 20 * np.log10(np.abs(x).max())
    if peak > MAX_PEAK_DBFS:
        raise SystemExit(f"peak {peak:.2f} dBFS exceeds {MAX_PEAK_DBFS} dBFS")
    write_wav(x, wav)
    manifest = dict(name=NAME, sample_rate=SR, channels=2, duration_s=len(x) / SR, peak_dbfs=peak,
                    level_convention="tones/sweeps: peak dBFS; noise: RMS dBFS", sections=b.sections)
    js.write_text(json.dumps(manifest, indent=1))
    print(f"wrote {wav} ({len(x) / SR / 60:.1f} min, peak {peak:.2f} dBFS) and {js.name}")


if __name__ == "__main__":
    main()
