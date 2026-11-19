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
PM_KAPPA = 0.55  # and the demodulated timing about 0.55x the injected jitter power (48-96 Hz, where next to all of it is jitter)
TIMING_OCTS = (2000, 4000, 8000)  # octaves where the timing estimate is cleanest
FLICKER_RATES = slice(0, 7)  # rate bands 3..384 Hz carry the flicker depth estimate
FINE_FROM_HZ, FINE_TO_HZ = 3.0, 50.0  # the transport is corrected in fine steps from the whole timing (to where its table fades out)
# Gain noise: a fast wobble of each channel's level as a whole (the same depth at every frequency),
# with a depth per channel. Its evidence is the AM at 96..384 Hz in the 1 and 2 kHz octaves, where the
# timing's own contribution to the AM is smallest and the flicker has little left.
GAIN_EVIDENCE = ((1000, slice(5, 6)), (2000, slice(5, 7)))  # (octave, rate bands): 96-192; 96-192 and 192-384 Hz
# Its rate spectrum: flat to 150 Hz, gone by 600 Hz. On the metal tape the left-minus-right AM is white
# from 12 to ~150 Hz, and the AM of neighbouring octaves moves together up to ~200 Hz and not above
# (crossband.py), so what lies above is not one gain for the whole channel (FINDINGS 2026-11-18).
GAINNOISE_SHAPE = dict(rate_freqs=[1.0, 150.0, 300.0, 600.0], rate_psd=[1.0, 1.0, 0.25, 0.02])


def centres(rates):
    return np.array([np.sqrt(a * b) for a, b in rates])


def widths(rates):
    return np.array([b - a for a, b in rates])


def mean_pm(sig, octs=TIMING_OCTS):
    """Timing power per rate band (us^2), mean over channels and the cleanest octaves."""
    return np.nanmean([sig["pm"][fc].mean(axis=0) for fc in octs], axis=0)


def fine_timing(sig):
    """The fine spectrum of the whole timing (signature's timing_psd: what the warp took out plus what
    it left): frequencies, the spectrum smoothed over a quarter octave, and the spectrum as measured."""
    f, P = np.asarray(sig["timing_psd"]["f"]), np.asarray(sig["timing_psd"]["psd"])
    c = np.concatenate([[0.0], np.cumsum(P)])
    lo = np.searchsorted(f, f * 2 ** (-1 / 8), side="left")
    hi = np.maximum(np.searchsorted(f, f * 2 ** (1 / 8), side="right"), lo + 1)
    return f, (c[hi] - c[lo]) / (hi - lo), P


def split_lines(prof: dict, min_us: float = 0.5, min_ratio: float = 20.0, max_width_hz: float = 0.45) -> list[dict]:
    """Move the narrow peaks of the transport's spectrum (the pinch roller, the capstan, the motor and
    their harmonics) out of the table into `lines`: sines of constant level. As a narrow peak in a noise
    spectrum each would fade in and out over tens of seconds; on the tape they hold steady (FINDINGS,
    2026-11-18). A peak counts as a line if it stands `min_ratio` times above the spectrum around it,
    is at most `max_width_hz` wide and holds `min_us` RMS; the table keeps the level around it."""
    tr = prof["transport"]
    f, P = np.array(tr["freqs"]), np.array(tr["psd_us2_per_hz"])
    df = f[1] - f[0]
    base = np.empty_like(P)
    for i in range(len(f)):
        h = max(20, int(0.12 * f[i] / df))
        base[i] = np.median(P[max(0, i - h): i + h + 1])
    hot = (P > min_ratio * base) & (f >= 0.8) & (f <= tr["crossover_hz"] + 5)
    lines, i = list(tr.get("lines", [])), 0
    while i < len(f):
        if not hot[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(f) and hot[j + 1]:
            j += 1
        lo, hi = max(i - 2, 0), min(j + 2, len(f) - 1)  # the peak's skirts belong to it
        excess = np.clip(P[lo:hi + 1] - base[lo:hi + 1], 0, None)
        us = float(np.sqrt(excess.sum() * df))
        if us >= min_us and f[hi] - f[lo] <= max_width_hz:
            lines.append(dict(hz=float((f[lo:hi + 1] * excess).sum() / excess.sum()), us=us))
            P[lo:hi + 1] = np.minimum(P[lo:hi + 1], base[lo:hi + 1])
        i = j + 1
    tr["psd_us2_per_hz"] = P.tolist()
    tr["lines"] = merge_close(lines)
    return tr["lines"]


def merge_close(lines: list[dict], within_hz: float = 0.12) -> list[dict]:
    """Lines closer together than the measurement can tell apart are one line: two sines that close
    would beat, which is the fading the lines are there to avoid."""
    out: list[dict] = []
    for line in sorted(lines, key=lambda l: l["hz"]):
        if out and line["hz"] - out[-1]["hz"] < within_hz:
            a, b = out[-1]["us"] ** 2, line["us"] ** 2
            out[-1] = dict(hz=(out[-1]["hz"] * a + line["hz"] * b) / (a + b), us=float(np.sqrt(a + b)))
        else:
            out.append(dict(line))
    return out


def table_power(freqs, psd, lo, hi) -> float:
    """The power a table (a spectrum on a log-frequency grid, as the emulator reads it: straight lines
    between its points in log-log, nothing outside) holds between lo and hi."""
    freqs, psd = np.asarray(freqs, float), np.maximum(np.asarray(psd, float), 1e-30)
    a, b = max(lo, freqs[0]), min(hi, freqs[-1])
    if b <= a:
        return 0.0
    g = np.geomspace(a, b, 200)
    return float(np.trapezoid(np.exp(np.interp(np.log(g), np.log(freqs), np.log(psd))), g))


def rate_share(freqs, psd, lo, hi):
    """Share of a unit-variance process's power between lo and hi Hz, for a log-log rate table."""
    def power(a, b):
        a, b = max(a, freqs[0]), min(b, freqs[-1])
        if b <= a:
            return 0.0
        f = np.geomspace(a, b, 2000)
        return float(np.trapezoid(np.exp(np.interp(np.log(f), np.log(freqs), np.log(np.maximum(psd, 1e-30)))), f))
    return power(lo, hi) / power(freqs[0], freqs[-1])


def add_gain_noise(prof: dict):
    """Start the profile's gain noise at nothing; update() fills it in from the first comparison."""
    prof["gain_noise"] = dict(GAINNOISE_SHAPE, depth_freqs=[1000.0, 4000.0], depth_L=[1e-4, 1e-4], depth_R=[1e-4, 1e-4],
                              note="fast wobble of each channel's level as a whole (track-edge contact): RMS fraction "
                                   "per channel, the same at every frequency")


# ---------------------------------------------------------------- initial profile
def init_profile(tid: str, name: str, tape_sig: dict, base: dict | None = None) -> dict:
    """A starting profile from the song's own measurements. With `base` (a fitted profile of the same
    deck and tape, from another song): this song's response, levels, slow wobble and dropouts, and the
    base's fast jitter, flicker, gain noise, noise, tones and saturation as the starting point, which
    are closer to the end than the raw measurements are."""
    st = song_stats(tid)
    prof = dict(version=2, name=name, created=str(date.today()),
                songs=[dict(id=st["id"], title=st["title"], side=st["side"], gain_db=st["gain_db"],
                            delay_us=st["delay_us"])],
                gain_db=st["gain_db"], delay_us=st["delay_us"],
                # polarity of the capture against the song's source file, from the alignment; the
                # WM-D6C chain inverts (FINDINGS), so this is -1 with a source of the right master
                polarity=int(np.load(OUT / f"{st['id']}_aligned.npz")["polarity"]),
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
    if base is not None:
        for key in ("jitter", "flicker", "gain_noise", "hiss", "tones", "saturation"):
            if key in base:
                prof[key] = json.loads(json.dumps(base[key]))
        prof["base"] = base.get("name", "")
        return prof

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


# The bottom of the response table is left as it was first measured: nothing below 25 Hz is corrected,
# everything from 40 Hz up is. Down there the songs hold next to nothing, the tape's reading is mostly
# noise, and the engine's filter realises little of what the table says, so a correction changes
# nothing in the next round and the same step is taken again: five rounds piled 2.5 dB onto the 20 Hz
# point of a fitted profile (verify_engine.py, check 4: 4 dB worse at 20-60 Hz).
BASS_TAPER = np.clip(np.log(np.array(EQ_GRID) / 25.0) / np.log(40.0 / 25.0), 0.0, 1.0)


def smooth_response_step(d: np.ndarray) -> np.ndarray:
    """A correction to the response table, smoothed over 5/24 octave, and below 200 Hz over half an
    octave. The engine's response filter is nearly causal and cannot follow detail finer than that in
    the bass: a point-by-point correction there is never taken up, so it comes back every round and
    piles up in the table as ripple of several dB that describes nothing (found on the first profile
    fitted through the engine, FINDINGS 2026-11-18)."""
    f = np.array(EQ_GRID)
    fine = np.convolve(d, np.ones(5) / 5, mode="same")
    pad = 6
    coarse = np.convolve(np.pad(d, pad, mode="edge"), np.ones(2 * pad + 1) / (2 * pad + 1), mode="valid")
    share = np.clip(np.log2(300.0 / f) / np.log2(300.0 / 150.0), 0.0, 1.0)  # 1 below 150 Hz, 0 above 300 Hz
    return share * coarse + (1 - share) * fine


# ---------------------------------------------------------------- one correction step
def update(prof: dict, tape: dict, emu: dict) -> list[str]:
    notes = []
    a = ALPHA
    # static response and gain
    for ch in "LR":
        d_eq = np.array(tape["eq"][ch]) - np.array(emu["eq"][ch])
        d_ph = np.array(tape["phase"][ch]) - np.array(emu["phase"][ch])
        d_ph = (d_ph + np.pi) % (2 * np.pi) - np.pi
        d_eq, d_ph = smooth_response_step(d_eq) * BASS_TAPER, smooth_response_step(d_ph) * BASS_TAPER
        prof["eq"][ch] = (np.array(prof["eq"][ch]) + a * d_eq).tolist()
        prof["eq"][f"phase_{ch}"] = (np.array(prof["eq"][f"phase_{ch}"]) + a * d_ph).tolist()
        dg = tape["gain_db"][ch] - emu["gain_db"][ch]
        for target in (prof["gain_db"], prof["songs"][0]["gain_db"]):
            target[ch] += a * dg
        notes.append(f"{ch}: gain {dg:+.2f} dB, eq max |d| {np.max(np.abs(d_eq)):.2f} dB, "
                     f"phase max |d| {np.degrees(np.max(np.abs(d_ph))):.1f} deg")

    # slow transport. Two kinds of evidence, both from the timing as a whole (the alignment's delay
    # curve, which holds the slow wobble and the flutter lines, plus the little it leaves):
    #   below 3 Hz the speed deviation of the delay curve, in bands;
    #   from 3 Hz up signature's timing_psd in fine steps: the capstan's 7.5 Hz line, its harmonics and
    #   the motor's lines each get their own correction. (Octave-wide bands traded a line that was too
    #   strong against too little beside it. And until the alignment got its second stage this rule
    #   looked at the timing left after the warp, of which the first tracker had taken a share that
    #   differed between tape and emulation: the metal profile's 7.5 Hz line came out 15% low.)
    tr = prof["transport"]
    f = np.array(tr["freqs"])
    low = [k for k, (lo, hi) in enumerate(DEV_RATES) if hi <= 3]
    r_low = (np.array(tape["dev"]) / np.array(emu["dev"]))[low]
    ff, Pt, raw_t = fine_timing(tape)
    _, Pe, raw_e = fine_timing(emu)
    fine = (ff >= FINE_FROM_HZ) & (ff <= FINE_TO_HZ)
    pts_f = np.concatenate([centres(DEV_RATES)[low], ff[fine]])
    pts_r = np.clip(np.concatenate([r_low, Pt[fine] / Pe[fine]]), 0.5, 2.0) ** a
    corr = np.exp(np.interp(np.log(np.maximum(f, 0.1)), np.log(pts_f), np.log(pts_r)))
    tr["psd_us2_per_hz"] = (np.array(tr["psd_us2_per_hz"]) * corr).tolist()
    for line in tr.get("lines", []):  # the steady lines follow the same correction, at their own frequency
        line["us"] *= float(np.exp(0.5 * np.interp(np.log(line["hz"]), np.log(pts_f), np.log(pts_r))))
    n_low = len(low)
    notes.append("transport x " + " ".join(f"{v:.2f}" for v in pts_r[:n_low])
                 + f" | {FINE_FROM_HZ:g}-{FINE_TO_HZ:g} Hz in fine steps x {pts_r[n_low:].min():.2f}..{pts_r[n_low:].max():.2f}"
                 + f" (7.5 Hz line x {pts_r[n_low:][np.argmin(np.abs(ff[fine] - 7.5))]:.2f})")

    # fast jitter: total per rate band, and the common share from the L/R coherence at 8 kHz.
    # The timing read at a rate is the jitter put in (times PM_KAPPA) plus what else lands there: noise
    # and distortion, which read as timing and as AM alike. With the slow flutter out of the way
    # (align.py's second stage) that share is half and more of the reading above 200 Hz, so the table
    # is corrected by the difference between tape and emulation as a share of the jitter's own part,
    # not by the ratio of the readings (which took ten rounds to say the same).
    j = prof["jitter"]
    jf = np.array(j["freqs"])
    c = centres(RATES)
    inj = np.array([table_power(jf, j["psd_total_us2_per_hz"], lo, hi) for lo, hi in RATES])
    pm_t, pm_e = mean_pm(tape), mean_pm(emu)
    r = 1.0 + (pm_t - pm_e) / np.maximum(PM_KAPPA * inj, 1e-12)
    ok = ~np.isnan(r) & (c >= 48) & (inj > 0)
    rr = np.clip(r[ok], 0.5, 2.0) ** a
    corr = np.exp(np.interp(np.log(jf), np.log(c[ok]), np.log(rr)))
    j["psd_total_us2_per_hz"] = (np.array(j["psd_total_us2_per_hz"]) * corr).tolist()
    dcoh = np.nan_to_num(tape["pm_coh"][8000] - emu["pm_coh"][8000])
    drho = np.interp(np.log(jf), np.log(c[ok]), dcoh[ok])
    j["rho"] = np.clip(np.array(j["rho"]) + a * drho, 0, 0.99).tolist()
    split_jitter(prof)
    notes.append("jitter x " + " ".join(f"{v:.2f}" for v in rr) + " | rho " + " ".join(f"{v:.2f}" for v in j["rho"]))

    # flicker depth per octave: emu AM = kappa * injected + leakage; solve for the injected depth
    fl = prof["flicker"]
    mn = prof.get("gain_noise")
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
    # rate spectrum of the flicker, from the two top octaves (where the flicker is largest). If there
    # is next to no flicker up there (the metal tape), their AM is the timing's and says nothing about
    # the flicker's rate spectrum: leave it.
    c = centres(RATES)
    if max(new[3:]) >= 0.005:
        ratio = np.nanmean([tape["am"][fc].mean(axis=0) / emu["am"][fc].mean(axis=0) for fc in (8000, 13000)], axis=0)
        ok = ~np.isnan(ratio)
        rr = np.clip(ratio[ok], 0.25, 4) ** a
        rf = np.array(fl["rate_freqs"])
        corr = np.exp(np.interp(np.log(rf), np.log(c[ok]), np.log(rr)))
        fl["rate_psd"] = (np.array(fl["rate_psd"]) * corr).tolist()
        shape_note = " | rate shape x " + " ".join(f"{v:.2f}" for v in rr)
    else:
        shape_note = " | rate shape kept"
    notes.append("flicker depth % " + " ".join(f"{v * 100:.2f}" for v in new)
                 + " | rho " + " ".join(f"{v:.2f}" for v in fl["rho"]) + shape_note)

    # gain noise: one depth per channel, by the same solve as for the flicker, with the share of its
    # power that falls into the rate bands looked at
    if mn:
        for ch, name in enumerate("LR"):
            d = float(mn[f"depth_{name}"][0])
            am_t = am_e = share = 0.0
            for fc, bands in GAIN_EVIDENCE:
                am_t += float(np.nansum(tape["am"][fc][ch][bands]))
                am_e += float(np.nansum(emu["am"][fc][ch][bands]))
                share += sum(rate_share(mn["rate_freqs"], mn["rate_psd"], lo, hi) for lo, hi in RATES[bands])
            leak = max(am_e - AM_KAPPA * share * d ** 2, 0.0)
            target = np.sqrt(max(am_t - leak, 0.0) / (AM_KAPPA * share))
            d = float(max(d + a * (target - d), 1e-4))
            mn[f"depth_{name}"] = [d] * len(mn["depth_freqs"])
        notes.append(f"gain noise depth % L {mn['depth_L'][0] * 100:.2f} | R {mn['depth_R'][0] * 100:.2f}")
    return notes


def summary(prof):
    j, fl, tr = prof["jitter"], prof["flicker"], prof["transport"]
    integ = lambda f, P: float(np.sqrt(np.trapezoid(P, f)))
    ff = np.geomspace(j["freqs"][0], j["freqs"][-1], 400)
    P = lambda key: np.exp(np.interp(np.log(ff), np.log(j["freqs"]), np.log(np.maximum(j[key], 1e-30))))
    lines = tr.get("lines", [])
    strongest = sorted(lines, key=lambda l: -l["us"])[:3]
    line_note = (f" + {len(lines)} steady lines, {np.sqrt(sum(l['us'] ** 2 for l in lines)):.1f} us ("
                 + ", ".join(f"{l['hz']:.2f} Hz {l['us']:.2f}" for l in strongest) + ")") if lines else ""
    return (f"transport {integ(tr['freqs'], tr['psd_us2_per_hz']):.1f} us RMS{line_note}; jitter common "
            f"{integ(ff, P('psd_common_us2_per_hz')):.2f} us, per channel {integ(ff, P('psd_indep_us2_per_hz')):.2f} us; "
            f"flicker depth % at 1k..13k " + " ".join(f"{d * 100:.2f}" for d in fl["depth_total"])
            + (f"; gain noise % L {prof['gain_noise']['depth_L'][0] * 100:.2f} R {prof['gain_noise']['depth_R'][0] * 100:.2f}"
               if "gain_noise" in prof else ""))


def render_with_engine(render_bin, tid: str, prof: dict, profile_path: Path, seed: int, out: Path):
    """The emulation at tape level through korre-render, registered as <tid>emu like render_emulation's."""
    from common import decode
    from tracks import register_virtual, track
    t = track(tid)
    z = np.load(OUT / f"{t.id}_aligned.npz")
    song = next((s for s in prof["songs"] if s["id"] == t.id), None)
    gains = song["gain_db"] if song else prof["gain_db"]
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(render_bin), str(t.source_path), str(out), "--profile", str(profile_path), "--seed", str(seed),
                    "--record-gain", f"{gains['L']},{gains['R']}", "--polarity", str(int(z["polarity"])), "--bits", "24"],
                   check=True, stdout=subprocess.DEVNULL)
    register_virtual(f"{t.id}emu", t.id, out, len(decode(t.source_path)) / int(z["sr"]), f"{t.title} (emulated)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--track", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--base", help="with --init: a fitted profile of the same deck and tape (another song). The new "
                                   "profile takes this song's own response, levels, slow wobble and dropouts, and "
                                   "starts from the base's fast jitter, flicker, gain noise, noise and tones")
    ap.add_argument("--refresh-noise", action="store_true",
                    help="replace the profile's noise with the recorded-gap noise before iterating")
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--only", default=None,
                    help="comma-separated profile sections to correct, e.g. 'transport,jitter': everything else "
                         "stays as it is (to adapt a side profile's wobble depth to one stretch of tape). Sections: "
                         "eq, gain_db, songs, transport, jitter, flicker, gain (the gain noise)")
    ap.add_argument("--lines", action="store_true",
                    help="move the narrow peaks of the transport's spectrum into steady lines, if the profile has "
                         "none yet (a peak in the noise table fades in and out; the deck's lines do not)")
    ap.add_argument("--gain-noise", action="store_true",
                    help="add gain noise to the profile if it has none (it starts at nothing)")
    ap.add_argument("--engine", nargs="?", const=str(Path(__file__).resolve().parent.parent / "build" / "bin" / "korre-render"),
                    help="render with the C++ engine (korre-render) instead of emulator.py: the same model "
                         "(verify_engine.py), about ten times faster")
    ap.add_argument("--tones", choices=("song", "side"), default="song",
                    help="measure the deck's steady tones in the song's own stretch, or over the whole side "
                         "(use 'side' when the song has bass throughout)")
    args = ap.parse_args()
    CAL.mkdir(parents=True, exist_ok=True)
    path = PROFILES / f"{args.name}.json"
    tape_sig = signature(args.track)
    if args.init:
        base = json.loads(Path(args.base).read_text()) if args.base else None
        prof = init_profile(args.track, args.name, tape_sig, base)
        if base is None:
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
    if args.gain_noise and "gain_noise" not in prof:
        add_gain_noise(prof)
        path.write_text(json.dumps(prof, separators=(",", ":")))
    if args.lines and not prof["transport"].get("lines"):
        found = split_lines(prof)
        path.write_text(json.dumps(prof, separators=(",", ":")))
        print("steady lines taken out of the transport's table: "
              + ", ".join(f"{l['hz']:.2f} Hz {l['us']:.2f} us" for l in found), flush=True)
    hist_path = CAL / f"{args.track}_history.json"
    history = json.loads(hist_path.read_text()) if hist_path.exists() and not args.init else []
    emu_id = f"{args.track}emu"
    for it in range(args.iters):
        if args.engine:
            render_with_engine(args.engine, args.track, prof, path, args.seed, CAL / f"{emu_id}.flac")
        else:
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
            if "gain" not in keep and "gain_noise" in before:  # "gain" names the gain noise
                prof["gain_noise"] = before["gain_noise"]
            notes = [n for n in notes if any(n.startswith(k) for k in keep)] + [f"(only {args.only} corrected)"]
        prof["created"] = str(date.today())
        path.write_text(json.dumps(prof, separators=(",", ":")))
        history.append(dict(iteration=len(history) + 1, notes=notes, summary=summary(prof)))
        hist_path.write_text(json.dumps(history, indent=1))
        print("  corrections: " + "\n               ".join(notes))
        print(f"  profile now: {summary(prof)}", flush=True)


if __name__ == "__main__":
    main()
