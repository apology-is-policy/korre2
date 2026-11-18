"""Reference for the C++ tape engine (tape/): the engine's own definitions, written out in numpy.

emulator.py is the model. It works on a whole track at once: the static response is applied with one
FFT as long as the track, and every random signal is made in one piece. An engine that plays music as
it arrives cannot do that, so it uses
  - a filter of a third of a second for the static response (tape/src/design.cpp: response_filter),
  - a short symmetric filter for the flicker depth (flicker_filter),
  - random signals made in overlapping blocks (tape/src/noise.cpp).
This file repeats the two filter designs line by line and applies the chain with *given* control
signals, so verify_engine.py can take the wobble, jitter, flicker and noise the engine really used
(korre-render --trace) and check its output sample by sample.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

from align import warp
from emulator import INGREDIENTS, cubic_coefficients, depth_curve, held_depth, hf_stage, measured_response


def lround(x: float) -> int:
    return int(np.floor(x + 0.5))


def sizes_for(sr: float) -> dict:
    taps = 1 << int(np.ceil(np.log2(lround(0.33 * sr))))
    return dict(response_taps=taps, response_block=taps // 16, response_pre=lround(0.0116 * sr),
                flicker_half=lround(0.0029 * sr), control_step=max(1, lround(sr / 187.5)))


def response_filter(profile: dict, channel: str, sr: float) -> np.ndarray:
    """The static response of one channel as a filter; time zero is tap sizes_for(sr)['response_pre']."""
    s = sizes_for(sr)
    taps, pre = s["response_taps"], s["response_pre"]
    n = 8 * taps
    f = np.fft.rfftfreq(n, 1 / sr)
    eq = profile["eq"]
    H = measured_response(np.array(eq["freqs"]), np.array(eq[channel]), np.array(eq[f"phase_{channel}"]), f)
    mean_delay = (profile["delay_us"]["L"] + profile["delay_us"]["R"]) / 2
    H = H * np.exp(2j * np.pi * f * mean_delay * 1e-6)
    h = np.fft.irfft(H, n)
    i = np.arange(taps)
    w = np.ones(taps)
    w[:pre] = np.sin(0.5 * np.pi * (i[:pre] + 0.5) / pre) ** 2
    fall = taps // 4
    w[taps - fall:] *= np.cos(0.5 * np.pi * (np.arange(fall) + 0.5) / fall) ** 2
    return h[(i - pre) % n] * w


def flicker_filter(freqs, rms, sr: float, held: bool = False) -> np.ndarray:
    """A symmetric filter of 2 * flicker_half + 1 taps whose gain is a depth table: the flicker's
    (falling below the table), or with `held` the gain noise's (held at both ends)."""
    half = sizes_for(sr)["flicker_half"]
    n = 1 << int(np.ceil(np.log2(32 * half)))
    fgrid = np.fft.rfftfreq(n, 1 / sr)
    d = held_depth(freqs, rms, fgrid) if held else depth_curve(dict(freqs=freqs, rms=rms), fgrid)
    h = np.fft.irfft(d, n)
    i = np.arange(2 * half + 1)
    return h[(i - half) % n] * np.sin(np.pi * (i + 1) / (2 * half + 2)) ** 2


def apply(x: np.ndarray, profile: dict, sr: int, controls: dict, ingredients=INGREDIENTS, gain_db: dict | None = None,
          polarity: int = 1, output_gain_db: float = 0.0) -> np.ndarray:
    """The engine's chain on x (frames, 2) with the given control signals (one value per frame):
    transport, differential, jitter_common, jitter_left/right [microseconds], flicker_common,
    flicker_left/right, gainnoise_left/right, dropout_left/right [gain], background_left/right [added signal]."""
    p, n = profile, len(x)
    g = gain_db or p["gain_db"]
    y = x.astype(np.float64) * np.array([10 ** (g[c] / 20) for c in "LR"])

    if "saturation" in ingredients:
        if p["saturation"]["ref_rms_dbfs"] is not None:
            sigma = 10 ** (p["saturation"]["ref_rms_dbfs"] / 20)
            y = y - cubic_coefficients(p["saturation"], sigma) * y ** 3
        hf = p["saturation"].get("hf")
        if hf:
            y = hf_stage(y, sr, hf["tau_s"], hf["shelf_db"], hf["c"])

    if "eq" in ingredients:
        pre = sizes_for(sr)["response_pre"]
        for c, name in enumerate("LR"):
            y[:, c] = signal.fftconvolve(y[:, c], response_filter(p, name, sr))[pre: pre + n]

    zero = np.zeros(n)
    common = (controls["transport"] if "transport" in ingredients else zero) + \
             (controls["jitter_common"] if "jitter" in ingredients else zero)
    for c, (side, sign) in enumerate((("left", 0.5), ("right", -0.5))):
        d = common.copy()
        if "differential" in ingredients:
            d = d + sign * controls["differential"]
        if "jitter" in ingredients:
            d = d + controls[f"jitter_{side}"]
        if d.any():
            ypad = np.concatenate([np.zeros(64), y[:, c], np.zeros(64)])  # silence around the track, as in the engine
            y[:, c] = warp(ypad[:, None], np.arange(n, dtype=np.float64) + 64 - d * 1e-6 * sr)[:, 0]

    if "flicker" in ingredients:
        fl = p["flicker"]
        hc = flicker_filter(fl["depth_freqs"], fl["depth_common"], sr)
        hi = flicker_filter(fl["depth_freqs"], fl["depth_indep"], sr)
        mn = p.get("gain_noise")
        for c, side in enumerate(("left", "right")):
            base = y[:, c].copy()
            vc = signal.fftconvolve(base, hc, mode="same")
            vi = signal.fftconvolve(base, hi, mode="same")
            y[:, c] = base - controls["flicker_common"] * vc - controls[f"flicker_{side}"] * vi
            if mn:
                hm = flicker_filter(mn["depth_freqs"], mn["depth_L" if c == 0 else "depth_R"], sr, held=True)
                y[:, c] -= controls[f"gainnoise_{side}"] * signal.fftconvolve(base, hm, mode="same")

    if "dropouts" in ingredients:
        y = y * np.stack([controls["dropout_left"], controls["dropout_right"]], axis=1)
    if "hiss" in ingredients:
        y = y + np.stack([controls["background_left"], controls["background_right"]], axis=1)
    return polarity * 10 ** (output_gain_db / 20) * y
