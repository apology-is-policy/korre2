"""Check the C++ tape engine (tape/, through korre-render) against the Python model.

    python verify_engine.py B3 --profile ../profiles/wmd6c_xlii_sideB.json [--seconds 90]
    python verify_engine.py B3 --profile ../profiles/wmd6c_xlii_sideB.json --register B3cpp
        only render the whole song with the engine and register it for align.py / signature.py

Four questions, in the order printed:
 1. Filters. Are the engine's two filter designs the ones streamref.py computes? (number by number)
 2. Arithmetic. Given the wobble, jitter, flicker and noise the engine really used (korre-render
    --trace), does its output equal the Python chain applied with those same signals? Also checks that
    the random signals do not depend on which ingredients are switched on.
 3. Random signals. Do they have the spectra and levels the profile asks for, and are the ones that
    should be independent uncorrelated?
 4. Definitions. How far is the engine's short filter for the static response from the whole-track
    FFT of emulator.py? (This is a property of the design, not an error of the port.)
The last check of all, that a full render still measures like the tape, is signature.py on --register.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from scipy import signal

import streamref
from common import decode
from emulator import INGREDIENTS, Emulator
from measure import OUT
from tracks import register_virtual, track

RENDER = Path(__file__).resolve().parent.parent / "build" / "bin" / "korre-render"
CONTROLS = ("transport", "differential", "jitter_common", "jitter_left", "jitter_right", "flicker_common",
            "flicker_left", "flicker_right", "gainnoise_left", "gainnoise_right", "dropout_left", "dropout_right",
            "background_left", "background_right")
EDGE_S = 0.5  # the ends of a clip are left out of comparisons: the engine starts from silence


def db(x):
    return 20 * np.log10(max(float(x), 1e-300))


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def render(render_bin, src_path, out_path, profile_path, gains, polarity, seed, ingredients=None, trace=None, bits="float"):
    cmd = [str(render_bin), str(src_path), str(out_path), "--profile", str(profile_path), "--seed", str(seed),
           "--record-gain", f"{gains['L']},{gains['R']}", "--polarity", str(polarity), "--bits", bits]
    if ingredients is not None:
        cmd += ["--ingredients", ",".join(sorted(ingredients)) or "none"]
    if trace is not None:
        cmd += ["--trace", str(trace)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def load_trace(folder: Path) -> dict:
    t = {k: np.fromfile(folder / f"{k}.f64") for k in CONTROLS}
    t["info"] = json.loads((folder / "info.json").read_text())
    for k in ("response_left", "response_right", "flicker_filter_common", "flicker_filter_own", "gainnoise_filter_left",
              "gainnoise_filter_right"):
        t[k] = np.fromfile(folder / f"{k}.f64")
    return t


def band_levels(x, sr, bands, nperseg):
    f, P = signal.welch(x, sr, nperseg=min(nperseg, len(x)), detrend=False)
    return np.array([np.sqrt(np.trapezoid(P[(f >= lo) & (f < hi)], f[(f >= lo) & (f < hi)])) for lo, hi in bands])


def table_levels(freqs, psd, bands, log=False):
    out = []
    for lo, hi in bands:
        f = np.geomspace(max(lo, 1e-3), hi, 4000) if log else np.linspace(lo, hi, 4000)
        if log:
            P = np.exp(np.interp(np.log(f), np.log(freqs), np.log(np.maximum(psd, 1e-30))))
            P[(f < freqs[0]) | (f > freqs[-1])] = 0
        else:
            P = np.interp(f, freqs, psd, left=0, right=0)
        out.append(np.sqrt(np.trapezoid(P, f)))
    return np.array(out)


def row(label, values, fmt="{:8.3f}"):
    print(f"    {label:<22}" + " ".join(fmt.format(v) for v in values))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("track")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--seconds", type=float, default=90.0, help="length of the excerpt used for checks 1-4")
    ap.add_argument("--start", type=float, default=60.0, help="where the excerpt starts in the song")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--long-minutes", type=int, default=20, help="length of the silent run used to judge the slow wobble")
    ap.add_argument("--render", default=str(RENDER), help="the korre-render binary")
    ap.add_argument("--register", help="render the whole song with the engine and register it under this id")
    args = ap.parse_args()

    profile_path = Path(args.profile).resolve()
    profile = json.loads(profile_path.read_text())
    t = track(args.track)
    z = np.load(OUT / f"{t.id}_aligned.npz")
    sr = int(z["sr"])
    song = next((s for s in profile["songs"] if s["id"] == t.id), None)
    gains = song["gain_db"] if song else profile["gain_db"]
    polarity = int(z["polarity"])

    if args.register:
        out = OUT / "listening" / t.id / "_engine_tape_level.flac"
        out.parent.mkdir(parents=True, exist_ok=True)
        render(args.render, t.source_path, out, profile_path, gains, polarity, args.seed, bits="24")
        n = len(decode(t.source_path))
        register_virtual(args.register, t.id, out, n / sr, f"{t.title} (C++ engine)")
        print(f"rendered {out} with the engine; registered as {args.register}")
        return

    work = Path(tempfile.mkdtemp(prefix="korre_verify_"))
    full = decode(t.source_path).astype(np.float64)
    a = int(args.start * sr)
    x = full[a: a + int(args.seconds * sr)]
    n = len(x)
    src_path = work / "excerpt.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "-",
                    "-c:a", "pcm_f32le", str(src_path)], input=np.ascontiguousarray(x, dtype=np.float32).tobytes(), check=True)
    x = decode(src_path).astype(np.float64)  # exactly what the engine reads
    edge = int(EDGE_S * sr)
    inner = slice(edge, n - edge)
    print(f"{t.id} {t.title}: {n / sr:.0f} s from {args.start:.0f} s at {sr} Hz, profile {profile['name']}, seed {args.seed}")

    render(args.render, src_path, work / "all.wav", profile_path, gains, polarity, args.seed, trace=work / "trace")
    tr = load_trace(work / "trace")
    info = tr["info"]
    print(f"  engine delay {info['delay']['total']} frames ({1e3 * info['delay']['total'] / sr:.1f} ms): response "
          f"{info['delay']['response']}, timing {info['delay']['timing']}, flicker {info['delay']['flicker']}")

    # ------------------------------------------------------------------ 1. filters
    print("\n1. Filter designs, engine against streamref.py (largest difference relative to the largest tap)")
    designs = [("response L", streamref.response_filter(profile, "L", sr)),
               ("response R", streamref.response_filter(profile, "R", sr)),
               ("flicker common", streamref.flicker_filter(profile["flicker"]["depth_freqs"], profile["flicker"]["depth_common"], sr)),
               ("flicker own", streamref.flicker_filter(profile["flicker"]["depth_freqs"], profile["flicker"]["depth_indep"], sr))]
    mn = profile.get("gain_noise")
    if mn:
        designs += [(f"gain noise {c}", streamref.flicker_filter(mn["depth_freqs"], mn[f"depth_{c}"], sr, held=True)) for c in "LR"]
    for name, mine in designs:
        key = {"response L": "response_left", "response R": "response_right", "flicker common": "flicker_filter_common",
               "flicker own": "flicker_filter_own", "gain noise L": "gainnoise_filter_left", "gain noise R": "gainnoise_filter_right"}[name]
        theirs = tr[key]
        same_len = len(theirs) == len(mine)
        diff = np.abs(theirs - mine).max() / np.abs(mine).max() if same_len else np.inf
        print(f"    {name:<15} {len(theirs):6d} taps   {db(diff):7.1f} dB" + ("" if same_len else f"   LENGTH DIFFERS (python {len(mine)})"))

    # ------------------------------------------------------------------ 2. arithmetic
    print("\n2. Engine output against the Python chain run with the engine's own control signals")
    print("   (difference relative to the signal, dB; then the same for the difference against the plain source)")
    sets = [("gain only", set()), ("saturation", {"saturation"}), ("eq", {"eq"}), ("eq + saturation", {"eq", "saturation"}),
            ("transport + differential", {"transport", "differential"}), ("jitter", {"jitter"}), ("flicker", {"flicker"}),
            ("dropouts + hiss", {"dropouts", "hiss"}), ("everything", set(INGREDIENTS))]
    plain = None
    for label, ing in sets:
        out_path = work / "set.wav"
        trace_dir = work / "trace_set"
        render(args.render, src_path, out_path, profile_path, gains, polarity, args.seed, ingredients=ing, trace=trace_dir)
        got = decode(out_path).astype(np.float64)
        want = streamref.apply(x, profile, sr, tr, ing, gains, polarity)
        if plain is None:
            plain = want
        same_controls = all(np.array_equal(np.fromfile(trace_dir / f"{k}.f64"), tr[k]) for k in CONTROLS)
        effect = rms((want - plain)[inner])  # how much this set changes the signal at all
        print(f"    {label:<26} {db(rms((got - want)[inner]) / rms(want[inner])):7.1f} dB"
              f"   (the set itself changes the signal by {db(effect / rms(plain[inner])) if effect > 0 else -np.inf:6.1f} dB)"
              + ("" if same_controls else "   CONTROL SIGNALS DIFFER FROM THE FULL RENDER"))

    # ------------------------------------------------------------------ 3. random signals
    print("\n3. The engine's random signals against the profile's tables")
    tp, df, jt, fl = profile["transport"], profile["differential"], profile["jitter"], profile["flicker"]
    slow_bands = [(0.05, 0.5), (0.5, 3), (3, 12), (12, 30), (30, 45)]
    fx = tp["crossover_hz"]
    tf, tP = np.array(tp["freqs"]), np.array(tp["psd_us2_per_hz"])
    tP = tP * np.clip((fx + 5 - tf) / 10, 0, 1)
    # The slow wobble is dominated by narrow lines and by drift below 0.5 Hz, which wander in strength
    # over tens of seconds, so its spectrum only shows over a long stretch: 20 minutes of silence at a low
    # sample rate (the wobble does not depend on the audio).
    long_sr, long_s = 8000, 60 * args.long_minutes
    long_dir = work / "long"
    long_dir.mkdir()
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"anullsrc=r={long_sr}:cl=stereo", "-t", str(long_s), "-c:a", "pcm_s16le", str(long_dir / "silence.wav")], check=True)
    render(args.render, long_dir / "silence.wav", long_dir / "out.wav", profile_path, gains, polarity, args.seed,
           ingredients=set(), trace=long_dir / "trace", bits="16")
    dec = 16
    slow = lambda name: signal.resample_poly(np.fromfile(long_dir / "trace" / f"{name}.f64"), 1, dec)
    long_transport, long_diff = slow("transport"), slow("differential")
    shutil.rmtree(long_dir)
    print(f"  slow timing over {args.long_minutes} min, RMS in microseconds per band [Hz]   "
          + " ".join(f"{lo:g}-{hi:g}".rjust(8) for lo, hi in slow_bands))
    # these tables are on a grid as coarse as the lowest band is wide and fall steeply there, so the
    # table's share of a band is the sum of its points, as a synthesised signal holds it
    by_points = lambda fr, P: np.array([np.sqrt(np.sum(P[(fr >= lo) & (fr < hi)]) * (fr[1] - fr[0])) for lo, hi in slow_bands])
    # a profile's steady lines (transport.lines) are part of the wobble: their power is added to the
    # table's in the band each falls in, with the table's fade at the crossover
    tlines = tp.get("lines", [])
    line_power = np.array([sum(l["us"] ** 2 * float(np.clip((fx + 5 - l["hz"]) / 10, 0, 1)) for l in tlines if lo <= l["hz"] < hi)
                           for lo, hi in slow_bands])
    row("transport: table" + (" + lines" if tlines else ""), np.sqrt(by_points(tf, tP) ** 2 + line_power))
    row("transport: engine", band_levels(long_transport, long_sr / dec, slow_bands, 1 << 15))
    row("differential: table", by_points(np.array(df["freqs"]), np.array(df["psd_us2_per_hz"])))
    row("differential: engine", band_levels(long_diff, long_sr / dec, slow_bands, 1 << 15))
    f, P = signal.welch(long_transport, long_sr / dec, nperseg=1 << 15, detrend=False)
    lines = []
    for lo, hi in ((1, 3), (5, 12), (20, 32), (40, 48)):
        m, mt = (f > lo) & (f < hi), (tf > lo) & (tf < hi)
        here = [l for l in tlines if lo < l["hz"] < hi]
        wanted = max(here, key=lambda l: l["us"])["hz"] if here else tf[mt][np.argmax(tP[mt])]
        lines.append(f"{lo}-{hi} Hz: {'line' if here else 'table'} {wanted:.2f}, engine {f[m][np.argmax(P[m])]:.2f}")
    print("    strongest line in " + "; ".join(lines))

    fast_bands = [(45, 90), (90, 180), (180, 360), (360, 720), (720, 1440), (1440, 2880), (2880, 4000)]
    jf = np.array(jt["freqs"])
    print("  fast timing, RMS in microseconds per band [Hz]   " + " ".join(f"{lo:g}-{hi:g}".rjust(8) for lo, hi in fast_bands))
    row("common: table", table_levels(jf, np.array(jt["psd_common_us2_per_hz"]), fast_bands, log=True))
    row("common: engine", band_levels(tr["jitter_common"], sr, fast_bands, 1 << 14))
    row("own: table", table_levels(jf, np.array(jt["psd_indep_us2_per_hz"]), fast_bands, log=True))
    row("own, left: engine", band_levels(tr["jitter_left"], sr, fast_bands, 1 << 14))
    row("own, right: engine", band_levels(tr["jitter_right"], sr, fast_bands, 1 << 14))

    rate_bands = [(1, 4), (4, 16), (16, 64), (64, 256), (256, 1024), (1024, 4000)]
    rf, rP = np.array(fl["rate_freqs"]), np.array(fl["rate_psd"])
    want = table_levels(rf, rP, rate_bands, log=True)
    want = want / np.sqrt(np.sum(table_levels(rf, rP, [(rf[0], rf[-1])], log=True) ** 2))
    print("  flicker, share of unit RMS per rate band [Hz]    " + " ".join(f"{lo:g}-{hi:g}".rjust(8) for lo, hi in rate_bands))
    row("table", want)
    for k in ("flicker_common", "flicker_left", "flicker_right"):
        row(f"{k.split('_')[1]}: engine", band_levels(tr[k], sr, rate_bands, 1 << 16))
    print("    overall RMS (should be 1): " + ", ".join(f"{k.split('_')[1]} {rms(tr[k]):.3f}" for k in ("flicker_common", "flicker_left", "flicker_right")))
    if mn:
        from calibrate import rate_share
        mf, mP = np.array(mn["rate_freqs"]), np.array(mn["rate_psd"])
        mod_bands = [(4, 16), (16, 64), (64, 256), (256, 1024), (1024, 4000)]
        print("  gain noise, share of unit RMS per rate band [Hz]  " + " ".join(f"{lo:g}-{hi:g}".rjust(8) for lo, hi in mod_bands))
        row("table", [np.sqrt(rate_share(mf, mP, lo, hi)) for lo, hi in mod_bands])
        for k in ("gainnoise_left", "gainnoise_right"):
            row(f"{k.split('_')[1]}: engine", band_levels(tr[k], sr, mod_bands, 1 << 16))
        print(f"    overall RMS (should be 1): left {rms(tr['gainnoise_left']):.3f}, right {rms(tr['gainnoise_right']):.3f}; "
              f"correlation left / right {np.corrcoef(tr['gainnoise_left'], tr['gainnoise_right'])[0, 1]:+.4f}, "
              f"left / flicker left {np.corrcoef(tr['gainnoise_left'], tr['flicker_left'])[0, 1]:+.4f}")

    hz = profile["hiss"]
    hf = np.array(hz["freqs"])
    oct_bands = [(22, 45), (45, 90), (90, 180), (180, 355), (355, 710), (710, 1400), (1400, 2800), (2800, 5600), (5600, 11200),
                 (11200, min(20000, sr / 2))]
    print("  background noise, dBFS per octave band [Hz]      " + " ".join(f"{lo:g}".rjust(8) for lo, _ in oct_bands))
    # The engine's background is noise plus the steady tones; take the tones out to look at the noise.
    tt = np.arange(n) / sr
    basis = [fn(2 * np.pi * tone["hz"] * tt) for tone in profile.get("tones", []) for fn in (np.cos, np.sin)]
    noise = {}
    for side in ("left", "right"):
        b = tr[f"background_{side}"]
        if basis:
            A = np.stack(basis, axis=1)
            b = b - A @ np.linalg.lstsq(A, b, rcond=None)[0]
        noise[side] = b
    for c, side in (("L", "left"), ("R", "right")):
        row(f"{c}: table", [db(v) for v in table_levels(hf, np.array(hz[c]), oct_bands)], "{:8.2f}")
        row(f"{c}: engine", [db(v) for v in band_levels(noise[side], sr, oct_bands, 1 << 15)], "{:8.2f}")
    for tone in profile.get("tones", []):
        w = np.exp(-2j * np.pi * tone["hz"] * np.arange(n) / sr)
        lv = [db(np.abs(np.mean(tr[f"background_{s}"] * w)) * np.sqrt(2)) for s in ("left", "right")]
        print(f"    tone {tone['hz']:6.2f} Hz: table L {tone['L_dbfs']:7.2f} R {tone['R_dbfs']:7.2f} dBFS, engine L {lv[0]:7.2f} R {lv[1]:7.2f}")

    sig = dict(tr, noise_left=noise["left"], noise_right=noise["right"])
    pairs = [("jitter_left", "jitter_right"), ("jitter_common", "jitter_left"), ("flicker_left", "flicker_right"),
             ("flicker_common", "flicker_left"), ("noise_left", "noise_right"), ("jitter_common", "flicker_common")]
    print("  correlation between signals that should be independent (0 within about 0.02):")
    print("    " + ", ".join(f"{a.replace('_', ' ')} / {b.replace('_', ' ')} {np.corrcoef(sig[a], sig[b])[0, 1]:+.4f}" for a, b in pairs))
    kurt = lambda v: float(np.mean((v - v.mean()) ** 4) / np.var(v) ** 2)
    print("  kurtosis (3 for a Gaussian signal): " + ", ".join(f"{k.replace('_', ' ')} {kurt(sig[k]):.2f}"
                                                               for k in ("jitter_common", "flicker_common", "noise_left")))

    # ------------------------------------------------------------------ 4. definitions
    print("\n4. The engine's static-response filter against emulator.py's whole-track response (eq + saturation only)")
    emu = Emulator(profile, sr, n, seed=args.seed, record_gain_db=gains, polarity=polarity)
    whole = emu.process(x, {"eq", "saturation"})
    short = streamref.apply(x, profile, sr, tr, {"eq", "saturation"}, gains, polarity)
    bands = [(20, 60), (60, 200), (200, 2000), (2000, 8000), (8000, 16000), (16000, min(21000, sr / 2 - 1))]
    print("    band [Hz]            " + " ".join(f"{lo:g}-{hi:g}".rjust(11) for lo, hi in bands))
    diffs, levels = [], []
    for lo, hi in bands:
        sos = signal.butter(4, [lo, hi], "bandpass", fs=sr, output="sos")
        d = signal.sosfilt(sos, (whole - short), axis=0)[inner]
        s = signal.sosfilt(sos, whole, axis=0)[inner]
        diffs.append(db(rms(d) / rms(s)))
        levels.append(db(rms(s) / rms(whole[inner])))
    print("    difference re band   " + " ".join(f"{v:11.1f}" for v in diffs))
    print("    band level re total  " + " ".join(f"{v:11.1f}" for v in levels))
    print(f"    overall: {db(rms((whole - short)[inner]) / rms(whole[inner])):.1f} dB relative to the signal")
    shutil.rmtree(work)


if __name__ == "__main__":
    main()
