"""Distortion of the chain: which order, which channel, and on which side of the chain it arises
(run align.py first).

    python distfit.py MB2 [MB2emu ...]
    python distfit.py MB2 --fit wmd6c_metalxr_v2_MB2      fit the profile's cubic per channel to the track

The residual left after the linear prediction, the per-window gain and the per-window timing is
explained with a squared and a cubed version of a signal, each through a short FIR, fitted on even
seconds and tested on odd ones. Two signals are tried:
  in    the source: a nonlinearity where the sound goes in (the tape being recorded)
  out   the linear prediction: a nonlinearity where it comes out, after the chain's response has
        turned the bass phase and raised the peaks (a playback or headphone amplifier)
For each: the share of the residual it explains in the loudest quarter of the test blocks, and the
level of what it predicts relative to the signal there. Run it on the emulation too: the same
estimator on a signal whose distortion is known says what a reading means.
"""
from __future__ import annotations

import argparse

import numpy as np

from common import db
from investigate import BLOCK, decompose, fit_fir_multi, load, predict
from tracks import track

K = 32


def fit(tid: str) -> dict:
    t = track(tid)
    sr, src, tape, z, trim = load(t.id)
    d = decompose(src, tape, sr)
    out = {}
    for name in ("L", "R"):
        ch = d[name]
        n = len(ch["clean"])
        sec = (np.arange(n) // sr) % 2
        train = sec == 0
        nb = n // BLOCK
        lvl = db(np.mean(ch["x"][: nb * BLOCK].reshape(nb, BLOCK) ** 2, axis=1))
        test_b = (np.arange(nb) * BLOCK // sr) % 2 == 1
        loud = test_b & (lvl >= np.percentile(lvl[test_b], 75))
        C = ch["clean"][: nb * BLOCK].reshape(nb, BLOCK)
        Y = ch["y"][: nb * BLOCK].reshape(nb, BLOCK)
        rows = {}
        sides = {"in": ch["x"], "out": ch["yhat"]}
        feats_of = {}
        for side, v in sides.items():
            u = v / np.std(v)
            feats_of[side] = {"2nd": u ** 2 - np.mean(u ** 2), "3rd": u ** 3}
        sets = {f"{side} {order}": [feats_of[side][order]] for side in sides for order in ("2nd", "3rd")}
        sets.update({f"{side} 2nd+3rd": [feats_of[side]["2nd"], feats_of[side]["3rd"]] for side in sides})
        sets["in+out 2nd+3rd"] = [feats_of[s][o] for s in sides for o in ("2nd", "3rd")]
        for label, feats in sets.items():
            hs = fit_fir_multi([f * train for f in feats], ch["clean"] * train, K)
            P = predict(feats, hs)[: nb * BLOCK].reshape(nb, BLOCK)
            expl = 1 - np.sum((C[loud] - P[loud]) ** 2) / np.sum(C[loud] ** 2)
            rows[label] = (float(expl), float(db(np.sum(P[loud] ** 2) / np.sum(Y[loud] ** 2))))
        rows["residual"] = (1.0, float(db(np.sum(C[loud] ** 2) / np.sum(Y[loud] ** 2))))
        out[name] = rows
    return out


def fit_cubic(tid: str, name: str, rounds: int, seed: int):
    """Sets the profile's flat cubic per channel so that the emulation's third-order distortion, measured
    as the tape's is (the "in 3rd" reading), has the tape's level. Renders with the C++ engine."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    from calibrate import CAL, render_with_engine
    from fitprofile import PROFILES

    path = PROFILES / f"{name}.json"
    prof = json.loads(path.read_text())
    engine = Path(__file__).resolve().parent.parent / "build" / "bin" / "korre-render"
    want = fit(tid)
    emu_id = f"{tid}emu"
    for r in range(rounds):
        render_with_engine(engine, tid, prof, path, seed, CAL / f"{emu_id}.flac")
        out = subprocess.run([sys.executable, "align.py", emu_id], capture_output=True, text=True, cwd=Path(__file__).parent)
        if out.returncode or "WARNING" in out.stdout:
            raise SystemExit(out.stdout + out.stderr)
        have = fit(emu_id)
        rel = prof["saturation"]["cubic_rel_db"]
        rel = dict(rel) if isinstance(rel, dict) else dict(L=rel, R=rel)
        steps = {c: want[c]["in 3rd"][1] - have[c]["in 3rd"][1] for c in "LR"}
        print(f"round {r + 1}: third-order level re signal, tape / emulation: "
              + ", ".join(f"{c} {want[c]['in 3rd'][1]:.1f} / {have[c]['in 3rd'][1]:.1f} dB" for c in "LR")
              + " | cubic_rel_db " + ", ".join(f"{c} {rel[c]:.2f} -> {rel[c] + steps[c]:.2f}" for c in "LR"), flush=True)
        prof["saturation"]["cubic_rel_db"] = {c: rel[c] + steps[c] for c in "LR"}
        prof["saturation"]["source"] = tid
        path.write_text(json.dumps(prof, separators=(",", ":")))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks", nargs="+")
    ap.add_argument("--fit", metavar="PROFILE", help="fit this profile's flat cubic per channel to the (one) track: "
                                                     "render, measure, correct, a few rounds")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    if args.fit:
        fit_cubic(args.tracks[0], args.fit, args.rounds, args.seed)
        return
    for tid in args.tracks:
        res = fit(tid)
        print(f"== {tid}: distortion in the loudest quarter (odd seconds): share of the residual explained | level re signal, dB")
        print(f"   {'':16s} {'L':>18s} {'R':>18s}")
        for label in res["L"]:
            print(f"   {label:16s} " + " ".join(f"{res[c][label][0] * 100:7.1f}% {res[c][label][1]:7.1f} dB" for c in "LR"), flush=True)


if __name__ == "__main__":
    main()
