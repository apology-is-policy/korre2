"""Render audio through the prototype emulator.

    python render.py B3 --profile ../profiles/wmd6c_xlii_sideB.json
        listening set for a song that has a tape capture -> out/listening/B3/
    python render.py --source in.flac --profile ../profiles/wmd6c_xlii_sideA.json --out out.flac
        any file through a profile

The listening set: the source and an ingredient ladder (each step adds one fault, with the
same random wobble/flicker/hiss throughout), the real tape capture, and a blind pair. All
files are level-matched to the tape (100 Hz-8 kHz RMS) and polarity-matched to it.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
from pathlib import Path

import numpy as np
from scipy import signal

from align import PAD
from common import decode
from emulator import Emulator
from measure import OUT
from tracks import register_virtual, track

LADDER = [
    ("1_source", None),
    ("2_linear", {"eq"}),
    ("3_plus_transport_flutter", {"eq", "transport", "differential"}),
    ("4_plus_fast_jitter", {"eq", "transport", "differential", "jitter"}),
    ("5_plus_flicker_dropouts", {"eq", "transport", "differential", "jitter", "flicker", "dropouts"}),
    ("6_full", {"eq", "transport", "differential", "jitter", "flicker", "dropouts", "hiss", "saturation"}),
]


def sample_rate(path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return int(json.loads(out)["streams"][0]["sample_rate"])


def write_flac(x: np.ndarray, sr: int, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "2",
                    "-i", "-", "-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24", str(path)],
                   input=np.ascontiguousarray(x, dtype=np.float32).tobytes(), check=True)


def write_wav(x: np.ndarray, sr: int, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "2",
                    "-i", "-", "-c:a", "pcm_s24le", "-map_metadata", "-1", "-fflags", "+bitexact", str(path)],
                   input=np.ascontiguousarray(x, dtype=np.float32).tobytes(), check=True)


def band_rms(x, sr):
    sos = signal.butter(4, [100, 8000], "bandpass", fs=sr, output="sos")
    return float(np.sqrt(np.mean(signal.sosfiltfilt(sos, x, axis=0) ** 2)))


def song_region(src: np.ndarray, sr: int, thresh_db: float = -60.0, pre_s: float = 0.3, post_s: float = 0.6):
    """Sample range from just before the source's first sound to just after its last."""
    loud = np.nonzero(np.abs(src).max(axis=1) > 10 ** (thresh_db / 20))[0]
    return max(0, int(loud[0] - pre_s * sr)), min(len(src), int(loud[-1] + post_s * sr))


def setup(tid: str, profile: dict, seed: int):
    """Source, sample rate, record gains, polarity and an Emulator for a song with a tape capture."""
    t = track(tid)
    z = np.load(OUT / f"{t.id}_aligned.npz")
    sr = int(z["sr"])
    src = decode(t.source_path).astype(np.float64)
    n = len(src)
    song = next((s for s in profile["songs"] if s["id"] == t.id), None)
    gains = song["gain_db"] if song else profile["gain_db"]
    pol = int(z["polarity"])
    emu = Emulator(profile, sr, n, seed=seed, record_gain_db=gains, polarity=pol)
    return t, z, sr, src, gains, pol, emu


def render_emulation(tid: str, profile: dict, seed: int, path: Path):
    """The full emulation at tape level (no level matching), registered as <tid>emu for analysis."""
    t, z, sr, src, gains, pol, emu = setup(tid, profile, seed)
    write_flac(emu.process(src), sr, path)
    register_virtual(f"{t.id}emu", t.id, path, len(src) / sr, f"{t.title} (emulated)")


ENGINE = Path(__file__).resolve().parent.parent / "build" / "bin" / "korre-render"


def engine_process(engine, src_path, profile: dict, gains: dict, pol: int, seed: int, ingredients) -> np.ndarray:
    """One render through the C++ engine (korre-render): the same model as Emulator.process
    (verify_engine.py), with the engine's streaming filters."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="korre_render_") as tmp:
        prof_path, out_path = Path(tmp) / "profile.json", Path(tmp) / "out.wav"
        prof_path.write_text(json.dumps(profile))
        subprocess.run([str(engine), str(src_path), str(out_path), "--profile", str(prof_path), "--seed", str(seed),
                        "--record-gain", f"{gains['L']},{gains['R']}", "--polarity", str(pol), "--bits", "float",
                        "--ingredients", ",".join(sorted(ingredients)) or "none"], check=True, stdout=subprocess.DEVNULL)
        return decode(out_path).astype(np.float64)


def render_track(tid: str, profile: dict, seed: int, engine=None, folder_name: str | None = None):
    t, z, sr, src, gains, pol, emu = setup(tid, profile, seed)
    if engine:
        process = lambda ingredients: engine_process(engine, t.source_path, profile, gains, pol, seed, ingredients)
    else:
        process = lambda ingredients: emu.process(src, ingredients)
    n = len(src)
    print(f"{t.id} {t.title}: {n / sr:.1f} s @ {sr} Hz, record gain L {gains['L']:+.2f} R {gains['R']:+.2f} dB, "
          f"polarity {pol:+d} (matched to the tape)")
    files = {}
    for name, ingredients in LADDER:
        if ingredients is None:
            files[name] = pol * src * np.array([10 ** (gains[c] / 20) for c in "LR"])
        else:
            files[name] = process(ingredients)
        print(f"  rendered {name}")

    d0 = float(np.interp(0, z["centers"], z["delay"]))  # tape-excerpt sample aligned with source sample 0
    tape_start = max(0.0, t.start - PAD) + d0 / sr
    tape = decode(t.path, tape_start, tape_start + n / sr + 0.5, sr=sr).astype(np.float64)[:n]
    if len(tape) < n:
        tape = np.pad(tape, ((0, n - len(tape)), (0, 0)))
    files["tape"] = tape
    full_tape_level = files["6_full"].copy()  # for analysis: untrimmed, before level matching

    # cut every file to the song itself, with the same short fades: the capture around it holds the
    # neighbouring songs, which would give the tape away in a blind comparison
    a, b = song_region(src, sr)
    fade = np.ones(b - a)
    k_in, k_out = int(0.03 * sr), int(0.15 * sr)
    fade[:k_in] = np.sin(np.linspace(0, np.pi / 2, k_in)) ** 2
    fade[-k_out:] = np.cos(np.linspace(0, np.pi / 2, k_out)) ** 2
    files = {k: v[a:b] * fade[:, None] for k, v in files.items()}
    n = b - a

    ref = band_rms(tape, sr)
    for k in files:
        files[k] = files[k] * (ref / band_rms(files[k], sr))
    peak = max(np.abs(v).max() for v in files.values())
    head = min(1.0, 0.95 / peak)  # common headroom so nothing clips; relative levels kept
    folder = OUT / "listening" / (folder_name or t.id)
    for k, v in files.items():
        write_flac(v * head, sr, folder / f"{k}.flac")

    pair = ["tape", "6_full"]
    random.Random(f"v{profile.get('version', 1)}-{seed}-{n}").shuffle(pair)  # fresh draw per model version
    # WAV, not FLAC: equal length and format give identical file sizes, so the size can't give it away
    for label, key in zip("XY", pair):
        write_wav(files[key] * head, sr, folder / "blind" / f"{label}.wav")
    (folder / "blind" / "KEY_dont_peek.txt").write_text(f"X = {pair[0]}\nY = {pair[1]}\n")

    # make the full render analysable as a capture (at tape level, before level matching)
    raw = folder / "_6_full_tape_level.flac"
    write_flac(full_tape_level, sr, raw)
    register_virtual(f"{t.id}emu", t.id, raw, len(src) / sr, f"{t.title} (emulated)")
    print(f"wrote {folder}/ (common headroom {20 * np.log10(head):+.1f} dB); registered {t.id}emu for analysis")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("track", nargs="?")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--source")
    ap.add_argument("--out")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--engine", nargs="?", const=str(ENGINE),
                    help="render the listening set with the C++ engine (korre-render) instead of emulator.py")
    ap.add_argument("--folder", help="name of the listening set's folder under out/listening/ (default: the track id)")
    ap.add_argument("--record-gain", nargs=2, type=float, metavar=("L", "R"),
                    help="record gain in dB for a song the profile was not fitted on (default: the profile's)")
    args = ap.parse_args()
    profile = json.loads(Path(args.profile).read_text())
    if args.track:
        if args.record_gain:  # a song of its own level: listed in the profile's songs, where setup() looks
            profile["songs"] = [s_ for s_ in profile["songs"] if s_["id"] != track(args.track).id] + [
                dict(id=track(args.track).id, gain_db=dict(L=args.record_gain[0], R=args.record_gain[1]))]
        render_track(args.track, profile, args.seed, engine=args.engine, folder_name=args.folder)
    else:
        if not (args.source and args.out):
            ap.error("give a track id, or --source and --out")
        sr = sample_rate(args.source)
        x = decode(args.source).astype(np.float64)
        y = Emulator(profile, sr, len(x), seed=args.seed).process(x)
        y *= min(1.0, 0.95 / np.abs(y).max())
        write_flac(y, sr, Path(args.out))
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
