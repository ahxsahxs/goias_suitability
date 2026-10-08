"""Gate 2 of the spatial holdout: which breakpoints move when the percentiles are
re-anchored on the calibration half, and which notes stop being true?

Offline, and WRITES NOTHING to config/. It prints the proposed edit and a CSV so a
human applies it; tools/derive_weights.py --check then confirms the weights followed.

Inputs
------
anchor_breakpoints.csv   from ``SPLIT_HALF=all tools/anchor_breakpoints.py percentiles``
                         ($SCRATCHPAD, else CWD -- pass --pctl to point at it)
config/segments.yaml     the `anchor:` block of each factor says HOW it was placed

THE THREE ANCHOR RULES (config/segments.yaml `anchor.rule`)
-----------------------------------------------------------
percentile  the breakpoint VALUE is a percentile of the observed distribution over
            a named mask. Only these can be re-anchored mechanically, and only
            these are what this gate acts on. `anchor.anchored_at` records, per
            point, the percentile VALUE the breakpoint currently sits on; the gate
            measures the shift against that, so re-running after applying an edit
            reports zero movement instead of proposing the same edit again. Absent,
            the baseline falls back to the full-domain percentile (the state before
            any re-anchoring).
mu_one      the ex-"gate" climate levers: thresholds placed so the PRESENT value
            gives mu = 1. Their anchor is a property of the present distribution,
            so the check is not "did a percentile move" but "does present mu still
            equal 1 on the calibration half" -- i.e. does the half's observed
            p5..p95 still sit inside the optimal plateau [b, c].
agronomic   a physical threshold that does not come from this territory's
            distribution (pH correctable by liming, clay to hold a pond,
            mechanisation limits). Domain-independent, hence exempt. Some of these
            quote percentiles in their note as CONTEXT; that is evidence the
            threshold was checked against the distribution, not set from it.

FLAGS (independent)
-------------------
move_breakpoint  |delta| / span >= 0.05. Two legs: (i) a 5 % shift moves mu by at
                 most 0.05 on the ramp, a fifth of the narrowest FAO class band
                 (0.25), so it cannot by itself push a pixel across a FAO cut;
                 (ii) 0.05 sits inside the +-20 % weight perturbation the thesis
                 already publishes as the model's robustness envelope. A shift the
                 sensitivity band already absorbs is not a change of claim.
rewrite_note     the percentile changed by more than NOTE_REL_TOL (0.1 %) in
                 relative terms. An earlier version compared at ONE decimal, on
                 the theory that "the notes print one decimal" -- but they print
                 whatever precision the band deserves: water_drain_density's note
                 quotes three decimals (p75 = 0,013, which moves to 0,017, a 31 %
                 change invisible at one decimal) and terr_twi's quotes two. The
                 one-decimal rule therefore passed visibly-wrong prose in silence.
                 A relative tolerance is band-agnostic. It fires MORE often than
                 move_breakpoint, and that asymmetry is correct: the prose must
                 stay true even when the threshold does not move.
shape_violation  the proposed move breaks a < b <= c < d. HARD FAIL, human
                 required -- never auto-resolve by nudging a neighbouring point,
                 which would silently change the shape's semantics.

Run::

    uv run python tools/diff_breakpoints.py [--half calib] [--pctl path/to/csv]
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd
import yaml

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

import membership  # noqa: E402

CHAPTERS = os.environ.get("SCRATCHPAD", os.path.join(ROOT, "thesis", "Chapters"))
SEG_YAML = os.path.join(ROOT, "config", "segments.yaml")
OUT_CSV = os.path.join(CHAPTERS, "breakpoint_shift.csv")

POINT_KEYS = ["a", "b", "c", "d"]
MOVE_FRAC = 0.05
# Relative, not a fixed number of decimals -- see the module docstring.
NOTE_REL_TOL = 1e-3


def span_of(ftype: str, pts: list[float]) -> float:
    """The factor's own breakpoint span -- the same convention anchor_breakpoints
    uses: b-a for increasing/decreasing, d-a for range."""
    if ftype in ("increasing", "decreasing"):
        return float(pts[1] - pts[0])
    return float(pts[-1] - pts[0])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--half", choices=["calib", "val"], default="calib")
    ap.add_argument("--pctl", default=None,
                    help="path to anchor_breakpoints.csv (default: $SCRATCHPAD/CWD)")
    args = ap.parse_args()

    src = args.pctl or os.path.join(os.environ.get("SCRATCHPAD", os.getcwd()),
                                    "anchor_breakpoints.csv")
    if not os.path.exists(src):
        raise SystemExit(f"[FALHA] {src} ausente. Rode:\n"
                         "  SPLIT_HALF=all ANCHOR_SCALE=1000 EE_PROJECT=probformer "
                         "uv run python tools/anchor_breakpoints.py percentiles")
    pct = pd.read_csv(src)
    if "half" not in pct.columns:
        raise SystemExit(f"[FALHA] {src} nao tem coluna 'half' (SPLIT_HALF=all).")
    for need in ("full", args.half):
        if need not in set(pct["half"]):
            raise SystemExit(f"[FALHA] falta half={need!r} em {src}.")

    # (mask, half, field) -> {p5: .., p50: ..}
    look: dict[tuple, dict] = {}
    for r in pct.itertuples():
        look[(r.mask, r.half, r.field)] = {c: getattr(r, c)
                                           for c in pct.columns if c.startswith("p")}

    cfg = yaml.safe_load(open(SEG_YAML, encoding="utf-8"))
    rows, missing, exempt = [], [], {"mu_one": 0, "agronomic": 0}

    for seg, d in cfg["segments"].items():
        for f, spec in d["factors"].items():
            anc = spec.get("anchor") or {}
            rule = anc.get("rule", "agronomic")
            pts = list(spec["points"])
            ftype = spec["type"]

            if rule == "mu_one":
                # does the restricted half's observed range still sit inside the
                # optimal plateau, so present mu is still 1?
                st = look.get(("available", args.half, f))
                sf = look.get(("available", "full", f))
                if st is None:
                    missing.append(f"{seg}.{f} (mu_one, banda ausente no CSV)")
                    continue
                lo_k, hi_k = ("p5", "p95")
                lo, hi = st.get(lo_k), st.get(hi_k)
                plateau = ((pts[1], pts[2]) if ftype == "range"
                           else (pts[0], pts[1]))
                holds = (lo is not None and hi is not None
                         and lo >= min(plateau) and hi <= max(plateau))
                rows.append({
                    "segment": seg, "factor": f, "rule": rule, "point": "-",
                    "type": ftype, "span": span_of(ftype, pts),
                    "value_now": None, "pctl": f"{lo_k}..{hi_k}",
                    "pctl_full": None if sf is None else sf.get(lo_k),
                    f"pctl_{args.half}": lo, "delta": None, "delta_over_span": None,
                    "value_proposed": None,
                    "move_breakpoint": False, "rewrite_note": False,
                    "shape_violation": False,
                    "mu_one_holds": bool(holds),
                    "detail": (f"plateau {plateau}, {args.half} p5..p95 "
                               f"= {lo}..{hi}"),
                })
                exempt["mu_one"] += 1
                continue

            if rule != "percentile":
                exempt["agronomic"] += 1
                rows.append({
                    "segment": seg, "factor": f, "rule": rule, "point": "-",
                    "type": ftype, "span": span_of(ftype, pts),
                    "value_now": None, "pctl": None, "pctl_full": None,
                    f"pctl_{args.half}": None, "delta": None,
                    "delta_over_span": None, "value_proposed": None,
                    "move_breakpoint": False, "rewrite_note": False,
                    "shape_violation": False, "mu_one_holds": None,
                    "detail": "exempt: threshold not drawn from the distribution",
                })
                continue

            mask = anc.get("mask", "available")
            pmap = anc.get("points") or {}
            span = span_of(ftype, pts)
            proposed = list(pts)
            for i, pk in enumerate(POINT_KEYS[:len(pts)]):
                q = pmap.get(pk)
                if not q:
                    continue
                kf = look.get((mask, "full", f))
                kh = look.get((mask, args.half, f))
                if kf is None or kh is None:
                    missing.append(f"{seg}.{f} ({mask}/{f})")
                    continue
                vf, vh = kf.get(q), kh.get(q)
                if vf is None or vh is None or (isinstance(vf, float) and np.isnan(vf)):
                    missing.append(f"{seg}.{f}.{pk} ({q} ausente)")
                    continue
                # BASELINE: the percentile this breakpoint is CURRENTLY anchored to,
                # recorded in anchor.anchored_at when a shift has been applied.
                # Without it the gate is not idempotent -- delta would stay
                # pctl_calib - pctl_full forever and keep proposing a move that is
                # already in the file, which is exactly how cattle.clim_soil_moist
                # and cattle.soil_soc read as "unapplied" after being applied.
                base = (anc.get("anchored_at") or {}).get(pk)
                vb = float(base) if base is not None else float(vf)
                delta = float(vh) - vb
                dos = abs(delta) / span if span else float("nan")
                move = dos >= MOVE_FRAC
                scale_ref = max(abs(vb), abs(float(vh)))
                note = (scale_ref > 0
                        and abs(delta) / scale_ref > NOTE_REL_TOL)
                if move:
                    # keep the breakpoint's own rounding style
                    proposed[i] = round(float(pts[i]) + delta,
                                        max(0, -int(np.floor(np.log10(span))) + 2))
                rows.append({
                    "segment": seg, "factor": f, "rule": rule, "point": pk,
                    "type": ftype, "span": span, "value_now": pts[i], "pctl": q,
                    "pctl_full": vf, "pctl_anchored_at": vb,
                    f"pctl_{args.half}": vh, "delta": delta,
                    "delta_over_span": dos,
                    "delta_rel": (abs(delta) / scale_ref) if scale_ref else None,
                    "value_proposed": proposed[i] if move else pts[i],
                    "move_breakpoint": bool(move), "rewrite_note": bool(note),
                    "shape_violation": False, "mu_one_holds": None, "detail": "",
                })
            # shape check on the full proposal for this factor
            try:
                # validate_points takes (band, spec); reuse it rather than
                # re-implementing a < b <= c < d, so the gate and the engine can
                # never disagree about what a valid shape is
                membership.validate_points(f, {"type": ftype, "points": proposed})
                bad = False
            except Exception as e:  # noqa: BLE001
                bad = True
                print(f"  !! {seg}.{f}: forma invalida apos o movimento: {e}")
            if bad:
                for r in rows:
                    if r["segment"] == seg and r["factor"] == f:
                        r["shape_violation"] = True

    out = pd.DataFrame(rows)
    os.makedirs(CHAPTERS, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    pd.set_option("display.width", 230, "display.max_columns", 30,
                  "display.max_rows", 300)

    perc = out[out.rule == "percentile"]
    print(f"\n=== fatores ancorados em percentil ({perc.factor.nunique()} fatores, "
          f"{len(perc)} pontos) ===")
    if len(perc):
        print(perc[["segment", "factor", "point", "pctl", "pctl_full",
                    f"pctl_{args.half}", "delta", "delta_over_span", "value_now",
                    "value_proposed", "move_breakpoint", "rewrite_note"]]
              .round(4).to_string(index=False))

    mu = out[out.rule == "mu_one"]
    if len(mu):
        print(f"\n=== fatores ancorados em mu=1 ({len(mu)}) ===")
        print(mu[["segment", "factor", "mu_one_holds", "detail"]].to_string(index=False))

    moves = perc[perc.move_breakpoint]
    notes = perc[perc.rewrite_note]
    shapes = out[out.shape_violation]
    broken = mu[mu.mu_one_holds == False]  # noqa: E712

    print(f"\n{'=' * 72}")
    print(f"GATE 2 ({args.half} vs full):")
    print(f"  exentos: {exempt['agronomic']} agronomicos + {exempt['mu_one']} mu=1")
    print(f"  mover breakpoint (|d|/span >= {MOVE_FRAC}): {len(moves)}")
    print(f"  reescrever note (mudanca relativa > 0,1%):  {len(notes)}")
    print(f"  violacao de forma (FALHA dura):             {len(shapes)}")
    print(f"  mu=1 deixou de valer na metade {args.half}:       {len(broken)}")
    if len(moves):
        print("\nedicao proposta em config/segments.yaml (aplicar a mao):")
        for (seg, f), g in moves.groupby(["segment", "factor"]):
            cur = cfg["segments"][seg]["factors"][f]["points"]
            new = list(cur)
            for r in g.itertuples():
                new[POINT_KEYS.index(r.point)] = r.value_proposed
            print(f"  {seg}.{f}:  points: {cur}  ->  {new}")
    if len(broken):
        print("\n!! mu=1 nao se sustenta -- esses fatores precisam de reancoragem "
              "manual, senao um deflator global volta:")
        print(broken[["segment", "factor", "detail"]].to_string(index=False))
    if missing:
        print(f"\nbandas nao encontradas no CSV de percentis ({len(missing)}):")
        for m in sorted(set(missing)):
            print(f"  {m}")
    print(f"\n# wrote {OUT_CSV}")
    print("# Esta ferramenta NAO escreve em config/. Aplique a mao e rode "
          "tools/derive_weights.py --check.")
    return 1 if (len(shapes) or len(broken)) else 0


if __name__ == "__main__":
    sys.exit(main())
