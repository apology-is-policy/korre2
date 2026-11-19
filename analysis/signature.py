"""Measurement signature of an aligned song: what calibrate.py makes the emulation match.

    python signature.py B3 [B3emu]      prints the signature (and a comparison if two are given)

Measured the same way for the real tape and for an emulation of the same source, so the
estimators' own biases cancel in the comparison:
  dev         speed-deviation spectrum from align.py's delay curve (slow transport wobble)
  am / pm     complex demodulation of the residual (tape minus linear prediction) per octave band
              (modstats.demod_spectra): amplitude modulation in %^2/Hz and timing in us^2/Hz,
              per modulation-rate band, per channel, and their L/R coherence
  eq / phase  static response per channel, magnitude (power only) and phase (fitprofile)
  left        whole residual re signal per octave band, loud blocks (the overall "dirt" level)
"""
from __future__ import annotations

import argparse
import pickle

import numpy as np
from scipy import signal

from common import data_file, db, decode
from fitprofile import eq_magnitude_phase, recorded_noise_psd
from align import FINE_HOP, window_delay
from investigate import band, load
from measure import OUT, apply_H, cross_spectra
from tracks import SIDE_FILES, track

OCT = [(707, 1414, 1000), (1414, 2828, 2000), (2828, 5657, 4000), (5657, 11314, 8000), (11314, 16000, 13000)]
RATES = [(3, 6), (6, 12), (12, 24), (24, 48), (48, 96), (96, 192), (192, 384), (384, 768), (768, 1536), (1536, 2800)]
DEV_RATES = [(0.3, 0.75), (0.75, 1.5), (1.5, 3), (3, 6), (6, 12), (12, 20)]
NPER = 16384
FINE_OCTS = (1000, 2000, 4000)  # octaves for the fine timing spectrum: where the music's body is
FINE_FS = 375.0  # its sample rate, Hz
FINE_SECONDS = 8.0  # and segment length: 0.125 Hz steps
EPS_REL = 0.25


def rate_sums(f, P, rates, fmax):
    df = f[1] - f[0]
    out = []
    for a, b in rates:
        m = (f >= a) & (f < b)
        out.append(float(P[m].sum() * df) if (m.any() and b <= fmax * 1.01) else np.nan)
    return np.array(out)


def hiss_psd(t, sr):
    """The tape's background noise (recorded gaps between songs), per channel."""
    return recorded_noise_psd(t.side, sr)


def signature(tid: str, cache: bool = True) -> dict:
    path = OUT / f"sig_{tid}.pkl"
    aligned = OUT / f"{tid}_aligned.npz"
    if cache and path.exists() and path.stat().st_mtime > aligned.stat().st_mtime:
        cached = pickle.loads(path.read_bytes())
        if "f" in cached.get("timing_psd", {}):  # absent in signatures cached before the whole timing spectrum existed
            return cached
    t = track(tid)
    sr, src, tape, z, trim = load(t.id)
    fh, Ph = hiss_psd(t, sr)
    sig = dict(id=tid, sr=sr)

    # slow transport: speed deviation spectrum (percent^2/Hz)
    dev_t, dev = z["dev_t"], z["dev"]
    fs = 1 / np.median(np.diff(dev_t))
    fd, Pd = signal.welch(dev, fs, nperseg=min(len(dev), 2048))
    sig["dev"] = rate_sums(fd, Pd, DEV_RATES, fs / 2)

    # static response, linear prediction and residual per channel
    yh, rr = [], []
    sig["eq"], sig["phase"], sig["gain_db"] = {}, {}, {}
    for c, name in ((0, "L"), (1, "R")):
        x, y = src[:, c], tape[:, c]
        eq, ph, ref = eq_magnitude_phase(x, y, sr, fh, Ph[:, c])
        sig["eq"][name], sig["phase"][name], sig["gain_db"][name] = eq, ph, float(10 * np.log10(ref))
        f, Pxx, _, Pxy = cross_spectra(x, y, sr)
        yhat = apply_H(x, f, Pxy / Pxx)
        yh.append(yhat)
        rr.append(y - yhat)

    # The whole timing in fine steps: what the alignment's warp took out (its delay curve: the slow
    # wobble and the flutter lines up to about 19 Hz) plus what it left, per 11 ms window, added in
    # step. Linear and unweighted: a steady line of 12 us reads 12 us wherever the music is dense or
    # sparse, and the reading does not depend on where the alignment's split falls.
    centres, late, weight = window_delay(yh, [tape[:, c] for c in range(2)], sr)
    late[weight < 0.05 * np.median(weight)] = 0.0  # no sound, no reading
    tracked = np.interp(trim + centres, z["centers"], z["delay"]) / sr
    whole_us = (tracked + late) * 1e6
    whole_us -= np.polyval(np.polyfit(centres, whole_us, 1), centres)  # the offset and the speed error
    fs_w = sr / FINE_HOP
    ft, Pt = signal.welch(whole_us, fs_w, nperseg=int(round(FINE_SECONDS * fs_w)), detrend="linear")
    sig["timing_psd"] = dict(f=ft, psd=Pt)  # us^2/Hz, the timing both channels share
    del src, tape

    # per octave: demodulated AM and timing spectra, L/R coherence, residual level
    sig["am"], sig["pm"], sig["am_coh"], sig["pm_coh"], sig["left_db"] = {}, {}, {}, {}, {}
    sig["pm_psd"] = {}
    for lo, hi, fc in OCT:
        hi = min(hi, 0.45 * sr)
        fmax = (hi - lo) / 2
        k_us = (1e6 / (2 * np.pi * np.sqrt(lo * hi))) ** 2
        dem, lefts = [], []
        for c in range(2):
            yb, rb = band(yh[c], sr, lo, hi), band(rr[c], sr, lo, hi)
            B = 4096
            nb = len(yb) // B
            py = (yb[: nb * B] ** 2).reshape(nb, B).mean(1)
            pr = (rb[: nb * B] ** 2).reshape(nb, B).mean(1)
            loud = py > np.median(py)
            lefts.append(float(db(pr[loud].sum() / py[loud].sum())))
            Yh, Rr = signal.hilbert(yb), signal.hilbert(rb)
            p2 = np.abs(Yh) ** 2
            eps = EPS_REL * np.median(p2[p2 > np.median(p2)])
            w = p2 / (p2 + eps)
            dem.append((Rr * np.conj(Yh) / (p2 + eps) * w, np.mean(w ** 2)))
            del yb, rb, Yh, Rr, p2, w
        am, pm = [], []
        for d, norm in dem:
            f, Pa = signal.welch(d.real, sr, nperseg=NPER)
            _, Pp = signal.welch(d.imag, sr, nperseg=NPER)
            am.append(rate_sums(f, Pa / norm, RATES, fmax))
            pm.append(rate_sums(f, Pp / norm * k_us, RATES, fmax))
        if fc in FINE_OCTS:
            # The slow end of the timing in fine steps: the bands above are 2.9 Hz bins, which cannot tell
            # the capstan's 7.5 Hz from what lies beside it.
            q = int(round(sr / FINE_FS))
            fine = []
            for d, norm in dem:
                slow = signal.resample_poly(d.imag, 1, q)
                ff, Pf = signal.welch(slow, sr / q, nperseg=int(FINE_SECONDS * sr / q))
                fine.append(Pf / norm * k_us)
            sig["pm_psd"][fc] = dict(f=ff, psd=np.mean(fine, axis=0))  # us^2/Hz, mean of L and R: left after the warp
        cohs = {}
        for kind, fn in (("am", np.real), ("pm", np.imag)):
            fc_, C = signal.coherence(fn(dem[0][0]), fn(dem[1][0]), sr, nperseg=NPER)
            cohs[kind] = np.array([float(C[(fc_ >= a) & (fc_ < b)].mean()) if b <= fmax * 1.01 else np.nan
                                   for a, b in RATES])
        sig["am"][fc], sig["pm"][fc] = np.array(am), np.array(pm)  # (channel, rate band)
        sig["am_coh"][fc], sig["pm_coh"][fc] = cohs["am"], cohs["pm"]
        sig["left_db"][fc] = np.array(lefts)
        del dem
    if cache:
        path.write_bytes(pickle.dumps(sig))
    return sig


# ---------------------------------------------------------------- reporting
def fmt_row(vals, f="{:6.2f}"):
    return " ".join("     -" if np.isnan(v) else f.format(v) for v in vals)


def report(s: dict, ref: dict | None = None):
    """Print a signature; with ref (the real tape), print tape -> emulation side by side."""
    pair = lambda key: (ref[key], s[key]) if ref else (s[key], None)
    print(f"== signature {s['id']}" + (f" vs tape {ref['id']}" if ref else ""))
    hdr = " ".join(f"{a:g}-{b:g}".rjust(6) for a, b in DEV_RATES)
    print(f"  speed deviation RMS % per rate band [Hz]   {hdr}")
    for lab, v in zip(("tape", "emu "), pair("dev")):
        if v is not None:
            print(f"    {lab}                                    {fmt_row(np.sqrt(v), '{:6.3f}')}")
    hdr = " ".join(f"{a:g}-{b:g}".rjust(9) for a, b in RATES)
    for key, unit, conv in (("pm", "timing us RMS", np.sqrt), ("am", "AM % RMS", lambda v: np.sqrt(v) * 100)):
        print(f"  {unit} (mean of L,R) per rate band [Hz]\n    band      {hdr}")
        for fc in s[key]:
            for lab, sg in zip(("tape", "emu "), pair(key)):
                if sg is not None:
                    print(f"    {fc:5d} {lab} " + " ".join("        -" if np.isnan(v) else f"{v:9.2f}"
                                                         for v in conv(sg[fc].mean(axis=0))))
        print(f"  {key.upper()} L/R coherence\n    band      {hdr}")
        for fc in s[key]:
            for lab, sg in zip(("tape", "emu "), pair(f"{key}_coh")):
                if sg is not None:
                    print(f"    {fc:5d} {lab} " + " ".join("        -" if np.isnan(v) else f"{v:9.2f}" for v in sg[fc]))
    print("  residual re signal, loud blocks, dB (L / R) per octave")
    for lab, sg in zip(("tape", "emu "), pair("left_db")):
        if sg is not None:
            print(f"    {lab} " + "  ".join(f"{fc}: {v[0]:6.1f}/{v[1]:6.1f}" for fc, v in sg.items()))
    from fitprofile import EQ_GRID
    g = np.array(EQ_GRID)
    pts = [30, 50, 100, 300, 1000, 3000, 6000, 10000, 14000]
    idx = [int(np.argmin(np.abs(g - p))) for p in pts]
    print("  static response L/R: magnitude dB re 1 kHz | phase deg at " + ", ".join(f"{p:g}" for p in pts) + " Hz")
    for lab, (sg_eq, sg_ph) in zip(("tape", "emu "), ((ref["eq"], ref["phase"]) if ref else (s["eq"], s["phase"]),
                                                       (s["eq"], s["phase"]) if ref else (None, None))):
        if sg_eq is None:
            continue
        for ch in "LR":
            print(f"    {lab} {ch} " + " ".join(f"{sg_eq[ch][i]:+5.1f}" for i in idx) + " | "
                  + " ".join(f"{np.degrees(sg_ph[ch][i]):+5.0f}" for i in idx))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    sigs = [signature(t, cache=not args.no_cache) for t in args.tracks]
    if len(sigs) == 2:
        report(sigs[1], sigs[0])
    else:
        for s in sigs:
            report(s)


if __name__ == "__main__":
    main()
