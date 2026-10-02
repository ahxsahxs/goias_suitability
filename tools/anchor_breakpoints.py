"""Empirical breakpoint + discriminating-power anchoring for Part 9.

Read-only. Two jobs, selected by the CLI argument:

``percentiles`` (default)
    Percentile distributions of every fuzzy-membership factor, over the
    AOI-available land AND over each segment's realized MapBiomas pixels. This
    is the "check the band's real range before trusting a breakpoint" step.

``discrimination``
    The evidence the weight derivation runs on. Per segment x factor it reduces
    the fuzzy MEMBERSHIP (not the raw band) to:

      * ``sigma_mu_available`` -- the spatial standard deviation of mu over the
        reference population. This is ``d`` in the regional adaptation
        ``w = normalize(w_lit * d**lambda)`` of tools/derive_weights.py.
      * ``frac_saturated`` / ``frac_vetoed`` -- the share of the population at
        mu = 1 and at mu = 0, which exposes silent global deflators and
        zero-inflated vetoes directly rather than by inference.

``sigma(mu)`` replaces the ad hoc ``iqr/span`` ratio used previously, which was
computed by hand outside the repository, depended on the arbitrary width of the
breakpoint span in its own denominator, and ignored the plateau of an interval
shape. sigma(mu) is dimensionless, lies in [0, 0.5], and goes to zero on its own
for a saturated or spatially constant factor -- which is exactly the property the
adaptation rule needs.

It NEVER writes an Earth Engine asset. The realized masks only *report*; ``d`` is
taken from the `available` population alone, so land use never enters the
calibration (CLAUDE.md section 7).

Run::

    EE_PROJECT=probformer uv run python tools/anchor_breakpoints.py percentiles
    EE_PROJECT=probformer uv run python tools/anchor_breakpoints.py discrimination

Percentiles go to ``$SCRATCHPAD`` (or CWD); the discrimination tables are
committed artifacts under ``thesis/Chapters/``.
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
import membership  # noqa: E402

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


# --- discriminating power: sigma(mu) per segment x factor --------------------
# Realized MapBiomas role code per segment (external.ROLE_CODES); solar has no
# realized class of its own, so it is reported over available land only.
REALIZED_ROLE = {
    "soybean": 1, "sugarcane": 2, "other_crops": 3,
    "pisciculture": 4, "cattle": 5, "conservation": 6, "solar": None,
}


def _mem_stats(M, geom, mask, scale):
    """sigma(mu), mean(mu), saturated and vetoed fractions, per band of ``M``."""
    src = M.updateMask(mask) if mask is not None else M
    rr = dict(geometry=geom, scale=scale, maxPixels=int(1e13),
              bestEffort=True, tileScale=16)
    sd = src.reduceRegion(reducer=ee.Reducer.stdDev(), **rr).getInfo()
    flags = src.addBands(
        src.gte(0.999).rename([f"sat__{b}" for b in M.bandNames().getInfo()])
    ).addBands(
        src.lte(0.001).rename([f"vet__{b}" for b in M.bandNames().getInfo()])
    )
    mn = flags.reduceRegion(reducer=ee.Reducer.mean(), **rr).getInfo()
    return sd, mn


def discrimination():
    """Write thesis/Chapters/factor_discrimination.csv + breakpoint_anchoring.csv."""
    project = utils.init()
    aoi = utils.load_aoi(project)
    scale = int(os.environ.get("ANCHOR_SCALE", "1000"))
    seg_cfg = utils.cfg("segments")
    print(f"# discrimination over AOI @ {scale} m (project={project})")

    stack = ee.Image(utils.asset_id(project, "feature_stack_250m"))
    lc = features.landcover_features_mapbiomas(aoi)
    realized = ee.Image(utils.asset_id(project, "feat_realized"))
    extras = {
        "sit_": ee.Image(utils.asset_id(project, "feat_siting")),
        "cv_": ee.Image(utils.asset_id(project, "feat_conservation")),
        "rl_": realized,
    }
    avail = lc.select("mask_available")
    role = realized.select("rl_role")

    rows, anchor_rows = [], []
    for name, seg in seg_cfg["segments"].items():
        print(f"  -> {name} ...", flush=True)
        M = membership.segment_membership_image(stack, lc, seg, seg_cfg, extras)
        sd_a, mn_a = _mem_stats(M, aoi, avail, scale)
        code = REALIZED_ROLE.get(name)
        sd_r = _mem_stats(M, aoi, role.eq(code), scale)[0] if code else {}
        for f, spec in seg["factors"].items():
            b = f"mem_{f}"
            rows.append({
                "segment": name, "factor": f, "role": spec.get("role", "limiting"),
                "type": spec["type"], "points": str(spec["points"]),
                "sigma_mu_available": sd_a.get(b),
                "sigma_mu_realized": sd_r.get(b),
                "mean_mu_available": mn_a.get(b),
                "frac_saturated": mn_a.get(f"sat__{b}"),
                "frac_vetoed": mn_a.get(f"vet__{b}"),
            })
            anchor_rows.append({
                "segment": name, "factor": f, "basis": spec.get("basis"),
                "source": spec.get("source"), "locator": spec.get("locator"),
                "type": spec["type"], "points_adotados": str(spec["points"]),
            })

    out = os.path.join(os.path.dirname(__file__), "..", "thesis", "Chapters")
    out = os.environ.get("SCRATCHPAD", os.path.normpath(out))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(out, "factor_discrimination.csv"), index=False)
    pd.DataFrame(anchor_rows).to_csv(
        os.path.join(out, "breakpoint_anchoring.csv"), index=False)
    pd.set_option("display.width", 200, "display.max_columns", 20)
    print("\n", df.to_string(index=False))
    print(f"\n# wrote factor_discrimination.csv + breakpoint_anchoring.csv -> {out}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "percentiles"
    if mode == "discrimination":
        discrimination()
    elif mode == "percentiles":
        main()
    else:
        raise SystemExit(f"unknown mode {mode!r}; use percentiles | discrimination")
