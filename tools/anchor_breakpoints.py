"""Empirical breakpoint + weight anchoring (T7/T8/T10 recalibration, 2026-09).

Read-only. Pulls percentile distributions of the fuzzy-membership factors, over
the AOI-available land AND over each segment's realized MapBiomas pixels, plus
present suitability quantiles at those realized pixels. This is the "verify
against a percentile reduceRegion before trusting a breakpoint or a weight" step
(CLAUDE.md §11 / §10 revision cycle). It NEVER writes an asset and never feeds
land use into the model — the realized masks only *inform* the expert
calibration (breakpoints AND, as of this revision, AHP weights).

**2026-09 extension** — the original TARGET_BANDS covered only the crop/cattle/
solar-srad/water_dist factors touched by the 2026-07-14 recalibration; it left
every conservation factor (`cv_*`, `terr_twi`, `rl_native_frac`) and part of
solar (`sit_clearness`, `terr_northing`, `access_logtt`) and `water_drain_density`
uncovered — some of those are marked "ANCHORED 2026-07-25" in `segments.yaml`
despite this script never having computed them (an earlier/manual pass). This
run now covers **every** segment/factor, and each row also carries `iqr`
(P75-P25) so a factor's *discriminating power* can be read off directly: an IQR
that is small relative to the segment's own breakpoint span in `segments.yaml`
means that factor is close to spatially constant in GO/DF and should carry a
lower AHP weight, regardless of its literature importance — the same reasoning
already applied ad hoc to cattle/solar's climate factors in 2026-07-14, now
applied systematically to all 7 segments as part of resolving T8/T10 together
(see the plan's Fase 4). CROP_MASKS also now covers pisciculture (role 4) and
native/conservation (role 6), previously missing.

Run:  EE_PROJECT=probformer uv run python tools/anchor_breakpoints.py
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
import features  # noqa: E402

# Percentiles reported per field.
PCTLS = [5, 10, 25, 50, 75, 90, 95]

# Stack factors (present in feature_stack_250m) whose breakpoints/weights are
# reviewed this iteration.
TARGET_BANDS = [
    # solar
    "clim_srad", "terr_northing", "access_logtt",
    # pisciculture / solar water proximity
    "water_dist",
    # cattle forage grading
    "clim_soil_moist", "clim_dry_months", "soil_soc",
    # crop recalibration factors
    "clim_pr_annual", "terr_slope", "soil_ph", "clim_twarm_q", "clim_aridity",
    "soil_clay", "clim_pr_cv", "clim_gdd", "soil_awc",
    # conservation stack-side factors (water/terrain themes; cv_*/rl_* handled
    # separately below, since they live in feat_conservation/realized_features,
    # not feature_stack_250m)
    "terr_twi", "water_drain_density",
]

# Side-image factors not present in feature_stack_250m: asset name -> band list.
# feat_conservation (Part 7d) and feat_siting (Part 7c) are the two `cv_`/`sit_`
# routing sources (src/membership._source_image via segments.yaml's `extras`).
SIDE_ASSETS = {
    "feat_conservation": ["cv_pa_dist", "cv_ruggedness", "cv_carbon"],
    "feat_siting": ["sit_clearness"],
}

# GSW occurrence thresholds for a seasonal-inclusive distance-to-water band.
# 80 == the current permanent-water definition (features.water_features).
SEAS_THRESHOLDS = [80, 50, 25, 10]

# realized role codes (external.ROLE_CODES): soybean=1 sugarcane=2 other_crops=3
#                                            pisciculture=4 pasture=5 native=6
# 2026-09: added pisciculture (4) and native/conservation (6) — previously
# missing, so those two segments had no realized-pixel percentile column.
CROP_MASKS = {
    "available": None,                 # filled below with mask_available
    "realized_soybean": 1,
    "realized_sugarcane": 2,
    "realized_other_crops": 3,
    "realized_pisciculture": 4,
    "realized_pasture": 5,
    "realized_native": 6,
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
    # T10 (2026-09): build the MapBiomas-sourced mask in memory rather than
    # loading the cached `feat_landcover` asset, which still reflects the
    # pre-T10 ESA WorldCover source until the Fase-4c rebuild — so this
    # diagnostic (and the calibration it feeds) is checked against the mask
    # that will actually be exported, not the one about to be replaced.
    lc = features.landcover_features_mapbiomas(aoi)
    realized = external.realized_features(aoi)
    role = realized.select("rl_role")

    gsw = ee.Image(utils.cfg()["water"]["gsw"]).select("occurrence")
    seas = ee.Image.cat([seasonal_dist(gsw, t) for t in SEAS_THRESHOLDS])

    side_imgs = [
        ee.Image(utils.asset_id(project, asset)).select(bands)
        for asset, bands in SIDE_ASSETS.items()
    ]

    # analysis image: stack factors + seasonal-water distances + side-image
    # factors (feat_conservation/feat_siting) + conservation's one sanctioned
    # land-cover factor (rl_native_frac, from realized_features — never a
    # generic land-cover band, see segments.yaml's guardrail note).
    factors_img = (
        stack.select(TARGET_BANDS)
        .addBands(seas)
        .addBands(realized.select("rl_native_frac"))
        .addBands(side_imgs)
    )

    masks = {"available": lc.select("mask_available")}
    for label, code in CROP_MASKS.items():
        if code is not None:
            masks[label] = role.eq(code)

    rows = []
    for label, mask in masks.items():
        print(f"  -> reducing over {label} ...", flush=True)
        stats = pctl_over(factors_img, aoi, mask, scale)
        for band in factors_img.bandNames().getInfo():
            p = {f"p{q}": stats.get(f"{band}_p{q}") for q in PCTLS}
            iqr = (p["p75"] - p["p25"]) if p["p75"] is not None and p["p25"] is not None else None
            rows.append({"mask": label, "field": band, **p, "iqr": iqr})

    # present suitability quantiles at each segment's realized pixels (S3/N
    # lower edge) — now also pisciculture and conservation (native), previously
    # missing (T7 coverage gap closed as part of the 2026-09 Fase-4 revision).
    suit_at = {
        "suit_soybean": ("realized_soybean", 1),
        "suit_sugarcane": ("realized_sugarcane", 2),
        "suit_other_crops": ("realized_other_crops", 3),
        "suit_pisciculture": ("realized_pisciculture", 4),
        "suit_conservation": ("realized_native", 6),
    }
    for sb, (label, code) in suit_at.items():
        print(f"  -> suitability quantiles: {sb} at {label} ...", flush=True)
        stats = pctl_over(suit.select(sb), aoi, role.eq(code), scale)
        p = {f"p{q}": stats.get(f"{sb}_p{q}") for q in PCTLS}
        iqr = (p["p75"] - p["p25"]) if p["p75"] is not None and p["p25"] is not None else None
        rows.append({"mask": label, "field": sb, **p, "iqr": iqr})

    df = pd.DataFrame(rows)
    scratch = os.environ.get("SCRATCHPAD", os.getcwd())
    out = os.path.join(scratch, "anchor_breakpoints.csv")
    df.to_csv(out, index=False)
    pd.set_option("display.width", 200, "display.max_columns", 20)
    print("\n", df.to_string(index=False))
    print(f"\n# wrote {out}")
    print(
        "\n# NOTE: `iqr` (P75-P25) is the raw spread over each mask. To judge a "
        "factor's discriminating power, compare it to that factor's OWN "
        "breakpoint span in config/segments.yaml (b-a for increasing/decreasing, "
        "d-a for range) for the specific segment under review — the same band "
        "(e.g. clim_pr_annual) has a different literature span per segment, so "
        "this script deliberately does not hardcode segment-specific ratios."
    )


if __name__ == "__main__":
    main()
