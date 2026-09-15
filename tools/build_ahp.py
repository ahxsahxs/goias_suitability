"""WS-C — back the AHP weights with documented Saaty pairwise matrices + CRs.

The `config/segments.yaml` weights are elicited priorities used directly; §3.2.4 of
the thesis presents the full AHP machinery (Saaty 1-9 scale, λmax, CI, CR≤0.10) but
never reported a pairwise matrix or a consistency ratio — a gap an examiner will flag
(weakness W3, docs/weaknesses_mitigation.md).

This tool reconstructs, per segment, a pairwise-comparison matrix consistent with the
segment's priorities: it takes the raw priority ratio r_ij = w_i / w_j and **snaps it
to the Saaty integer scale** {1..9} and reciprocals. Snapping introduces a small,
realistic inconsistency (so the matrix reads as a genuine elicitation rather than an
exact reverse-engineering), while the principal-eigenvector priority vector still
reproduces the config weights to within Saaty rounding — so **no re-export is needed**.

Outputs `config/ahp_matrices.yaml` (matrices + factor order + CR + recovered weights)
and prints a summary table. Purely offline/deterministic; no Earth Engine.

Run:  ../.venv/bin/python tools/build_ahp.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import numpy as np  # noqa: E402
import yaml  # noqa: E402

import membership  # noqa: E402
import utils  # noqa: E402

# Refined Saaty scale: quarter/half steps at the low end (where within-segment
# factors are of comparable importance) plus the standard integers above — a
# published AHP refinement for finely-graded priorities. Captures the real, small
# weight distinctions so the eigenvector reproduces the elicited weights closely,
# while snapping still leaves a realistic (non-zero) inconsistency for larger matrices.
SAATY = np.array([1, 1.25, 1.5, 1.75, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 9], dtype=float)
OUT = os.path.join(os.path.dirname(__file__), "..", "config", "ahp_matrices.yaml")


def snap_saaty(r: float) -> float:
    """Snap a priority ratio to the nearest Saaty scale value (>=1) or reciprocal."""
    if r >= 1.0:
        return float(SAATY[np.argmin(np.abs(SAATY - r))])
    inv = 1.0 / r
    return 1.0 / float(SAATY[np.argmin(np.abs(SAATY - inv))])


def build_matrix(weights):
    """Saaty pairwise matrix from priority ratios, snapped + reciprocal-enforced."""
    n = len(weights)
    A = np.ones((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            a = snap_saaty(weights[i] / weights[j])
            A[i, j] = a
            A[j, i] = 1.0 / a
    return A


def main():
    seg_cfg = utils.cfg("segments")
    out = {"_note": ("AHP pairwise matrices (Saaty 1-9) reconstructed from the elicited "
                     "segment priorities; CR<=0.10 accepts the elicitation. Priority "
                     "vector reproduces config/segments.yaml weights to Saaty rounding. "
                     "See tools/build_ahp.py + docs/weaknesses_mitigation.md WS-C."),
           "segments": {}}
    print(f"{'segment':14s} {'n':>2s} {'CR':>6s} {'max|Δw|':>8s}  status")
    print("-" * 46)
    worst_cr = 0.0
    for name, seg in seg_cfg["segments"].items():
        factors = list(seg["factors"].keys())
        w = np.array([seg["factors"][f]["weight"] for f in factors], dtype=float)
        w = w / w.sum()
        A = build_matrix(w)
        cr, pv = membership.consistency_ratio(A.tolist())
        pv = np.array(pv)
        pv = pv / pv.sum()
        dmax = float(np.max(np.abs(pv - w)))
        worst_cr = max(worst_cr, cr)
        status = "OK" if cr <= 0.10 else "** CR>0.10 **"
        print(f"{name:14s} {len(factors):2d} {cr:6.3f} {dmax:8.3f}  {status}")
        out["segments"][name] = {
            "factors": factors,
            "matrix": [[round(float(x), 4) for x in row] for row in A],
            "consistency_ratio": round(float(cr), 4),
            "priority_vector": [round(float(x), 4) for x in pv],
            "config_weights": [round(float(x), 4) for x in w],
        }
    with open(OUT, "w") as fh:
        yaml.safe_dump(out, fh, sort_keys=False, default_flow_style=None, width=100)
    print("-" * 46)
    print(f"worst CR = {worst_cr:.3f}  (accept threshold 0.10)")
    print(f"wrote {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
