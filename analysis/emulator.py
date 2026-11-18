"""The reference tape model (v0.5): applies a measured profile (calibrate.py) to audio, offline.

Signal chain, in physical order:
  record gain -> saturation: a tiny cubic, then treble saturation (cubic on the pre-emphasised signal)
  -> static response per channel: measured magnitude AND phase (the phase holds each channel's
     delay and the large low-frequency rotation of the chain)
  -> timing, one warp per channel:
       transport   slow common wobble with the mechanical line spectrum (capstan, motor, pinch roller)
       differential  slow L-R wobble (pinch roller tilting the tape)
       jitter      fast timing (scrape flutter), 20 Hz .. 3 kHz rates, a common part and a part
                   independent per channel
  -> amplitude flicker (head contact): depth per frequency, common + independent parts
     and gain noise: a fast wobble of each channel's level as a whole (up to a few hundred Hz), with
     its own depth per channel (the left track runs along the tape's edge and has more of it)
  -> dropouts -> background: noise per channel + the deck's faint steady tones -> polarity

v0.1 modelled most of the fast modulation as amplitude flicker; with a better alignment it turned
out to be mostly timing (FINDINGS, 2026-11-16 v0.2). Profiles from v0.1 are not supported.

Every random process is generated up front from the seed, so renders with different ingredient
sets share exactly the same wobble, jitter, flicker and hiss.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

from align import warp

INGREDIENTS = ("eq", "transport", "differential", "jitter", "flicker", "dropouts", "hiss", "saturation")


def synth_from_psd(freqs, psd, fs, n, rng, log_interp=False):
    """Gaussian process of length n at rate fs with the given one-sided PSD (units^2/Hz)."""
    k = np.fft.rfftfreq(n, 1 / fs)
    if log_interp:  # table on a log-frequency grid: interpolate log PSD vs log f, zero outside
        freqs, psd = np.asarray(freqs, float), np.maximum(np.asarray(psd, float), 1e-30)
        P = np.exp(np.interp(np.log(np.maximum(k, 1e-9)), np.log(freqs), np.log(psd)))
        P[(k < freqs[0]) | (k > freqs[-1])] = 0.0
    else:
        P = np.interp(k, freqs, psd, left=0.0, right=0.0)
    P[0] = 0.0
    amp = np.sqrt(P * fs * n / 2)
    X = amp * (rng.standard_normal(len(k)) + 1j * rng.standard_normal(len(k))) / np.sqrt(2)
    return np.fft.irfft(X, n)


def upsample_to(x, n_out):
    """Band-limited resampling of a control signal to n_out samples."""
    return signal.resample(x, n_out)


def measured_response(freqs, db_vals, phase, f):
    """Response on frequencies f from a measured magnitude (dB) and phase (rad) table on a log grid.
    Below the table: magnitude keeps the bottom octave's slope, phase its log-frequency slope.
    Above it: magnitude held, phase continued linearly in frequency (a pure delay)."""
    lf = np.log(np.maximum(f, 1e-3))
    lg = np.log(freqs)
    mag_db = np.interp(lf, lg, db_vals)
    ph = np.interp(lf, lg, phase)
    lo = f < freqs[0]
    oct_lo = np.log2(freqs[0] / np.maximum(f[lo], 1e-3))
    mag_db[lo] = db_vals[0] - (db_vals[12] - db_vals[0]) / np.log2(freqs[12] / freqs[0]) * oct_lo
    ph[lo] = phase[0] - (phase[12] - phase[0]) / np.log2(freqs[12] / freqs[0]) * oct_lo
    hi = f > freqs[-1]
    slope = (phase[-1] - phase[-7]) / (freqs[-1] - freqs[-7])
    ph[hi] = phase[-1] + slope * (f[hi] - freqs[-1])
    H = 10 ** (mag_db / 20) * np.exp(1j * ph)
    H[f == 0] = np.abs(H[f == 0])  # a real filter: DC bin is real
    return H


def shelf(t1, gain_db, sr):
    """First-order high shelf (b, a): unity at DC, +gain_db far above the corner 1/(2 pi t1)."""
    t2 = t1 / 10 ** (gain_db / 20)
    return signal.bilinear([t1, 1], [t2, 1], fs=sr)


def hf_stage(x, sr, tau, gain_db, c):
    """Treble saturation: cubic on the pre-emphasised signal, then the exact inverse shelf, so quiet
    signals pass unchanged and loud treble dips a little (satfit.py)."""
    b, a = shelf(tau, gain_db, sr)
    u = signal.lfilter(b, a, x, axis=0)
    u = u - c * u ** 3
    return signal.lfilter(a, b, u, axis=0)  # inverse shelf (minimum phase, so stable)


def depth_curve(table, f):
    """Flicker depth (fraction RMS) at frequencies f from a per-band table, log-log interpolated;
    below the table it falls with the slope of the bottom two points, above it is held."""
    fr = np.asarray(table["freqs"], float)
    d = np.maximum(np.asarray(table["rms"], float), 1e-6)
    lf = np.log(np.maximum(f, 1.0))
    out = np.exp(np.interp(lf, np.log(fr), np.log(d)))
    lo = f < fr[0]
    slope = np.log(d[1] / d[0]) / np.log(fr[1] / fr[0])
    out[lo] = d[0] * (np.maximum(f[lo], 1.0) / fr[0]) ** max(slope, 0.0)
    return out


def held_depth(freqs, rms, f):
    """Depth (fraction RMS) at frequencies f from a per-band table, log-log interpolated and held at
    both ends: the gain noise is about as deep in the bass as in the mids (levelsplit.py)."""
    d = np.maximum(np.asarray(rms, float), 1e-6)
    return np.exp(np.interp(np.log(np.maximum(f, 1.0)), np.log(np.asarray(freqs, float)), np.log(d)))


class Emulator:
    def __init__(self, profile: dict, sr: int, n: int, seed: int = 1, record_gain_db: dict | None = None,
                 polarity: int = 1):
        if profile.get("version", 1) < 2:
            raise ValueError("v0.1 profile: refit it with calibrate.py --init")
        self.p, self.sr, self.n, self.polarity = profile, sr, n, polarity
        self.gain_db = record_gain_db or profile["gain_db"]
        rng = np.random.default_rng(seed)
        p = profile

        # ---- slow timing (microseconds): transport with its line spectrum, faded out at the crossover
        tr, df = p["transport"], p["differential"]
        fx = tr["crossover_hz"]
        fs_t = tr["fs"]
        n_t = int(np.ceil(n / sr * fs_t)) + 1
        tf, tP = np.array(tr["freqs"]), np.array(tr["psd_us2_per_hz"])
        tP = tP * np.clip((fx + 5 - tf) / 10, 0, 1)
        self.transport_us = upsample_to(synth_from_psd(tf, tP, fs_t, n_t, rng), n)
        self.diff_us = upsample_to(synth_from_psd(df["freqs"], df["psd_us2_per_hz"], fs_t, n_t, rng), n)

        # ---- fast timing: common and per-channel jitter, synthesised at the audio rate
        jt = p["jitter"]
        self.jitter_common_us = synth_from_psd(jt["freqs"], jt["psd_common_us2_per_hz"], sr, n, rng, log_interp=True)
        self.jitter_indep_us = [synth_from_psd(jt["freqs"], jt["psd_indep_us2_per_hz"], sr, n, rng, log_interp=True)
                                for _ in range(2)]

        # ---- amplitude flicker: unit-RMS processes with the measured rate spectrum
        fl = p["flicker"]
        def unit(rng_):
            v = synth_from_psd(fl["rate_freqs"], fl["rate_psd"], sr, n, rng_, log_interp=True)
            return v / (np.std(v) + 1e-20)
        self.flicker_common = unit(rng)
        self.flicker_indep = [unit(rng) for _ in range(2)]

        # ---- dropouts: Poisson events drawn from the measured ones
        dr = p["dropouts"]
        env = np.ones((n, 2))
        if dr["events"]:
            n_events = rng.poisson(dr["rate_per_min"] * n / sr / 60)
            for _ in range(n_events):
                e = dr["events"][rng.integers(len(dr["events"]))]
                start = int(rng.integers(0, n))
                length = max(int(e["dur_ms"] / 1e3 * sr), 64)
                shape = 1 - (1 - 10 ** (e["depth_db"] / 20)) * np.sin(np.pi * np.arange(length) / length) ** 2
                chans = (0, 1) if e["both"] else (int(rng.integers(2)),)
                seg = slice(start, min(start + length, n))
                for c in chans:
                    env[seg, c] *= shape[: seg.stop - seg.start]
        self.dropout_env = env

        # ---- hiss per channel
        hz = p["hiss"]
        self.hiss = np.stack([synth_from_psd(hz["freqs"], hz[c], sr, n, rng) for c in ("L", "R")], axis=1)

        # ---- steady deck tones (capstan and motor rates, mains hum): part of the background
        tt = np.arange(n) / sr
        for tone in p.get("tones", []):
            ph0 = rng.uniform(0, 2 * np.pi)
            for c, (key, dph) in enumerate((("L_dbfs", np.radians(tone["phase_deg"])), ("R_dbfs", 0.0))):
                self.hiss[:, c] += np.sqrt(2) * 10 ** (tone[key] / 20) * np.cos(2 * np.pi * tone["hz"] * tt + ph0 + dph)

        # ---- gain noise: unit-RMS processes, one per channel (drawn last, so that a seed's other
        # signals are the same with and without it)
        self.gainnoise = None
        mn = p.get("gain_noise")
        if mn:
            def unit_gn():
                v = synth_from_psd(mn["rate_freqs"], mn["rate_psd"], sr, n, rng, log_interp=True)
                return v / (np.std(v) + 1e-20)
            self.gainnoise = [unit_gn() for _ in range(2)]

    # ------------------------------------------------------------------
    def process(self, x: np.ndarray, ingredients=INGREDIENTS) -> np.ndarray:
        p, sr, n = self.p, self.sr, self.n
        assert len(x) == n
        y = x.astype(np.float64) * np.array([10 ** (self.gain_db[c] / 20) for c in "LR"])

        if "saturation" in ingredients and p["saturation"]["ref_rms_dbfs"] is not None:
            sigma = 10 ** (p["saturation"]["ref_rms_dbfs"] / 20)
            c3 = 10 ** (p["saturation"]["cubic_rel_db"] / 20) / (np.sqrt(15) * sigma ** 2)
            y = y - c3 * y ** 3
        hf = p["saturation"].get("hf")
        if "saturation" in ingredients and hf:
            y = hf_stage(y, sr, hf["tau_s"], hf["shelf_db"], hf["c"])

        nfft = 1 << int(np.ceil(np.log2(n + 8192)))
        f_full = np.fft.rfftfreq(nfft, 1 / sr)
        if "eq" in ingredients:
            mean_delay = (p["delay_us"]["L"] + p["delay_us"]["R"]) / 2
            freqs = np.array(p["eq"]["freqs"])
            for c, name in enumerate("LR"):
                # measured phase holds each channel's delay; remove the common part so the output
                # stays aligned with the input
                H = measured_response(freqs, np.array(p["eq"][name]), np.array(p["eq"][f"phase_{name}"]), f_full)
                H *= np.exp(2j * np.pi * f_full * mean_delay * 1e-6)
                y[:, c] = np.fft.irfft(np.fft.rfft(y[:, c], nfft) * H, nfft)[:n]

        common = np.zeros(n)
        if "transport" in ingredients:
            common += self.transport_us
        if "jitter" in ingredients:
            common += self.jitter_common_us
        for c, sign in ((0, 0.5), (1, -0.5)):
            d = common.copy()
            if "differential" in ingredients:
                d += sign * self.diff_us
            if "jitter" in ingredients:
                d += self.jitter_indep_us[c]
            if d.any():
                pos = np.arange(n, dtype=np.float64) - d * 1e-6 * sr
                y[:, c] = warp(y[:, [c]], np.clip(pos, 0, n - 1))[:, 0]

        if "flicker" in ingredients:
            fl = p["flicker"]
            dc = depth_curve(dict(freqs=fl["depth_freqs"], rms=fl["depth_common"]), f_full)
            di = depth_curve(dict(freqs=fl["depth_freqs"], rms=fl["depth_indep"]), f_full)
            mn = p.get("gain_noise")
            for c in range(2):
                Y = np.fft.rfft(y[:, c], nfft)
                vc = np.fft.irfft(Y * dc, nfft)[:n]
                vi = np.fft.irfft(Y * di, nfft)[:n]
                out = y[:, c] - self.flicker_common * vc - self.flicker_indep[c] * vi
                if self.gainnoise is not None:
                    dm = held_depth(mn["depth_freqs"], mn["depth_L" if c == 0 else "depth_R"], f_full)
                    out = out - self.gainnoise[c] * np.fft.irfft(Y * dm, nfft)[:n]
                y[:, c] = out

        if "dropouts" in ingredients:
            y = y * self.dropout_env
        if "hiss" in ingredients:
            y = y + self.hiss
        return self.polarity * y
