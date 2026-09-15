"""Empirical breakpoint anchoring for the RECONCEPTUALIZED conservation segment (WS-A).

Read-only percentile audit of the conservation factors over (a) ALL land of GO+DF
(conservation is unmasked — mask: none) and (b) realized native-vegetation pixels
(MapBiomas role==native), so each moving breakpoint can be set inside the variable's
empirical envelope — the same discipline as tools/anchor_breakpoints.py. NEVER writes
an asset; the native mask only *informs* the expert breakpoints (guardrail intact).

Factors:
  cv_pa_dist, cv_ruggedness, cv_carbon   (feat_conservation side bands)
  clim_aridity, clim_twarm_q             (STACK, MOVING under CMIP6)
  terr_twi, water_drain_density, terr_slope  (STACK, kept)

Run:  EE_PROJECT=probformer ../.venv/bin/python tools/anchor_conservation.py
Out:  <scratchpad or CWD>/anchor_conservation.csv + a printed summary.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import ee  # noqa: E402
import pandas as pd  # noqa: E402

import utils  # noqa: E402
import features  # noqa: E402
import external  # noqa: E402

PCTLS = [5, 10, 25, 50, 75, 90, 95]
STACK_BANDS = ["clim_aridity", "clim_twarm_q", "terr_twi", "water_drain_density", "terr_slope"]
CV_BANDS = ["cv_pa_dist", "cv_ruggedness", "cv_carbon"]


def pctl_over(img, geom, mask, scale):
    src = img.updateMask(mask) if mask is not None else img
    return src.reduceRegion(
        reducer=ee.Reducer.percentile(PCTLS), geometry=geom, scale=scale,
        maxPixels=int(1e13), bestEffort=True, tileScale=16,
    ).getInfo()


def main():
    project = utils.init()
    aoi = utils.load_aoi(project)
    scale = int(os.environ.get("ANCHOR_SCALE", "1000"))
    print(f"# conservation anchoring over AOI @ {scale} m (project={project})")

    stack = ee.Image(utils.asset_id(project, "feature_stack_250m"))
    # prefer the cached feat_conservation asset (the live WDPA distance-transform +
    # biomass graphs are too heavy to reduce inline — "Object too large"); fall back
    # to the live builder only if the asset isn't exported yet.
    cid = utils.asset_id(project, "feat_conservation")
    try:
        ee.data.getAsset(cid)
        consv = ee.Image(cid)
        print("  (using cached feat_conservation asset)")
    except ee.EEException:
        consv = features.conservation_features(aoi)
        print("  (feat_conservation asset absent — using live builder)")
    realized = external.realized_features(aoi)
    role = realized.select("rl_role")

    factors_img = stack.select(STACK_BANDS).addBands(consv.select(CV_BANDS))
    bands = factors_img.bandNames().getInfo()

    masks = {
        "all_land": None,                 # conservation is unmasked (mask: none)
        "realized_native": role.eq(external.ROLE_CODES["native"]),
    }

    rows = []
    for label, mask in masks.items():
        print(f"  -> reducing over {label} ...", flush=True)
        stats = pctl_over(factors_img, aoi, mask, scale)
        for band in bands:
            rows.append({"mask": label, "field": band,
                         **{f"p{p}": stats.get(f"{band}_p{p}") for p in PCTLS}})

    df = pd.DataFrame(rows)
    scratch = os.environ.get("SCRATCHPAD", os.getcwd())
    out = os.path.join(scratch, "anchor_conservation.csv")
    df.to_csv(out, index=False)
    pd.set_option("display.width", 220, "display.max_columns", 20)
    print("\n", df.round(3).to_string(index=False))
    print(f"\n# wrote {out}")


if __name__ == "__main__":
    main()
