"""Shared helpers for the tape-capture analysis.

Conventions used everywhere in this folder:
  * Levels are dBFS in the ffmpeg-astats convention: 10*log10(mean square), so a
    full-scale sine reads -3 dBFS.
  * Inter-channel delays are in microseconds, positive = LEFT lags RIGHT.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterator

import numpy as np
from scipy import signal

REPO = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("KORRE2_DATA", REPO / "data"))

OCTAVES = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]


def data_file(name: str) -> Path:
    """Resolve a file in the data directory (see analysis/README.md, 'Data')."""
    path = DATA / name
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - see analysis/README.md, section 'Data'")
    return path


def _ffmpeg_cmd(path, start, end, sr) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", str(path)]
    if sr:
        cmd += ["-ar", str(sr)]
    return cmd + ["-f", "f32le", "-acodec", "pcm_f32le", "-ac", "2", "-"]


def decode(path, start: float | None = None, end: float | None = None,
           sr: int | None = None) -> np.ndarray:
    """Decode [start, end] seconds of an audio file to a float32 (frames, 2) array.

    Uses ffmpeg, so anything ffmpeg reads works. `sr` resamples on the way out.
    """
    raw = subprocess.run(_ffmpeg_cmd(path, start, end, sr),
                         stdout=subprocess.PIPE, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)


def stream(path, start: float | None = None, end: float | None = None,
           sr: int | None = None, chunk_frames: int = 1 << 20) -> Iterator[np.ndarray]:
    """Like decode(), but yields float32 (frames, 2) chunks to keep memory flat."""
    proc = subprocess.Popen(_ffmpeg_cmd(path, start, end, sr), stdout=subprocess.PIPE)
    assert proc.stdout is not None
    nbytes = chunk_frames * 8
    leftover = b""
    try:
        while True:
            buf = proc.stdout.read(nbytes)
            if not buf:
                break
            buf = leftover + buf
            usable = len(buf) - len(buf) % 8
            leftover = buf[usable:]
            if usable:
                yield np.frombuffer(buf[:usable], dtype=np.float32).reshape(-1, 2)
    finally:
        proc.stdout.close()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed decoding {path}")


def db(power) -> np.ndarray | float:
    """Power (mean square) to dB."""
    return 10 * np.log10(np.maximum(power, 1e-30))


def psd(x: np.ndarray, sr: int, nperseg: int):
    """Welch PSD (density) along axis 0. Returns (freqs, P) with P shaped like x's columns."""
    return signal.welch(x, sr, window="hann", nperseg=nperseg, axis=0)


def bandpow(f: np.ndarray, P: np.ndarray, lo: float, hi: float) -> float:
    """Integrate a PSD between lo and hi Hz -> mean-square power in that band."""
    m = (f >= lo) & (f < hi)
    return float(np.trapezoid(P[m], f[m])) if m.sum() > 1 else 0.0


def octave_edges(center: float) -> tuple[float, float]:
    return center / 2**0.5, center * 2**0.5


def gcc_phat(left: np.ndarray, right: np.ndarray, sr: int, fmin: float, fmax: float,
             maxlag: int) -> tuple[float, float]:
    """Delay of `left` relative to `right` via band-limited GCC-PHAT.

    Returns (lag in samples with parabolic sub-sample refinement, correlation peak height).
    Positive lag = left lags right.
    """
    n = len(left)
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    win = np.hanning(n)
    X = np.fft.rfft(left * win, nfft)
    Y = np.fft.rfft(right * win, nfft)
    R = X * np.conj(Y)
    R /= np.maximum(np.abs(R), 1e-15)
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    R[(freqs < fmin) | (freqs > fmax)] = 0
    cc = np.fft.irfft(R, nfft)
    cc = np.concatenate((cc[-maxlag:], cc[:maxlag + 1]))
    k = int(np.argmax(cc))
    frac = 0.0
    if 0 < k < len(cc) - 1:
        a, b, c = cc[k - 1], cc[k], cc[k + 1]
        den = a - 2 * b + c
        frac = 0.5 * (a - c) / den if den else 0.0
    return k - maxlag + frac, float(cc[k])


def windowed_delays(x: np.ndarray, sr: int, win_s: float = 0.5, hop_s: float = 0.5,
                    fmin: float = 300, fmax: float = 16000, maxlag: int = 40,
                    min_level_db: float = -40):
    """GCC-PHAT inter-channel delay over sliding windows.

    Returns (times_s, delays_us, peak_heights) for windows louder than min_level_db.
    """
    n, hop = int(win_s * sr), int(hop_s * sr)
    times, delays, peaks = [], [], []
    for s in range(0, len(x) - n, hop):
        seg = x[s:s + n].astype(np.float64)
        if db(np.mean(seg**2)) < min_level_db:
            continue
        lag, peak = gcc_phat(seg[:, 0], seg[:, 1], sr, fmin, fmax, maxlag)
        times.append(s / sr)
        delays.append(lag / sr * 1e6)
        peaks.append(peak)
    return np.array(times), np.array(delays), np.array(peaks)


def fmt_t(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{seconds % 60:04.1f}"
