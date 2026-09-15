"""Empirical breakpoint anchoring for the robustness+recalibration iteration.

Read-only. Pulls percentile distributions of the stack factors whose fuzzy-
membership breakpoints move in this iteration, over the AOI-available land AND
over each crop's realized MapBiomas pixels, plus present suitability quantiles at
those realized pixels. This is the "verify against a percentile reduceRegion
before trusting new breakpoints" step (CLAUDE.md 11 / recalibration_plan 2.1 /
robustness_plan 4). It NEVER writes an asset and never feeds land use into the
model — the realized masks only *inform* the expert breakpoints.

Run:  EE_PROJECT=probformer ../.venv/bin/python tools/anchor_breakpoints.py
Out:  <scratchpad or CWD>/anchor_breakpoints.csv  + a printed summary.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import ee  # noqa: E402
import pandas as pd  # noqa: E402

import utils  # noqa: E402
import external  # noqa: E402

# Percentiles reported per field.
PCTLS = [5, 10, 25, 50, 75, 90, 95]

# Stack factors whose breakpoints are candidates for change this iteration.
TARGET_BANDS = [
    # solar
    "clim_srad",
    # pisciculture / solar water proximity
    "water_dist",
    # cattle forage grading
    "clim_soil_moist", "clim_dry_months", "soil_soc",
    # crop recalibration factors
    "clim_pr_annual", "terr_slope", "soil_ph", "clim_twarm_q", "clim_aridity",
    "soil_clay", "clim_pr_cv", "clim_gdd", "soil_awc",
]

# GSW occurrence thresholds for a seasonal-inclusive distance-to-water band.
# 80 == the current permanent-water definition (features.water_features).
SEAS_THRESHOLDS = [80, 50, 25, 10]

# realized role codes (external.ROLE_CODES): soybean=1 sugarcane=2 other_crops=3
#                                            pisciculture=4 pasture=5 native=6
CROP_MASKS = {
    "available": None,                 # filled below with mask_available
    "realized_soybean": 1,
    "realized_sugarcane": 2,
    "realized_other_crops": 3,
    "realized_pasture": 5,
}


def seasonal_dist(occ, threshold):
    """Distance (m) to water present > `threshold`% of the time, on the 250 m grid."""
    proj = utils.grid_projection()
    wet = occ.gt(threshold).unmask(0).reproject(proj)
    return (
        wet.fastDistanceTransform(1024, "pixels").sqrt()
        .multiply(utils.scale_m())
        .rename(f"water_dist_occ{threshold}")
    )


def pctl_over(img, geom, mask, scale):
    """Percentiles of every band of `img` over `geom`, optionally masked."""
    src = img.updateMask(mask) if mask is not None else img
    red = ee.Reducer.percentile(PCTLS)
    return src.reduceRegion(
        reducer=red, geometry=geom, scale=scale, maxPixels=int(1e13),
        bestEffort=True, tileScale=16,
    ).getInfo()


def main():
    project = utils.init()
    aoi = utils.load_aoi(project)
    scale = int(os.environ.get("ANCHOR_SCALE", "1000"))
    print(f"# anchoring over AOI @ {scale} m (project={project})")

    stack = ee.Image(utils.asset_id(project, "feature_stack_250m"))
    suit = ee.Image(utils.asset_id(project, "suit_present"))
    lc = ee.Image(utils.asset_id(project, "feat_landcover"))
    realized = external.realized_features(aoi)
    role = realized.select("rl_role")

    gsw = ee.Image(utils.cfg()["water"]["gsw"]).select("occurrence")
    seas = ee.Image.cat([seasonal_dist(gsw, t) for t in SEAS_THRESHOLDS])

    # analysis image: target stack factors + seasonal-water distances
    factors_img = stack.select(TARGET_BANDS).addBands(seas)

    masks = {
        "available": lc.select("mask_available"),
        "realized_soybean": role.eq(1),
        "realized_sugarcane": role.eq(2),
        "realized_other_crops": role.eq(3),
        "realized_pasture": role.eq(5),
    }

    rows = []
    for label, mask in masks.items():
        print(f"  -> reducing over {label} ...", flush=True)
        stats = pctl_over(factors_img, aoi, mask, scale)
        for band in factors_img.bandNames().getInfo():
            rows.append({"mask": label, "field": band,
                         **{f"p{p}": stats.get(f"{band}_p{p}") for p in PCTLS}})

    # present suitability quantiles at each crop's realized pixels (S3/N lower edge)
    suit_at = {
        "suit_soybean": ("realized_soybean", 1),
        "suit_sugarcane": ("realized_sugarcane", 2),
        "suit_other_crops": ("realized_other_crops", 3),
    }
    for sb, (label, code) in suit_at.items():
        print(f"  -> suitability quantiles: {sb} at {label} ...", flush=True)
        stats = pctl_over(suit.select(sb), aoi, role.eq(code), scale)
        rows.append({"mask": label, "field": sb,
                     **{f"p{p}": stats.get(f"{sb}_p{p}") for p in PCTLS}})

    df = pd.DataFrame(rows)
    scratch = os.environ.get("SCRATCHPAD", os.getcwd())
    out = os.path.join(scratch, "anchor_breakpoints.csv")
    df.to_csv(out, index=False)
    pd.set_option("display.width", 200, "display.max_columns", 20)
    print("\n", df.to_string(index=False))
    print(f"\n# wrote {out}")


if __name__ == "__main__":
    main()
