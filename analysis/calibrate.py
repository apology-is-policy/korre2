"""Fit an emulator profile to a real tape by analysis-by-synthesis (run align.py on the song first).

    python calibrate.py --track B3 --name wmd6c_xlii_sideB --init --iters 4

--init builds a starting profile from the tape's own measurements (fitprofile.song_stats for the
transport, differential wobble, dropouts, hiss, gains and static response; the demodulated timing
and AM spectra of signature.py for the fast jitter and the flicker). Each iteration then:
  render the emulation of the same source at tape level -> align.py -> signature.py
  -> compare with the tape's signature -> correct the profile where they differ.
The estimators have their own smoothing, floors and leakage (timing shows up a little as AM,
hiss as both), so matching measure(emulation) to measure(tape) is what calibrates the profile,
not the raw measurements themselves.

Writes profiles/<name>.json after every iteration and out/calib/<track>_history.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np

from fitprofile import CUBIC_REL_DB, CUBIC_SONG, EQ_GRID, PROFILES, song_stats
from measure import OUT
from render import render_emulation
from signature import DEV_RATES, OCT, RATES, report, signature

CAL = OUT / "calib"
ALPHA = 0.8  # damping of each correction (in log/dB terms)
JITTER_TOP_HZ = 4000.0  # fast timing is assumed flat from the last measured band up to here
AM_KAPPA = 0.7  # demodulated AM reads ~0.7x the injected AM power (synthetic test, FINDINGS)
TIMING_OCTS = (2000, 4000, 8000)  # octaves where the timing estimate is cleanest
FLICKER_RATES = slice(0, 7)  # rate bands 3..384 Hz carry the flicker depth estimate


def centres(rates):
    return np.array([np.sqrt(a * b) for a, b in rates])


def widths(rates):
    return np.array([b - a for a, b in rates])


def mean_pm(sig, octs=TIMING_OCTS):
    """Timing power per rate band (us^2), mean over channels and the cleanest octaves."""
    return np.nanmean([sig["pm"][fc].mean(axis=0) for fc in octs], axis=0)


# ---------------------------------------------------------------- initial profile
def init_profile(tid: str, name: str, tape_sig: dict) -> dict:
    st = song_stats(tid)
    prof = dict(version=2, name=name, created=str(date.today()),
                songs=[dict(id=st["id"], title=st["title"], side=st["side"], gain_db=st["gain_db"],
                            delay_us=st["delay_us"])],
                gain_db=st["gain_db"], delay_us=st["delay_us"],
                eq=dict(freqs=EQ_GRID, **{k: st["eq"][k] for k in ("L", "R", "phase_L", "phase_R")}),
                hiss=st["hiss"], transport=dict(st["transport"], crossover_hz=45.0),
                differential=st["differential"], dropouts=st["dropouts"])
    old = PROFILES / f"{name}.json"
    ref_rms = None
    if old.exists():
        ref_rms = json.loads(old.read_text()).get("saturation", {}).get("ref_rms_dbfs")
    if ref_rms is None:
        ref_rms = song_stats(CUBIC_SONG).get("cubic_ref_rms_dbfs")
    prof["saturation"] = dict(cubic_rel_db=CUBIC_REL_DB, ref_rms_dbfs=ref_rms, source=CUBIC_SONG)

    # fast jitter: the tape's demodulated timing PSD above 48 Hz, split by the L/R coherence
    c, w = centres(RATES), widths(RATES)
    pm = mean_pm(tape_sig) / w  # us^2/Hz
    fast = c >= 48
    coh = np.nan_to_num(tape_sig["pm_coh"][8000], nan=0.3)
    freqs = [45.0] + c[fast].tolist() + [JITTER_TOP_HZ]
    tot = [pm[fast][0]] + pm[fast].tolist() + [pm[fast][-1]]
    rho = [coh[fast][0]] + coh[fast].tolist() + [coh[fast][-1]]
    prof["jitter"] = dict(freqs=freqs, psd_total_us2_per_hz=tot, rho=rho)
    split_jitter(prof)

    # flicker: half the measured AM per octave (the rest is leakage and hiss), shape from 8 kHz
    am8 = tape_sig["am"][8000].mean(axis=0) / w
    ok = ~np.isnan(am8)
    depth = [float(np.sqrt(np.nansum(tape_sig["am"][fc].mean(axis=0)[FLICKER_RATES]) * 0.5)) for _, _, fc in OCT]
    rho_am = [float(np.nanmean(tape_sig["am_coh"][fc][:5])) for _, _, fc in OCT]
    prof["flicker"] = dict(rate_freqs=[1.0] + c[ok].tolist() + [JITTER_TOP_HZ],
                           rate_psd=[am8[ok][0]] + am8[ok].tolist() + [am8[ok][-1]],
                           depth_freqs=[fc for _, _, fc in OCT], depth_total=depth, rho=rho_am)
    split_flicker(prof)
    return prof


def split_jitter(prof):
    j = prof["jitter"]
    tot, rho = np.array(j["psd_total_us2_per_hz"]), np.clip(np.array(j["rho"]), 0, 0.99)
    j["psd_common_us2_per_hz"] = (tot * rho).tolist()
    j["psd_indep_us2_per_hz"] = (tot * (1 - rho)).tolist()


def split_flicker(prof):
    """Common and per-channel depth per octave, from the total depth and that octave's L/R share."""
    fl = prof["flicker"]
    d = np.array(fl["depth_total"])
    rho = np.clip(np.broadcast_to(np.asarray(fl["rho"], float), d.shape), 0, 0.99)
    fl["depth_common"] = (d * np.sqrt(rho)).tolist()
    fl["depth_indep"] = (d * np.sqrt(1 - rho)).tolist()


# ---------------------------------------------------------------- one correction step
def update(prof: dict, tape: dict, emu: dict) -> list[str]:
    notes = []
    a = ALPHA
    # static response and gain
    for ch in "LR":
        d_eq = np.array(tape["eq"][ch]) - np.array(emu["eq"][ch])
        d_ph = np.array(tape["phase"][ch]) - np.array(emu["phase"][ch])
        d_ph = (d_ph + np.pi) % (2 * np.pi) - np.pi
        k = np.ones(5) / 5  # 5 x 1/24 octave
        d_eq, d_ph = np.convolve(d_eq, k, mode="same"), np.convolve(d_ph, k, mode="same")
        prof["eq"][ch] = (np.array(prof["eq"][ch]) + a * d_eq).tolist()
        prof["eq"][f"phase_{ch}"] = (np.array(prof["eq"][f"phase_{ch}"]) + a * d_ph).tolist()
        dg = tape["gain_db"][ch] - emu["gain_db"][ch]
        for target in (prof["gain_db"], prof["songs"][0]["gain_db"]):
            target[ch] += a * dg
        notes.append(f"{ch}: gain {dg:+.2f} dB, eq max |d| {np.max(np.abs(d_eq)):.2f} dB, "
                     f"phase max |d| {np.degrees(np.max(np.abs(d_ph))):.1f} deg")

    # slow transport. Below 6 Hz the delay tracker follows the wobble, so the tracked speed deviation is
    # the evidence. Above that it cannot (85 ms windows, 150 ms smoothing): its reading there is mostly
    # its own noise, and extra flutter lands in the timing left after the warp instead. So from 6 Hz up
    # the demodulated timing decides. (Matching the tracked value up there made the metal fit diverge.)
    tr = prof["transport"]
    f = np.array(tr["freqs"])
    low = [k for k, (lo, hi) in enumerate(DEV_RATES) if hi <= 6]
    r_dev = (np.array(tape["dev"]) / np.array(emu["dev"]))[low]
    hi_bands = [k for k, (lo, hi) in enumerate(RATES) if 6 <= lo < 48]
    r_pm = (mean_pm(tape) / mean_pm(emu))[hi_bands]
    pts_f = np.concatenate([centres(DEV_RATES)[low], centres(RATES)[hi_bands]])
    pts_r = np.clip(np.concatenate([r_dev, r_pm]), 0.5, 2.0) ** a
    corr = np.exp(np.interp(np.log(np.maximum(f, 0.1)), np.log(pts_f), np.log(pts_r)))
    tr["psd_us2_per_hz"] = (np.array(tr["psd_us2_per_hz"]) * corr).tolist()
    notes.append("transport x " + " ".join(f"{v:.2f}" for v in pts_r))

    # fast jitter: total per rate band, and the common share from the L/R coherence at 8 kHz
    j = prof["jitter"]
    jf = np.array(j["freqs"])
    c = centres(RATES)
    r = mean_pm(tape) / mean_pm(emu)
    ok = ~np.isnan(r) & (c >= 48)
    rr = np.clip(r[ok], 0.25, 4) ** a
    corr = np.exp(np.interp(np.log(jf), np.log(c[ok]), np.log(rr)))
    j["psd_total_us2_per_hz"] = (np.array(j["psd_total_us2_per_hz"]) * corr).tolist()
    dcoh = np.nan_to_num(tape["pm_coh"][8000] - emu["pm_coh"][8000])
    drho = np.interp(np.log(jf), np.log(c[ok]), dcoh[ok])
    j["rho"] = np.clip(np.array(j["rho"]) + a * drho, 0, 0.99).tolist()
    split_jitter(prof)
    notes.append("jitter x " + " ".join(f"{v:.2f}" for v in rr) + " | rho " + " ".join(f"{v:.2f}" for v in j["rho"]))

    # flicker depth per octave: emu AM = kappa * injected + leakage; solve for the injected depth
    fl = prof["flicker"]
    new = []
    for (_, _, fc), d in zip(OCT, fl["depth_total"]):
        am_t = np.nansum(tape["am"][fc].mean(axis=0)[FLICKER_RATES])
        am_e = np.nansum(emu["am"][fc].mean(axis=0)[FLICKER_RATES])
        leak = max(am_e - AM_KAPPA * d ** 2, 0.0)
        target = np.sqrt(max(am_t - leak, 0.0) / AM_KAPPA)
        new.append(float(max(d + a * (target - d), 1e-4)))
    fl["depth_total"] = new
    # L/R share per octave, from the AM coherence at low rates (where flicker, not leakage, dominates)
    rho = np.broadcast_to(np.asarray(fl["rho"], float), (len(OCT),)).copy()
    for k, (_, _, fc) in enumerate(OCT):
        rho[k] += a * np.nanmean(tape["am_coh"][fc][:5] - emu["am_coh"][fc][:5])
    fl["rho"] = np.clip(rho, 0, 0.99).tolist()
    split_flicker(prof)
    # rate spectrum of the flicker, from the two top octaves (where the flicker is largest)
    c = centres(RATES)
    ratio = np.nanmean([tape["am"][fc].mean(axis=0) / emu["am"][fc].mean(axis=0) for fc in (8000, 13000)], axis=0)
    ok = ~np.isnan(ratio)
    rr = np.clip(ratio[ok], 0.25, 4) ** a
    rf = np.array(fl["rate_freqs"])
    corr = np.exp(np.interp(np.log(rf), np.log(c[ok]), np.log(rr)))
    fl["rate_psd"] = (np.array(fl["rate_psd"]) * corr).tolist()
    notes.append("flicker depth % " + " ".join(f"{v * 100:.2f}" for v in new)
                 + " | rho " + " ".join(f"{v:.2f}" for v in fl["rho"])
                 + " | rate shape x " + " ".join(f"{v:.2f}" for v in rr))
    return notes


def summary(prof):
    j, fl, tr = prof["jitter"], prof["flicker"], prof["transport"]
    integ = lambda f, P: float(np.sqrt(np.trapezoid(P, f)))
    ff = np.geomspace(j["freqs"][0], j["freqs"][-1], 400)
    P = lambda key: np.exp(np.interp(np.log(ff), np.log(j["freqs"]), np.log(np.maximum(j[key], 1e-30))))
    return (f"transport {integ(tr['freqs'], tr['psd_us2_per_hz']):.1f} us RMS; jitter common "
            f"{integ(ff, P('psd_common_us2_per_hz')):.2f} us, per channel {integ(ff, P('psd_indep_us2_per_hz')):.2f} us; "
            f"flicker depth % at 1k..13k " + " ".join(f"{d * 100:.2f}" for d in fl["depth_total"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--track", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--refresh-noise", action="store_true",
                    help="replace the profile's noise with the recorded-gap noise before iterating")
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--only", default=None,
                    help="comma-separated profile sections to correct, e.g. 'transport,jitter': everything else "
                         "stays as it is (to adapt a side profile's wobble depth to one stretch of tape)")
    ap.add_argument("--tones", choices=("song", "side"), default="song",
                    help="measure the deck's steady tones in the song's own stretch, or over the whole side "
                         "(use 'side' when the song has bass throughout)")
    args = ap.parse_args()
    CAL.mkdir(parents=True, exist_ok=True)
    path = PROFILES / f"{args.name}.json"
    tape_sig = signature(args.track)
    if args.init:
        prof = init_profile(args.track, args.name, tape_sig)
        from fitprofile import steady_tones
        prof["tones"] = steady_tones(args.track, whole_side=args.tones == "side")
        path.write_text(json.dumps(prof, separators=(",", ":")))
        print(f"initial profile -> {path}\n  {summary(prof)}", flush=True)
    prof = json.loads(path.read_text())
    if args.refresh_noise:
        from fitprofile import recorded_noise_psd
        from investigate import load
        from tracks import track
        t = track(args.track)
        fh, Ph = recorded_noise_psd(t.side, load(t.id)[0])
        prof["hiss"] = dict(freqs=fh.tolist(), L=Ph[:, 0].tolist(), R=Ph[:, 1].tolist(),
                            note="recorded gaps between songs (not the blank leader)")
        from fitprofile import steady_tones
        prof["tones"] = steady_tones(args.track, whole_side=args.tones == "side")
        path.write_text(json.dumps(prof, separators=(",", ":")))
        print("noise replaced with the recorded-gap noise; deck tones: "
              + ", ".join(f"{t_['hz']:.2f} Hz ({t_['L_dbfs']:.0f}/{t_['R_dbfs']:.0f} dBFS)" for t_ in prof["tones"]),
              flush=True)
    hist_path = CAL / f"{args.track}_history.json"
    history = json.loads(hist_path.read_text()) if hist_path.exists() and not args.init else []
    emu_id = f"{args.track}emu"
    for it in range(args.iters):
        render_emulation(args.track, prof, args.seed, CAL / f"{emu_id}.flac")
        out = subprocess.run([sys.executable, "align.py", emu_id], capture_output=True, text=True,
                             cwd=Path(__file__).parent)
        if out.returncode:
            raise SystemExit(out.stdout + out.stderr)
        if "WARNING" in out.stdout:
            raise SystemExit(f"stopping: the emulation no longer aligns cleanly, so its measurements can't be "
                             f"trusted (profile left as of the previous iteration is in {path}):\n" + out.stdout)
        emu_sig = signature(emu_id, cache=False)
        print(f"\n######## iteration {len(history) + 1}", flush=True)
        report(emu_sig, tape_sig)
        before = json.loads(json.dumps(prof))
        notes = update(prof, tape_sig, emu_sig)
        if args.only:
            keep = set(args.only.split(","))
            for key in ("eq", "gain_db", "songs", "transport", "jitter", "flicker"):
                if key not in keep:
                    prof[key] = before[key]
            notes = [n for n in notes if any(n.startswith(k) for k in keep)] + [f"(only {args.only} corrected)"]
        prof["created"] = str(date.today())
        path.write_text(json.dumps(prof, separators=(",", ":")))
        history.append(dict(iteration=len(history) + 1, notes=notes, summary=summary(prof)))
        hist_path.write_text(json.dumps(history, indent=1))
        print("  corrections: " + "\n               ".join(notes))
        print(f"  profile now: {summary(prof)}", flush=True)


if __name__ == "__main__":
    main()
