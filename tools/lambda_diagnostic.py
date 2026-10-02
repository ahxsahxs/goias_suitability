"""Robustness of the regional-adaptation exponent lambda (Part 9).

Recomputes suitability offline for lambda in {0, 0.25, 0.5, 0.75, 1} and scores each
against realized presence, so the thesis can state where the chosen lambda = 0.5 sits
rather than assert that it is reasonable.

Cheap by construction: the per-factor memberships are sampled from Earth Engine ONCE
per segment, and every lambda is then a numpy re-weighting of the same matrix. No
re-export, and the fuzzy engine is never re-run server-side.

**This is a diagnostic, not a calibration.** lambda is fixed a priori at 0.5 and is NOT
retuned from this output: MapBiomas is a validation and masking layer, never a
calibration target (CLAUDE.md section 7). Moving lambda to the argmax would make the
realized map an input.

What the sweep actually shows (thesis/Chapters/lambda_auc.csv) is that AUC rises
MONOTONICALLY with lambda for soybean (0.6752 -> 0.7293), other_crops and cattle; only
sugarcane declines, and by 0.0008. So lambda = 0.5 is not "at the optimum" -- it sits
BELOW the presence-optimal value in every segment with a real gradient. Report it that
way: the a priori choice is deliberately conservative, conceding discriminating power
rather than harvesting it, which is the stronger argument for fixing it in advance.

Two caveats that belong beside any reported table:
  * other_crops has 34 presences at AUC ~0.54 -- noise, not evidence. Do not report it.
  * the ranking is not fully independent of MapBiomas. Seven breakpoints in
    config/segments.yaml are still anchored to the REALIZED niche (soybean/sugarcane/
    cattle percentiles, from the 2026-07 recalibration, predating the available-land
    rule of docs/ahp_literatura.md 2b), so realized use reaches mu, hence sigma(mu),
    hence w -- and then this tool scores w against that same map.

Run::

    EE_PROJECT=probformer uv run python tools/lambda_diagnostic.py [segment ...]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import ee  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import features  # noqa: E402
import membership  # noqa: E402
import metrics  # noqa: E402
import utils  # noqa: E402
import zoning  # noqa: E402
import derive_weights as dw  # noqa: E402

# realized MapBiomas role per segment (external.ROLE_CODES)
ROLE = {"soybean": 1, "sugarcane": 2, "other_crops": 3, "pisciculture": 4, "cattle": 5}
CAP, TS = 4500, 8


def main():
    want = sys.argv[1:] or ["soybean", "sugarcane", "other_crops", "cattle"]
    project = utils.init()
    aoi = utils.load_aoi(project)
    cfg = utils.cfg("segments")
    lam_cfg = cfg["aggregation"]["lambda_regional"]
    eps = cfg["aggregation"]["epsilon"]

    stack = ee.Image(utils.asset_id(project, "feature_stack_250m"))
    lc = features.landcover_features_mapbiomas(aoi)
    realized = ee.Image(utils.asset_id(project, "feat_realized"))
    extras = {
        "sit_": ee.Image(utils.asset_id(project, "feat_siting")),
        "cv_": ee.Image(utils.asset_id(project, "feat_conservation")),
        "rl_": realized,
    }
    grid = zoning.build_strat_band(aoi, n_side=8)
    d_map = dw.load_discrimination()
    ahp = dw.yaml.safe_load(open(dw.AHP_YAML, encoding="utf-8"))

    rows = []
    for seg in want:
        spec = cfg["segments"][seg]
        res = dw.derive_segment(seg, ahp["segments"][seg], 0.10, 3, verbose=False)
        fs = res["factors"]
        M = membership.segment_membership_image(stack, lc, spec, cfg, extras)
        img = (M.select([f"mem_{f}" for f in fs])
                 .addBands(realized.select("rl_role"))
                 .addBands(grid)
                 .updateMask(lc.select("mask_available")))
        print(f"  -> sampling {seg} ...", flush=True)
        fc = img.stratifiedSample(
            numPoints=CAP // 64, classBand="strat_grid", region=aoi,
            scale=250, seed=11, tileScale=TS, dropNulls=True, geometries=False)
        df = zoning.fc_to_df(fc)
        y = (df["rl_role"] == ROLE[seg]).astype(int).values
        if y.sum() < 30:
            print(f"     (skip {seg}: only {y.sum()} presences)")
            continue
        Mx = np.clip(df[[f"mem_{f}" for f in fs]].values.astype(float), eps, 1.0)
        d = np.array([d_map[(seg, f)] for f in fs])
        for lam in dw.LAMBDA_GRID:
            w = np.array(dw.adapt(res["priority_vector"], d, lam))
            s = np.exp(np.log(Mx) @ w) if spec.get("aggregate") != "arithmetic" else Mx @ w
            rows.append({"segment": seg, "lambda": lam, "n": len(y),
                         "presences": int(y.sum()),
                         "auc": round(metrics.auc(y, s)["auc"], 4)})
            print(f"     lambda={lam:<5} AUC={rows[-1]['auc']:.4f}")

    df = pd.DataFrame(rows)
    out = os.path.join(os.path.dirname(__file__), "..", "thesis", "Chapters")
    out = os.environ.get("SCRATCHPAD", os.path.normpath(out))
    dest = os.path.join(out, "lambda_auc.csv")
    df.to_csv(dest, index=False)
    print("\n", df.pivot(index="segment", columns="lambda", values="auc").to_string())
    best = df.loc[df.groupby("segment")["auc"].idxmax(), ["segment", "lambda", "auc"]]
    print(f"\nlambda adotado (a priori) = {lam_cfg}")
    print("argmax por segmento (NAO usado para calibrar):")
    print(best.to_string(index=False))
    print(f"\n# wrote {dest}")


if __name__ == "__main__":
    main()
