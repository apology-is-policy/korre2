"""Is a flutter line on the tape two lines? (run align.py first)

    python beatfit.py MB3 [B3 ...]                       the fit, for the strong lines of each tape
    python beatfit.py MB3 --apply wmd6c_metalxr_v2       write the pairs into the profile's transport.lines

A tape recorded and played on the same deck carries each of the transport's lines twice: the capstan's
(or the pinch roller's) wobble frozen into the tape at recording, and the same part's wobble again at
playback. The two are a hair apart in frequency, because a turn of the capstan did not move quite the same
length of tape both times, which is also why the tape plays a little faster or slower than it was
recorded. So they beat: over minutes the line swells to the sum of the two and fades to their difference.
Within one song that looks like a line that grows, or falls to nothing and comes back.

The line is taken from the alignment's delay curve (which holds the timing below about 19 Hz at its true
size) as a complex amplitude over time, and two steady sines are fitted to it:
  the capstan and its harmonics   apart by the speed difference between recording and playback, which
                                  the alignment has measured (the motor is speed-locked, so it is the
                                  length of tape per turn that differs)
  every other line                apart by whatever fits; of the fits that explain the line about
                                  equally well, the one with the smallest amplitudes (a song is short
                                  against a beat, and many pairs trace the same piece of it)
A pair replaces the single line when it explains clearly more of it. Its two lines carry phases, so the
emulation's beat stands where the tape's stood through the fitted song.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
from scipy import signal

from fitprofile import PROFILES
from measure import OUT
from tracks import track

MIN_US = 1.5  # weaker lines are left alone: their envelope is mostly the noise beside them
SPAN_HZ, STEP_HZ = 0.03, 0.00025  # where a line may sit around its nominal frequency
MAX_GAP_HZ = 0.03  # a pair further apart beats faster than twice a minute: two lines in their own right
BETTER_BY = 0.03  # a pair must explain this much more of the line's power than one line does
CAPSTAN_HZ = 7.53


def envelope(tid: str, hz: float):
    """The line's complex amplitude (peak, microseconds) twice a second, the times in seconds from the
    start of the source, and the speed difference between tape and source (a fraction)."""
    z = np.load(OUT / f"{track(tid).id}_aligned.npz")
    sr = int(z["sr"])
    c, d = z["centers"], z["delay"] / sr * 1e6
    fs = sr / np.median(np.diff(c))
    tt = c / sr
    speed = float(np.polyfit(tt, z["delay"] / sr, 1)[0])
    d = d - np.polyval(np.polyfit(tt, d, 3), tt)
    lp = signal.butter(3, 0.2, "lowpass", fs=fs, output="sos")
    env = 2 * signal.sosfiltfilt(lp, d * np.exp(-2j * np.pi * hz * tt))
    keep = (tt > 6) & (tt < tt[-1] - 6)
    q = int(fs // 2)
    return tt[keep][::q], env[keep][::q], speed


def fit_line(t: np.ndarray, e: np.ndarray, gaps_hz) -> dict:
    """One steady line and the best pair of lines `gap` apart (for each gap offered), by least squares."""
    offs = np.arange(-SPAN_HZ, SPAN_HZ + STEP_HZ / 2, STEP_HZ)
    basis = np.exp(2j * np.pi * offs[None, :] * t[:, None])  # (time, offset)
    n = len(t)
    total = float(np.sum(np.abs(e) ** 2))
    p = basis.conj().T @ e  # projection of the line on each candidate
    one_err = total - np.abs(p) ** 2 / n
    k1 = int(np.argmin(one_err))
    out = dict(one=dict(off=float(offs[k1]), amp=complex(p[k1] / n), explained=1 - float(one_err[k1]) / total), pairs=[])
    for g in gaps_hz:
        s = np.sum(np.exp(2j * np.pi * g * t))  # <first, second>
        pb = (basis * np.exp(2j * np.pi * g * t)[:, None]).conj().T @ e
        det = n * n - np.abs(s) ** 2
        if det < 1e-6 * n * n:
            continue
        c1 = (n * p - s * pb) / det
        c2 = (n * pb - np.conj(s) * p) / det
        err = total - np.real(np.conj(p) * c1 + np.conj(pb) * c2)
        k = int(np.argmin(err))
        out["pairs"].append(dict(off=float(offs[k]), gap=float(g), c1=complex(c1[k]), c2=complex(c2[k]),
                                 explained=1 - float(err[k]) / total))
    return out


def best_pair(fit: dict) -> dict | None:
    """Of the pairs within a point of the best, the one with the smallest amplitudes."""
    if not fit["pairs"]:
        return None
    top = max(q["explained"] for q in fit["pairs"])
    near = [q for q in fit["pairs"] if q["explained"] >= top - 0.01]
    return min(near, key=lambda q: abs(q["c1"]) + abs(q["c2"]))


def analyse(tid: str, hz: float, capstan_hz: float) -> dict:
    t, e, speed = envelope(tid, hz)
    k = round(hz / capstan_hz)
    of_capstan = k >= 1 and abs(hz - k * capstan_hz) < 0.04 and abs(speed) > 20e-6
    gaps = [speed * hz, -speed * hz] if of_capstan else [g for g in np.arange(STEP_HZ * 2, MAX_GAP_HZ, STEP_HZ)]
    fit = fit_line(t, e, gaps)
    pair = best_pair(fit)
    res = dict(hz=hz, of_capstan=of_capstan, speed=speed, seconds=float(t[-1] - t[0]), rms=float(np.sqrt(np.mean(np.abs(e) ** 2) / 2)),
               one=fit["one"], pair=pair)
    res["take_pair"] = bool(pair and res["rms"] >= MIN_US and pair["explained"] - fit["one"]["explained"] >= BETTER_BY
                            and min(abs(pair["c1"]), abs(pair["c2"])) >= 0.15 * max(abs(pair["c1"]), abs(pair["c2"])))
    return res


def as_lines(res: dict) -> list[dict]:
    """The profile's lines for a fitted line: RMS in microseconds and the sine's phase at the song's start."""
    q = res["pair"]
    f1 = res["hz"] + q["off"]
    out = []
    for f, c in ((f1, q["c1"]), (f1 + q["gap"], q["c2"])):
        out.append(dict(hz=float(f), us=float(abs(c) / np.sqrt(2)), phase=float((np.angle(c) + np.pi / 2) % (2 * np.pi))))
    return sorted(out, key=lambda l: l["hz"])


def nominal_lines(prof: dict) -> list[dict]:
    """The profile's transport lines with pairs put back together: one line per rotating part and harmonic."""
    out: list[dict] = []
    for l in sorted(prof["transport"].get("lines", []), key=lambda l: l["hz"]):
        if out and "phase" in l and out[-1].get("paired") and l["hz"] - out[-1]["hz"] < 2 * MAX_GAP_HZ:
            out[-1]["us"] = float(np.hypot(out[-1]["us"], l["us"]))
            continue
        out.append(dict(hz=l["hz"], us=l["us"], paired="phase" in l))
    return out


def describe(tid: str, res: dict) -> str:
    one, q = res["one"], res["pair"]
    text = f"{tid:7s} {res['hz']:6.2f} Hz  {res['rms']:5.2f} us RMS over {res['seconds']:.0f} s | one line explains {100 * one['explained']:5.1f}%"
    if q:
        a1, a2 = abs(q["c1"]) / np.sqrt(2), abs(q["c2"]) / np.sqrt(2)
        text += (f" | two, {abs(q['gap']) / (res['hz'] + q['off']) * 1e6:5.0f} ppm apart"
                 + (" (the speed difference)" if res["of_capstan"] else "")
                 + f": {a1:5.2f} + {a2:5.2f} us explain {100 * q['explained']:5.1f}%, beat {1 / abs(q['gap']):5.0f} s"
                 + ("  -> pair" if res["take_pair"] else ""))
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    ap.add_argument("--apply", metavar="PROFILE", help="write the pairs found on the (one) track into this profile")
    ap.add_argument("--lines", nargs="*", type=float, help="the lines to look at, Hz (default: the profile's, or 1.67 and 7.53)")
    args = ap.parse_args()
    prof = path = None
    if args.apply:
        path = PROFILES / f"{args.apply}.json"
        prof = json.loads(path.read_text())
    for tid in args.tracks:
        if args.lines:
            wanted = [dict(hz=h, us=MIN_US) for h in args.lines]
        elif prof:
            wanted = nominal_lines(prof)
        else:
            wanted = [dict(hz=1.67, us=MIN_US), dict(hz=CAPSTAN_HZ, us=MIN_US)]
        capstan = min((l["hz"] for l in wanted), key=lambda h: abs(h - CAPSTAN_HZ))
        capstan = capstan if abs(capstan - CAPSTAN_HZ) < 0.1 else CAPSTAN_HZ
        speed = envelope(tid, CAPSTAN_HZ)[2]
        print(f"== {tid}: tape against source {speed * 1e6:+.0f} ppm")
        new_lines = []
        for l in wanted:
            if l["us"] < MIN_US:
                new_lines.append(dict(hz=l["hz"], us=l["us"]))
                continue
            res = analyse(tid, l["hz"], capstan)
            print("   " + describe(tid, res), flush=True)
            new_lines += as_lines(res) if res["take_pair"] else [dict(hz=l["hz"], us=l["us"])]
        if prof:
            prof["transport"]["lines"] = sorted(new_lines, key=lambda l: l["hz"])
            prof["transport"]["lines_note"] = (f"lines with a phase are pairs fitted on {track(tid).id} (beatfit.py): the same part's "
                                               "wobble from the recording and from the playback, beating")
            path.write_text(json.dumps(prof, separators=(",", ":")))
            pairs = sum(1 for l in new_lines if "phase" in l) // 2
            print(f"   -> {path.name}: {len(new_lines)} lines, {pairs} of them pairs")


if __name__ == "__main__":
    main()
