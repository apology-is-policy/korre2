"""Align a song's digital source with its tape capture.

  1. coarse offset of the song inside the tape capture
  2. delay tracking along the whole song (GCC-PHAT on short windows) -> how the
     tape's timeline drifts and wobbles against the source: speed error, wow, flutter
  3. warp the tape onto the source timeline (windowed-sinc interpolation), so the two
     line up sample for sample at the source's rate

    python align.py B3

Writes out/<id>_aligned.npz (source, warped tape, delay curve) for measure.py.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy import signal

from common import decode
from tracks import track

PAD = 8.0  # seconds of extra tape read on each side of the track boundaries
# Polarity and delay tracking look only at this band. Below ~200 Hz the tape chain turns the
# phase by 90-300 degrees (static, the same in every song), so a full-band window match fails
# on bass-heavy songs even when the alignment is right.
TRACK_BAND = (200.0, 8000.0)
OUT = Path(__file__).resolve().parent / "out"


def mono(x):
    return x.astype(np.float64).mean(axis=1)


def track_band(x, sr):
    sos = signal.butter(4, [TRACK_BAND[0], min(TRACK_BAND[1], 0.45 * sr)], "bandpass", fs=sr, output="sos")
    return signal.sosfiltfilt(sos, x)


def coarse_offset(src: np.ndarray, tape: np.ndarray, sr: int, max_start_s: float, dec: int = 10) -> int:
    """Tape index where the source starts, from a 20 s excerpt (robust to speed drift).

    Only offsets in [-5 s, max_start_s] are considered: the tape excerpt starts PAD seconds
    before the song's gap-detected start, and an unrestricted search can lock onto a
    repeated chorus further in.
    """
    s = signal.decimate(src[int(5 * sr):int(25 * sr)], dec, ftype="fir", zero_phase=True)
    t = signal.decimate(tape, dec, ftype="fir", zero_phase=True)
    n = 1 << int(np.ceil(np.log2(len(s) + len(t))))
    cc = np.fft.irfft(np.fft.rfft(t, n) * np.conj(np.fft.rfft(s, n)), n)[: len(t) - len(s)]
    lo = 0  # tape index of excerpt start relative to source 5 s point
    hi = min(len(cc), int((max_start_s + 5) * sr / dec))
    k = lo + int(np.argmax(np.abs(cc[lo:hi])))  # abs: polarity may be inverted
    return k * dec - int(5 * sr)


def refine_start(src: np.ndarray, tape: np.ndarray, sr: int, start: int, span_s: float = 4.0,
                 search_s: float = 0.03) -> int:
    """Pin the tape index of source sample 0 with a short excerpt from the first seconds of music.

    coarse_offset matches seconds 5-25, so with a speed difference of 0.02% its answer is ~3 ms off at
    the start, outside the tracker's search range: the tracker then needs many seconds to lock on, and
    the stretch before that is misaligned (seen on the metal capture; the chrome's 0.013% just fitted)."""
    env = np.abs(src)
    i0 = int(np.argmax(env > 0.05 * np.percentile(env, 99.9)))
    n, L = int(span_s * sr), int(search_s * sr)
    a = start + i0 - L
    if a < 0 or a + n + 2 * L > len(tape) or i0 + n > len(src):
        return start
    s, t = src[i0:i0 + n], tape[a:a + n + 2 * L]
    nfft = 1 << int(np.ceil(np.log2(len(t) + n)))
    cc = np.fft.irfft(np.fft.rfft(t, nfft) * np.conj(np.fft.rfft(s, nfft)), nfft)[: 2 * L + 1]
    return start + int(np.argmax(np.abs(cc))) - L  # abs: polarity is decided afterwards


def choose_polarity(src: np.ndarray, tape: np.ndarray, sr: int, start: int) -> tuple[int, dict]:
    """Track the first 40 s with both polarities; keep the one whose windows match better."""
    s = src[: min(len(src), int(40 * sr))]
    scores = {}
    for pol in (1, -1):
        _, _, q = track_delay(s, tape * pol, sr, start, hop=4096, search=256)
        scores[pol] = float(np.median(q)) if len(q) else -1.0
    return max(scores, key=scores.get), scores


def track_delay(src, tape, sr, start, win=4096, hop=1024, search=64, fmin=200, fmax=8000):
    """Follow tape-index-minus-source-index along the song.

    Returns (centers, delay, quality): window centres in source samples, fractional delay
    in samples, and the normalised correlation of the matched windows (NaN-free; low
    quality marks unreliable windows).
    """
    nfft = 1 << int(np.ceil(np.log2(2 * win + 2 * search)))
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    band = (freqs >= fmin) & (freqs <= fmax)
    w = np.hanning(win)
    pred = float(start)
    centers, delays, quality = [], [], []
    for c in range(win // 2, len(src) - win // 2, hop):
        s = src[c - win // 2: c + win // 2] * w
        t0 = c - win // 2 + int(round(pred)) - search
        if t0 < 0 or t0 + win + 2 * search > len(tape):
            continue
        t = tape[t0: t0 + win + 2 * search]
        S, T = np.fft.rfft(s, nfft), np.fft.rfft(t, nfft)
        R = T * np.conj(S)
        R /= np.maximum(np.abs(R), 1e-15)
        R[~band] = 0
        cc = np.fft.irfft(R, nfft)[: 2 * search + 1]
        k = int(np.argmax(cc))
        frac = 0.0
        if 0 < k < 2 * search:
            a, b, d = cc[k - 1], cc[k], cc[k + 1]
            den = a - 2 * b + d
            frac = 0.5 * (a - d) / den if den else 0.0
        seg = t[k: k + win] * w
        q = float(np.dot(s, seg) / (np.linalg.norm(s) * np.linalg.norm(seg) + 1e-20))
        delay = (t0 + k + frac) - (c - win // 2)
        centers.append(c)
        delays.append(delay)
        quality.append(q)
        if q > 0.5:
            pred = delay
    return np.array(centers), np.array(delays), np.array(quality)


def clean_curve(centers, delays, quality, min_q=0.6, max_jump=1.0):
    """Drop weak windows and gross outliers (> max_jump samples off a 9-point median), lightly smooth.

    The residual spread is heavy-tailed (real wobble + estimator noise), so a sigma-based
    cut would throw away genuine flutter; only gross mis-picks are removed here.
    """
    ok = quality > min_q
    if ok.sum() < 50:
        raise SystemExit(f"alignment failed: only {ok.sum()} of {len(quality)} windows matched "
                         f"(median match {np.median(quality):.2f}). Wrong source version or master?")
    c, d = centers[ok], delays[ok]
    med = signal.medfilt(d, 9)
    keep = np.abs(d - med) < max_jump
    c, d = c[keep], d[keep]
    d = signal.savgol_filter(d, 7, 2)
    return c, d, ok.mean(), keep.mean()


def warp(x: np.ndarray, pos: np.ndarray, taps: int = 48, beta: float = 9.0,
         cutoff: float = 0.95) -> np.ndarray:
    """Sample x (frames, ch) at fractional positions `pos` with a Kaiser-windowed sinc.
    Positions outside the signal are held at its first / last sample."""
    pos = np.clip(pos, 0, len(x) - 1)
    half = taps // 2
    ks = np.arange(-half + 1, half + 1)
    out = np.zeros((len(pos), x.shape[1]))
    i0 = np.floor(pos).astype(np.int64)
    fr = pos - i0
    xp = np.pad(x.astype(np.float64), ((half, half), (0, 0)))
    for a in range(0, len(pos), 1 << 15):
        b = min(a + (1 << 15), len(pos))
        dist = fr[a:b, None] - ks[None, :]
        win = np.i0(beta * np.sqrt(np.clip(1 - (dist / half) ** 2, 0, 1))) / np.i0(beta)
        h = cutoff * np.sinc(cutoff * dist) * win
        h /= h.sum(axis=1, keepdims=True)
        idx = i0[a:b, None] + ks[None, :] + half
        out[a:b] = np.einsum("mt,mtc->mc", h, xp[idx])
    return out


def wow_flutter(c, d, sr, hop):
    """Speed deviation (%) from the delay curve, after removing the constant speed error."""
    t = c / sr
    slope, icpt = np.polyfit(t, d, 1)  # samples of delay per second
    speed_err = slope / sr * 100  # % : positive = tape timeline longer = playback slower
    resid = d - (slope * t + icpt)
    # resample the residual delay onto a uniform grid, differentiate -> speed deviation
    fs = sr / hop
    tu = np.arange(t[0], t[-1], 1 / fs)
    ru = np.interp(tu, t, resid)
    dev = np.gradient(ru, 1 / fs) / sr * 100  # % speed deviation
    sos = signal.butter(2, 0.3, "highpass", fs=fs, output="sos")
    dev = signal.sosfiltfilt(sos, dev)
    f, P = signal.welch(dev, fs, nperseg=min(len(dev), 1024))
    return speed_err, resid / sr * 1e6, tu, dev, f, P


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("track")
    ap.add_argument("--source", help="override data/sources/<id>.flac")
    args = ap.parse_args()
    t = track(args.track)
    src_path = args.source or t.source_path

    src = decode(src_path).astype(np.float64)
    import json, subprocess
    sr = int(json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate",
                                        "-of", "json", str(src_path)], capture_output=True, text=True,
                                       check=True).stdout)["streams"][0]["sample_rate"])
    tape = decode(t.path, max(0.0, t.start - PAD), t.end + PAD, sr=sr).astype(np.float64)
    print(f"{t.id} {t.title or ''}: source {len(src) / sr:.2f} s @ {sr} Hz, tape excerpt {len(tape) / sr:.2f} s")

    start = coarse_offset(mono(src), mono(tape), sr, max_start_s=2 * PAD + 15)
    print(f"coarse: source starts {start / sr:.3f} s into the tape excerpt")
    ms, mt = track_band(mono(src), sr), track_band(mono(tape), sr)
    fine = refine_start(ms, mt, sr, start)
    if fine != start:
        print(f"start refined by {(fine - start) / sr * 1e3:+.2f} ms from the first seconds of the song")
        start = fine
    pol, scores = choose_polarity(ms, mt, sr, start)
    tape *= pol
    print(f"polarity relative to this source file: {'inverted (corrected)' if pol < 0 else 'same'} "
          f"(window match +1: {scores[1]:.2f}, -1: {scores[-1]:.2f})")

    hop = 1024
    centers, delays, quality = track_delay(ms, mt * pol, sr, start, hop=hop, search=128,
                                           fmin=TRACK_BAND[0], fmax=TRACK_BAND[1])
    c, d, frac_q, frac_keep = clean_curve(centers, delays, quality)
    print(f"delay tracking: {len(centers)} windows, {frac_q * 100:.0f}% reliable, "
          f"{frac_keep * 100:.0f}% of those kept after outlier rejection")
    holes = np.diff(c) / sr
    steps = np.abs(np.diff(d)) / sr * 1e6
    print(f"curve check: longest stretch without a tracked window {holes.max():.2f} s, "
          f"largest step between neighbours {steps.max():.0f} us"
          + ("  <- WARNING: the tracker lost the signal somewhere" if holes.max() > 0.5 or steps.max() > 100 else ""))

    speed_err, resid_us, tu, dev, f, P = wow_flutter(c, d, sr, hop)
    print(f"\nspeed: tape timeline {'longer' if speed_err > 0 else 'shorter'} than source by "
          f"{abs(speed_err):.3f}% (= playback {'slower' if speed_err > 0 else 'faster'} than recording)")
    print(f"timing wander after removing that: {resid_us.min():+.0f}..{resid_us.max():+.0f} us "
          f"(std {resid_us.std():.0f} us)")
    for lo, hi, name in [(0.3, 4, "wow    0.3-4 Hz"), (4, 20, "flutter  4-20 Hz"), (0.3, 20, "total  0.3-20 Hz")]:
        m = (f >= lo) & (f < hi)
        rms = np.sqrt(np.trapezoid(P[m], f[m]))
        print(f"  speed deviation {name}: {rms:.3f}% RMS (unweighted)")
    print(f"  peak speed deviation: {np.percentile(np.abs(dev), 99):.3f}% (99th percentile of |dev|)")
    m = (f >= 0.3) & (f <= 20)
    pk, _ = signal.find_peaks(P[m], prominence=P[m].max() * 0.05)
    top = sorted(pk, key=lambda k: -P[m][k])[:6]
    print("  strongest periodicities: " + ", ".join(f"{f[m][k]:.2f} Hz" for k in sorted(top, key=lambda k: f[m][k])))

    # warp tape onto the source timeline
    n = np.arange(len(src))
    dly = np.interp(n, c, d)  # constant extrapolation at the ends
    aligned = warp(tape, n + dly)
    OUT.mkdir(exist_ok=True)
    np.savez(OUT / f"{t.id}_aligned.npz", sr=sr, src=src.astype(np.float32), tape=aligned.astype(np.float32),
             centers=c, delay=d, dev_t=tu, dev=dev, polarity=pol)
    print(f"\nwrote {OUT / f'{t.id}_aligned.npz'}")


if __name__ == "__main__":
    main()
