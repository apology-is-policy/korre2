"""Fit a tape profile (JSON) from aligned songs: every parameter the emulator uses, measured.

    python fitprofile.py --name wmd6c_xlii_sideB --tracks B3
    python fitprofile.py --name wmd6c_xlii_sideA --tracks A4 A6

Writes profiles/<name>.json at the repo root. What it measures, per song, then averages:
  eq            per-channel magnitude response (power-only, i.e. not dragged down by jitter),
                1/6-octave smoothed, re 1 kHz; per-channel gain at 1 kHz; static L/R delay
  transport     PSD of the common timing wobble up to ~80 Hz: the tracked delay curve plus the
                ~6 ms timing fits, minus the null-test (estimator) floor
  differential  PSD of the L-R timing wobble, minus its null floor
  scrape        PSD of fast timing jitter (3-10 kHz band, ~1.5 ms windows), minus null
  flicker       PSD of treble amplitude flicker, converted to a spacing-loss process
                (amplitude change proportional to frequency), minus null; L/R correlation
  dropouts      broadband gain dips: rate, depths, durations, share hitting both channels
  hiss          per-channel PSD of the tape's background noise, from the recorded gaps between songs
  saturation    3rd-order level found by the Hammerstein fit (Forever Young), as a cubic
"""
from __future__ import annotations

import argparse
import json
from datetime import date

import numpy as np
from scipy import signal

from common import REPO, data_file, db, decode
from investigate import band, load
from measure import apply_H, cross_spectra, phase_delay
from residual import fit_windows
from tracks import NOISE_POOL, SIDE_FILES, recorded_gaps, track

PROFILES = REPO / "profiles"
RNG = np.random.default_rng(3)
EQ_GRID = [20 * 2 ** (k / 24) for k in range(0, 240) if 20 * 2 ** (k / 24) <= 20000]
TRANSPORT_FMAX = 45.0  # above this, the fast (scrape) estimate takes over
CUBIC_REL_DB, CUBIC_SONG = -43.0, "A6"  # Hammerstein 3rd order, loud blocks, Forever Young


def psd_minus_null(x, x_null, fs, nper):
    f, P = signal.welch(x, fs, nperseg=min(nper, len(x)))
    _, P0 = signal.welch(x_null, fs, nperseg=min(nper, len(x_null)))
    P0 = np.convolve(P0, np.ones(15) / 15, mode="same")  # smooth the floor so its random dips leave no false residue
    # keep only components clearly above the floor (>2x in power); below that it's estimator noise
    return f, np.where(P > 2 * P0, P - P0, 0.0), P, P0


EQ_TOP_HZ = 18000.0  # the static response is measured up to here and extrapolated above
NOISE_FINE_HZ = 60.0  # below this the noise spectrum is measured with 0.5 Hz resolution
OUT = REPO / "analysis" / "out"


def recorded_noise_psd(side: str, sr: int, nper: int = 8192, keep: float = 0.6):
    """Per-channel PSD of the tape's real background noise: the silent gaps between songs, cut into
    0.5 s chunks, keeping the quietest share (so reverb tails and lead-ins drop out).
    Returns (freqs, psd[freq, channel])."""
    chunk = int(0.5 * sr)
    psds = []
    for sd in NOISE_POOL.get(side, (side,)):
        for a, b in recorded_gaps(sd):
            g = decode(data_file(SIDE_FILES[sd]), a + 0.5, b - 0.5, sr=sr).astype(np.float64)
            for i in range(len(g) // chunk):
                f, P = signal.welch(g[i * chunk:(i + 1) * chunk], sr, nperseg=nper, axis=0)
                psds.append(P)
    psds = np.array(psds)
    m = (f >= 300) & (f < 6000)
    lvl = psds[:, m].sum(axis=(1, 2))
    P = psds[lvl <= np.quantile(lvl, keep)].mean(axis=0)

    # below NOISE_FINE_HZ the 6 Hz grid is too coarse (the floor falls away under ~18 Hz): take 2 s
    # windows from the gaps of 5 s or more, median over gaps, smoothed over 2.5 Hz so the steady
    # tones (steady_tones) are not counted twice, and scaled to join the coarse spectrum
    fine = []
    for a, b in recorded_gaps(side, min_s=5.0):
        g = decode(data_file(SIDE_FILES[side]), a + 0.75, b - 0.75, sr=sr).astype(np.float64)
        ff, Pf = signal.welch(g, sr, nperseg=2 * sr, axis=0)
        fine.append(Pf)
    if not fine:
        return f, P
    Pf = signal.medfilt(np.median(fine, axis=0), kernel_size=(5, 1))
    join = (NOISE_FINE_HZ, 2 * NOISE_FINE_HZ)
    scale = (P[(f >= join[0]) & (f < join[1])].mean(axis=0)
             / Pf[(ff >= join[0]) & (ff < join[1])].mean(axis=0))
    lo, hi = ff < NOISE_FINE_HZ, f >= NOISE_FINE_HZ
    return np.concatenate((ff[lo], f[hi])), np.concatenate((Pf[lo] * scale, P[hi]))


def steady_tones(tid: str, fmin: float = 3.0, fmax: float = 130.0, rise_db: float = 10.0, whole_side: bool = False):
    """Faint steady tones the deck adds at the bottom end (capstan and motor rates, mains hum).

    From the song's stretch of the raw capture at 0.05 Hz resolution: per frequency the 10th percentile
    over 20 s segments (music comes and goes, a steady tone stays), peaks at least rise_db above the
    local median, minus tones the source itself holds at a similar level. Level and L/R phase from the
    segments with the least low-frequency music. Returns a list of dicts (hz, L_dbfs, R_dbfs, phase_deg:
    left relative to right)."""
    t = track(tid)
    sr, seg_s = 3000, 20.0
    if whole_side:
        # all the songs on the side: no single song's bass notes survive the 10th percentile, so the
        # source needn't be consulted (and bass-heavy songs can't hide the tones)
        from tracks import TRACKS
        side = [u for u in TRACKS if u.side == t.side]
        x = decode(data_file(SIDE_FILES[t.side]), side[0].start, side[-1].end - 10, sr=sr).astype(np.float64)
        src = None
    else:
        x = decode(t.path, t.start + 3, t.end - 3, sr=sr).astype(np.float64)
        src = decode(t.source_path, sr=sr).astype(np.float64)
    n = int(seg_s * sr)
    win = np.hanning(n)[:, None]
    def spectra(v):
        return np.array([np.fft.rfft(v[i:i + n] * win, axis=0) for i in range(0, len(v) - n + 1, n // 2)])
    f = np.fft.rfftfreq(n, 1 / sr)
    X = spectra(x)
    amp2 = (2 / win.sum()) ** 2 / 2  # |FFT bin|^2 -> mean square of a steady sine (amplitude^2 / 2)
    P10 = np.percentile(np.abs(X) ** 2, 10, axis=0) * amp2
    band = (f >= fmin) & (f <= fmax)
    if src is None:
        S10, gain = np.zeros_like(P10), 1.0
    else:
        S10 = np.percentile(np.abs(spectra(src)) ** 2, 10, axis=0) * amp2
        gain = np.median(P10[(f > 200) & (f < 1000)]) / np.median(S10[(f > 200) & (f < 1000)])  # tape re source
    low_power = (np.abs(X[:, band, :]) ** 2).sum(axis=(1, 2))
    quiet = low_power <= np.quantile(low_power, 0.4)
    tones = []
    L = 10 * np.log10(P10.sum(axis=1) + 1e-30)
    base = signal.medfilt(L, 301)
    peaks, _ = signal.find_peaks(np.where(band, L - base, 0), height=rise_db, distance=6)
    from scipy.ndimage import maximum_filter1d
    src_near = maximum_filter1d(S10.sum(axis=1), size=int(1.0 / (f[1] - f[0])) + 1)  # strongest within +-0.5 Hz
    for i in peaks:
        if 10 * np.log10(P10[i].sum() / (src_near[i] * gain + 1e-30)) < 10:
            continue  # the music has this tone too (flutter can move it a bin or two)
        lvl = np.median(np.abs(X[quiet, i, :]) ** 2, axis=0) * amp2
        cross = (X[quiet, i, 0] * np.conj(X[quiet, i, 1])).sum()
        tones.append(dict(hz=float(f[i]), L_dbfs=float(10 * np.log10(lvl[0])), R_dbfs=float(10 * np.log10(lvl[1])),
                          phase_deg=float(np.degrees(np.angle(cross)))))
    return [tone for tone in tones if in_recorded_silence(t.side, tone)]


def in_recorded_silence(side: str, tone: dict, margin_db: float = 10.0) -> bool:
    """True if the tone is also there in the silences recorded between songs.

    A tone the deck adds does not stop when the music does. A bass note that several songs share can
    survive the 10th percentile above and pass as steady (65.3 Hz, a C, did on side B of the metal tape:
    FINDINGS 2026-11-17), but it is gone in the gaps. The gaps are only seconds long, so the frequency
    resolution is coarse; the test is on level alone: the gap's level at the tone's frequency must come
    within margin_db of the tone's. Without recorded gaps there is nothing to test against."""
    sr = 3000
    levels = []
    for sd in NOISE_POOL.get(side, (side,)):
        for a, b in recorded_gaps(sd):
            g = decode(data_file(SIDE_FILES[sd]), a + 0.15, b - 0.15, sr=sr).astype(np.float64)
            w = np.hanning(len(g))
            ph = np.exp(-2j * np.pi * tone["hz"] * np.arange(len(g)) / sr)
            amp2 = np.abs((g * (w * ph)[:, None]).sum(axis=0) / w.sum()) ** 2 * 2  # mean square of a sine there
            levels.append(10 * np.log10(amp2 + 1e-30))
    if not levels:
        return True
    found = np.median(levels, axis=0)  # per channel, over the gaps
    return bool(np.mean(found) >= np.mean([tone["L_dbfs"], tone["R_dbfs"]]) - margin_db)


def eq_magnitude_phase(x, y, sr, fh, hiss_psd, nper=1 << 16):
    """Static response on EQ_GRID (1/6-octave bands), re 1 kHz: magnitude from power only
    ((Pyy - hiss) / Pxx, not dragged down by jitter) and phase from the cross spectrum
    (jitter and flicker are symmetric, so they don't bias it). The phase holds the per-channel
    delay and the large low-frequency rotation that a minimum-phase fit would miss.
    0.7 Hz resolution so the bottom octave has enough bins."""
    f, Pxx = signal.welch(x, sr, nperseg=nper)
    _, Pyy = signal.welch(y, sr, nperseg=nper)
    _, Pxy = signal.csd(x, y, sr, nperseg=nper)
    Pn = np.interp(f, fh, hiss_psd)
    m1 = (f >= 900) & (f <= 1100)
    ref = np.maximum(Pyy[m1] - Pn[m1], 1e-30).sum() / Pxx[m1].sum()
    grid = np.array(EQ_GRID)
    eq, ph = np.full(len(grid), np.nan), np.full(len(grid), np.nan)
    for k, fc in enumerate(grid):
        m = (f >= fc / 2 ** (1 / 12)) & (f < fc * 2 ** (1 / 12))
        if m.sum() >= 2:
            eq[k] = 10 * np.log10(max((Pyy[m] - Pn[m]).sum(), 1e-30) / Pxx[m].sum() / ref)
            ph[k] = np.angle(Pxy[m].sum())
    ok = ~np.isnan(eq)
    eq = np.interp(grid, grid[ok], eq[ok])
    ph = np.unwrap(np.interp(grid, grid[ok], np.unwrap(ph[ok])))
    i1 = int(np.argmin(np.abs(grid - 1000)))
    ph -= 2 * np.pi * np.round(ph[i1] / (2 * np.pi))  # anchor: phase at 1 kHz within +-pi
    i16 = int(np.argmin(np.abs(grid - EQ_TOP_HZ)))
    fit = (grid >= 8000) & (grid <= EQ_TOP_HZ)
    a, b = np.polyfit(grid[fit], ph[fit], 1)
    for k in range(i16 + 1, len(grid)):  # beyond that the songs have too little content to measure
        eq[k] = eq[i16] - 18 * np.log2(grid[k] / grid[i16])
        ph[k] = a * grid[k] + b
    return eq, ph, ref


def valid_interp(v, ok, clip):
    i = np.arange(len(v))
    return np.clip(np.interp(i, i[ok], v[ok]), -clip, clip)


def song_stats(tid):
    t = track(tid)
    sr, src, tape, z, trim = load(t.id)
    fh, Ph = recorded_noise_psd(t.side, sr)
    out = dict(id=tid, sr=sr, side=t.side, title=t.title, eq={}, gain_db={}, delay_us={})
    ch = {}
    for c, name in ((0, "L"), (1, "R")):
        x, y = src[:, c], tape[:, c]
        f, Pxx, Pyy, Pxy = cross_spectra(x, y, sr)
        H = Pxy / Pxx
        coh = np.abs(Pxy) ** 2 / (Pxx * Pyy)
        eq, ph, ref = eq_magnitude_phase(x, y, sr, fh, Ph[:, c])
        out["eq"][name] = eq.tolist()
        out["eq"][f"phase_{name}"] = ph.tolist()
        out["gain_db"][name] = float(10 * np.log10(ref))
        out["delay_us"][name] = float(phase_delay(f, H, coh))

        yhat = apply_H(x, f, H)
        r = y - yhat
        dy = np.gradient(yhat) * sr
        # ~6 ms timing fits (for the common transport wobble), with null
        # null fits shift the TARGET by 1 s (not the regressors), so the coefficient noise floor
        # is estimated with exactly the same regressor statistics
        *_, tau256, _, loud256, lvl256 = fit_windows(r, yhat, dy, x, 256)
        *_, tau256n, _, _, _ = fit_windows(np.roll(r, sr), yhat, dy, x, 256)
        # leftover after the ~11 ms broadband timing + gain fit, then fast fits in the treble
        *_, tau512, g512, loud512, lvl512 = fit_windows(r, yhat, dy, x, 512)
        n = len(tau512) * 512
        clean = r[:n] - np.repeat(g512, 512) * yhat[:n] - np.repeat(tau512, 512) * dy[:n]
        yb, rb, xb = band(yhat[:n], sr, 3000, 10000), band(clean, sr, 3000, 10000), band(x[:n], sr, 3000, 10000)
        dyb = np.gradient(yb) * sr
        *_, tau64, g64, loud64, lvl64 = fit_windows(rb, yb, dyb, xb, 64)
        *_, tau64n, g64n, _, _ = fit_windows(np.roll(rb, sr), yb, dyb, xb, 64)
        fb, Pb = signal.welch(xb, sr, nperseg=4096)
        f_eff = float(np.sqrt(np.sum(fb ** 2 * Pb) / np.sum(Pb)))  # RMS frequency of the treble band
        ch[name] = dict(tau256=tau256, tau256n=tau256n, lvl256=lvl256, g512=g512, lvl512=lvl512,
                        tau64=tau64, tau64n=tau64n, g64=g64, g64n=g64n, lvl64=lvl64, f_eff=f_eff)
        del x, y, yhat, r, dy, clean, yb, rb, xb, dyb

    # ---- common transport timing: tracked delay curve + residual 6 ms timing (sign: tape early by tau)
    fs_t = sr / 256
    L, R = ch["L"], ch["R"]
    ok = (L["lvl256"] > np.percentile(L["lvl256"], 40)) & (R["lvl256"] > np.percentile(R["lvl256"], 40))
    k = np.arange(len(L["tau256"]))
    centres_untrimmed = trim + k * 256 + 128
    warp_us = np.interp(centres_untrimmed, z["centers"], z["delay"]) / sr * 1e6
    warp_us -= np.polyval(np.polyfit(k, warp_us, 1), k)
    tau_c = valid_interp((L["tau256"] + R["tau256"]) / 2 * 1e6, ok, 200)
    tau_cn = valid_interp((L["tau256n"] + R["tau256n"]) / 2 * 1e6, ok, 200)
    total = warp_us - tau_c
    ft, Pt, _, _ = psd_minus_null(total, tau_cn, fs_t, 8192)
    tau_d = valid_interp((L["tau256"] - R["tau256"]) * 1e6, ok, 100)
    tau_dn = valid_interp((L["tau256n"] - R["tau256n"]) * 1e6, ok, 100)
    fd, Pd, _, _ = psd_minus_null(tau_d - tau_d.mean(), tau_dn - tau_dn.mean(), fs_t, 4096)

    # ---- fast timing (scrape flutter) and treble flicker from the 64-sample treble fits
    fs_f = sr / 64
    okf = (L["lvl64"] > np.percentile(L["lvl64"], 40)) & (R["lvl64"] > np.percentile(R["lvl64"], 40))
    scr = valid_interp((L["tau64"] + R["tau64"]) / 2 * 1e6, okf, 60)
    scr_n = valid_interp((L["tau64n"] + R["tau64n"]) / 2 * 1e6, okf, 60)
    fs_, Ps, _, _ = psd_minus_null(scr, scr_n, fs_f, 4096)
    print(f"  {tid} timing: transport raw {np.std(total):.1f} us (null {np.std(tau_cn):.1f}); "
          f"diff raw {np.std(tau_d):.2f} (null {np.std(tau_dn):.2f}); scrape raw {np.std(scr):.2f} (null {np.std(scr_n):.2f})")
    flick = {}
    for name in ("L", "R"):
        g = valid_interp(ch[name]["g64"], okf, 1.0) / ch[name]["f_eff"]  # spacing-loss coefficient, 1/Hz
        gn = valid_interp(ch[name]["g64n"], okf, 1.0) / ch[name]["f_eff"]
        flick[name] = psd_minus_null(g - g.mean(), gn - gn.mean(), fs_f, 4096)[:2] + (g,)
        print(f"  {tid} {name} flicker raw {np.std(g[okf]) * ch[name]['f_eff'] * 100:.1f}% RMS, "
              f"null {np.std(gn[okf]) * ch[name]['f_eff'] * 100:.1f}%")
    ff = flick["L"][0]
    Pf = (flick["L"][1] + flick["R"][1]) / 2
    rho = float(np.corrcoef(flick["L"][2][okf], flick["R"][2][okf])[0, 1])
    f_eff = (L["f_eff"] + R["f_eff"]) / 2

    # ---- dropouts: broadband gain dips in loud ~11 ms windows
    W, okd = 512, (L["lvl512"] > np.percentile(L["lvl512"], 50)) & (R["lvl512"] > np.percentile(R["lvl512"], 50))
    thr = 10 ** (-1 / 20) - 1
    events = []
    dip_l, dip_r = okd & (L["g512"] < thr), okd & (R["g512"] < thr)
    either = dip_l | dip_r
    i = 0
    while i < len(either):
        if either[i]:
            j = i
            while j < len(either) and either[j]:
                j += 1
            depth = 20 * np.log10(1 + max(min(L["g512"][i:j].min(), R["g512"][i:j].min()), -0.95))
            events.append(dict(depth_db=float(depth), dur_ms=float((j - i) * W / sr * 1e3),
                               both=bool(dip_l[i:j].any() and dip_r[i:j].any())))
            i = j
        else:
            i += 1
    loud_minutes = okd.sum() * W / sr / 60

    out.update(
        hiss=dict(freqs=fh.tolist(), L=Ph[:, 0].tolist(), R=Ph[:, 1].tolist()),
        transport=dict(fs=fs_t, freqs=ft.tolist(), psd_us2_per_hz=Pt.tolist()),
        differential=dict(fs=fs_t, freqs=fd.tolist(), psd_us2_per_hz=Pd.tolist()),
        scrape=dict(fs=fs_f, freqs=fs_.tolist(), psd_us2_per_hz=Ps.tolist()),
        flicker=dict(fs=fs_f, freqs=ff.tolist(), psd_per_hz=Pf.tolist(), lr_correlation=rho, f_eff_hz=f_eff,
                     rms_at_f_eff=float(np.sqrt(np.trapezoid(Pf, ff)) * f_eff)),
        dropouts=dict(rate_per_min=len(events) / loud_minutes, events=events),
    )
    if tid == CUBIC_SONG:
        lv = db(np.mean(tape[: len(tape) // 4096 * 4096].reshape(-1, 4096, 2) ** 2, axis=(1, 2)))
        out["cubic_ref_rms_dbfs"] = float(np.median(lv[lv > np.median(lv)]))
    return out


def average(stats, name):
    """Combine songs: EQ/delay/flicker/scrape/transport averaged; hiss from the side."""
    s0 = stats[0]
    prof = dict(name=name, created=str(date.today()), songs=[dict(id=s["id"], title=s["title"], side=s["side"],
                gain_db=s["gain_db"], delay_us=s["delay_us"]) for s in stats],
                eq=dict(freqs=EQ_GRID, **{k: np.mean([s["eq"][k] for s in stats], 0).tolist()
                                          for k in ("L", "R", "phase_L", "phase_R")}),
                gain_db={c: float(np.mean([s["gain_db"][c] for s in stats])) for c in "LR"},
                delay_us={c: float(np.mean([s["delay_us"][c] for s in stats])) for c in "LR"},
                hiss=s0["hiss"])
    for key, field in (("transport", "psd_us2_per_hz"), ("differential", "psd_us2_per_hz"),
                       ("scrape", "psd_us2_per_hz"), ("flicker", "psd_per_hz")):
        base = s0[key]
        grid = np.array(base["freqs"])
        P = np.mean([np.interp(grid, s[key]["freqs"], s[key][field]) for s in stats], 0)
        prof[key] = dict(base, freqs=grid.tolist(), **{field: P.tolist()})
    prof["flicker"]["lr_correlation"] = float(np.mean([s["flicker"]["lr_correlation"] for s in stats]))
    prof["flicker"]["rms_at_f_eff"] = float(np.mean([s["flicker"]["rms_at_f_eff"] for s in stats]))
    events = [e for s in stats for e in s["dropouts"]["events"]]
    prof["dropouts"] = dict(rate_per_min=float(np.mean([s["dropouts"]["rate_per_min"] for s in stats])), events=events)
    prof["transport"]["crossover_hz"] = TRANSPORT_FMAX
    cub = [s for s in stats if "cubic_ref_rms_dbfs" in s]
    ref_rms = cub[0]["cubic_ref_rms_dbfs"] if cub else None
    prof["saturation"] = dict(cubic_rel_db=CUBIC_REL_DB, ref_rms_dbfs=ref_rms, source=CUBIC_SONG)
    return prof


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--tracks", nargs="+", required=True)
    args = ap.parse_args()
    stats = [song_stats(t) for t in args.tracks]
    if all("cubic_ref_rms_dbfs" not in s for s in stats):
        try:  # the cubic reference comes from Forever Young even for other profiles
            stats_c = song_stats(CUBIC_SONG)
            stats[0]["cubic_ref_rms_dbfs"] = stats_c["cubic_ref_rms_dbfs"]
        except FileNotFoundError:
            pass
    prof = average(stats, args.name)
    PROFILES.mkdir(exist_ok=True)
    path = PROFILES / f"{args.name}.json"
    path.write_text(json.dumps(prof, separators=(",", ":")))
    tr = prof["transport"]
    rms = lambda key, field="psd_us2_per_hz": float(np.sqrt(np.trapezoid(prof[key][field], prof[key]["freqs"])))
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB) from {', '.join(args.tracks)}")
    print(f"  gain at 1 kHz L {prof['gain_db']['L']:+.2f} R {prof['gain_db']['R']:+.2f} dB; "
          f"delay L-R {prof['delay_us']['L'] - prof['delay_us']['R']:+.1f} us")
    print(f"  transport timing {rms('transport'):.1f} us RMS; differential {rms('differential'):.2f} us; "
          f"scrape {rms('scrape'):.2f} us (all, before the crossover split)")
    print(f"  flicker {prof['flicker']['rms_at_f_eff'] * 100:.1f}% RMS at {prof['flicker']['f_eff_hz']:.0f} Hz, "
          f"L/R correlation {prof['flicker']['lr_correlation']:.2f}")
    print(f"  dropouts {prof['dropouts']['rate_per_min']:.1f}/min (median depth "
          f"{np.median([e['depth_db'] for e in prof['dropouts']['events']]) if prof['dropouts']['events'] else 0:.1f} dB)")
    print(f"  saturation ref RMS {prof['saturation']['ref_rms_dbfs']}")


if __name__ == "__main__":
    main()
