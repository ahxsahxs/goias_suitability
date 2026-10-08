"""Gate 1 of the spatial holdout: does restricting sigma(mu) to the calibration
half break any factor's weight?

Offline. Reads thesis/Chapters/factor_discrimination.csv (which must carry a
`half` column -- produce it with
``SPLIT_HALF=all tools/anchor_breakpoints.py discrimination``) and writes
thesis/Chapters/sigma_domain_diff.csv plus a verdict.

WHY THIS GATE EXISTS
--------------------
sigma(mu) can only SHRINK on half the territory, and under the weighted geometric
mean a weight of exactly zero removes a factor from the product entirely -- taking
its CMIP6 lever with it. That is the failure the `sigma_mu_horizon` pooling was
introduced to prevent (it replaced the `role: gate` category on 2026-10-02), and
CLAUDE.md S11 treats it as a hard rule. Five factors already sit at w = 0 because
their mu is identically 1 in both the present and the SSP5-8.5 horizon; halving the
measurement domain must not add more.

An epsilon floor on d is deliberately NOT an option here: config/ahp_matrices.yaml
records it as considered and declined, because it arbitrates exactly the
subjectivity the derivation exists to remove.

DECISION RULE, in strict precedence (per factor):
  d_full > 0 and d_calib == 0 .................. FAIL  (factor leaves the product)
  d_calib < 0.01 while d_full >= 0.05 .......... FAIL  (weight collapses >= 5x)
  ratio = d_calib/d_full outside [0.5, 2.0] .... WARN  (name it in the results)
  |delta_w| > 0.05 ............................. WARN  (exceeds the +-20% band)
  otherwise .................................... OK

Run::

    uv run python tools/diff_sigma_domains.py
    uv run python tools/diff_sigma_domains.py --half val   # audit the other half
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import derive_weights as dw  # noqa: E402

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CHAPTERS = os.environ.get("SCRATCHPAD", os.path.join(ROOT, "thesis", "Chapters"))
DISCRIM = os.path.join(CHAPTERS, "factor_discrimination.csv")
OUT_CSV = os.path.join(CHAPTERS, "sigma_domain_diff.csv")

ZERO_TOL = 1e-12      # "exactly zero" as written by a float CSV round-trip
D_COLLAPSE = 0.01     # d below this is practically inert
D_MATERIAL = 0.05     # ... and only a FAIL if it was material in the full domain
RATIO_LO, RATIO_HI = 0.5, 2.0
DELTA_W_WARN = 0.05


def verdict(d_full: float, d_half: float, ratio: float, delta_w: float) -> str:
    if d_full > ZERO_TOL and d_half <= ZERO_TOL:
        return "FAIL: zeroed by restriction"
    if d_half < D_COLLAPSE and d_full >= D_MATERIAL:
        return "FAIL: weight collapses >=5x"
    if not np.isnan(ratio) and (ratio < RATIO_LO or ratio > RATIO_HI):
        return f"WARN: d moved {ratio:.2f}x"
    if not np.isnan(delta_w) and abs(delta_w) > DELTA_W_WARN:
        return f"WARN: |dw|={abs(delta_w):.3f} > {DELTA_W_WARN}"
    return "OK"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--half", choices=["calib", "val"], default="calib",
                    help="the restricted domain to compare against full")
    args = ap.parse_args()

    if not os.path.exists(DISCRIM):
        raise SystemExit(f"[FALHA] {DISCRIM} ausente.")
    df = pd.read_csv(DISCRIM)
    if "half" not in df.columns:
        raise SystemExit(
            f"[FALHA] {os.path.relpath(DISCRIM, ROOT)} nao tem coluna 'half'.\n"
            "        Rode: SPLIT_HALF=all EE_PROJECT=probformer uv run python "
            "tools/anchor_breakpoints.py discrimination")
    have = sorted(df["half"].dropna().unique())
    for need in ("full", args.half):
        if need not in have:
            raise SystemExit(f"[FALHA] falta half={need!r} no CSV (tem {have}).")

    d = {h: {(r.segment, r.factor): float(getattr(r, dw.D_COLUMN))
             for r in df[df.half == h].itertuples()} for h in have}

    seg_cfg = yaml.safe_load(open(dw.SEG_YAML, encoding="utf-8"))
    lam = seg_cfg["aggregation"]["lambda_regional"]
    ahp = yaml.safe_load(open(dw.AHP_YAML, encoding="utf-8"))
    cr_max = ahp["scale"]["cr_threshold"]
    max_rev = ahp["scale"]["max_revisions_per_segment"]
    print(f"# lambda = {lam};  dominios: full vs {args.half}")

    rows = []
    for name in seg_cfg["segments"]:
        res = dw.derive_segment(name, ahp["segments"][name], cr_max, max_rev,
                                verbose=False)
        fs = res["factors"]
        w_lit = res["priority_vector"]
        # w depends on EVERY factor of the segment through the normalisation, so
        # the weights must be recomputed per domain for the whole segment at once
        # -- a per-factor ratio of d would not give the weight change.
        try:
            w_full = dw.adapt(w_lit, [d["full"][(name, f)] for f in fs], lam)
        except (KeyError, ValueError) as e:
            print(f"  !! {name}: {e}")
            continue
        try:
            w_half = dw.adapt(w_lit, [d[args.half][(name, f)] for f in fs], lam)
        except ValueError:
            # every d == 0 in the restricted domain: the segment has no
            # discriminating power left at all
            w_half = [float("nan")] * len(fs)
        for i, f in enumerate(fs):
            df_full = d["full"][(name, f)]
            df_half = d[args.half].get((name, f), float("nan"))
            ratio = (df_half / df_full) if df_full > ZERO_TOL else float("nan")
            dwt = w_half[i] - w_full[i]
            rows.append({
                "segment": name, "factor": f,
                "d_full": df_full, f"d_{args.half}": df_half,
                "d_val": d.get("val", {}).get((name, f), float("nan")),
                "ratio": ratio,
                "w_lit": w_lit[i], "w_full": w_full[i], f"w_{args.half}": w_half[i],
                "delta_w": dwt,
                "verdict": verdict(df_full, df_half, ratio, dwt),
            })

    out = pd.DataFrame(rows)
    os.makedirs(CHAPTERS, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    pd.set_option("display.width", 220, "display.max_columns", 30,
                  "display.max_rows", 200)
    print("\n" + out.round(4).to_string(index=False))
    print(f"\n# wrote {OUT_CSV}")

    fails = out[out.verdict.str.startswith("FAIL")]
    warns = out[out.verdict.str.startswith("WARN")]
    print(f"\n{'=' * 72}")
    print(f"GATE 1 ({args.half} vs full):  {len(fails)} FAIL, {len(warns)} WARN, "
          f"{len(out) - len(fails) - len(warns)} OK  (de {len(out)} fatores)")
    if len(fails):
        print("\nFAIL -- a perna de estimacao NAO pode seguir como esta:")
        print(fails[["segment", "factor", "d_full", f"d_{args.half}",
                     "w_full", f"w_{args.half}", "verdict"]].round(4)
              .to_string(index=False))
        print("\nEscada de recuo (pre-comprometida, ver o plano):")
        print("  F1  alargar a populacao de horizonte (presente U as 4 celulas CMIP6);")
        print("      monotonicamente nao-decrescente em d, logo nao pode piorar nada.")
        print("      Exige exportar os 3 clim_future_* ainda nao cacheados.")
        print("  F2  restringir so os percentis de breakpoint; manter sigma(mu) no")
        print("      dominio completo (justificado: sem desfecho dentro de sigma(mu)).")
        print("  F3  abandonar a perna de estimacao; manter o holdout na validacao,")
        print("      no RF e em lambda. Desfecho legitimo, nao fracasso.")
    if len(warns):
        print("\nWARN -- permitido, mas tem de ser nomeado no texto:")
        print(warns[["segment", "factor", "d_full", f"d_{args.half}", "ratio",
                     "delta_w", "verdict"]].round(4).to_string(index=False))
    # Five factors are ALREADY at d == 0 in the full domain; they are not failures
    # of the restriction and must not be counted as such.
    pre = out[(out.d_full <= ZERO_TOL)]
    if len(pre):
        print(f"\nnota: {len(pre)} fator(es) ja estavam em d = 0 no dominio completo "
              f"(nao sao efeito da restricao):")
        print("  " + ", ".join(f"{r.segment}.{r.factor}" for r in pre.itertuples()))
    return 1 if len(fails) else 0


if __name__ == "__main__":
    sys.exit(main())
