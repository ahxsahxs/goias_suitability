"""Regenerate the diagnostic CSVs that feed fig_4_10 / fig_4_11 / fig_4_12.

  zoning_kselect.csv    — cluster-validity + stability sweep over k (fig_4_10)
  factor_variance.csv   — per-segment factor share of suitability variance (fig_4_11)
  factor_variance_theme.csv — theme-grouped roll-up of the above (climate /
                           terrain+soil / other), raw prefix-based grouping and a
                           thematically-relabelled one (clim_soil_moist -> soil);
                           offline pandas only, no new GEE compute
  theme_roughness.csv   — spatial local-std of climate vs. terrain/soil, per
                           window radius (fig_4_12; revision point 5 companion
                           to factor_variance.csv's pooled decomposition)

The first two are normally emitted as a side effect of the heavy re-export
cascades (``tools/run_conservation_recal.py`` Stage 4 and
``tools/run_ws_analysis.py`` D1). This tool reproduces *only* those computations
from the already-built assets — no asset is written, no export is submitted. The
zoning sweep is deterministic (seed=42) and label-identical to the cascade; the
variance decomposition and the roughness decomposition use the same
capped-sample pattern.

Output goes where ``tools/make_figures.py`` looks for it: ``$SCRATCHPAD`` if set,
otherwise ``thesis/Chapters/``.

Run:
    EE_PROJECT=probformer uv run python tools/gen_diag_csvs.py [zoning|variance|roughness|all]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ee  # noqa: E402
import pandas as pd  # noqa: E402

import utils  # noqa: E402
import external  # noqa: E402
import features  # noqa: E402
import membership  # noqa: E402
import zoning  # noqa: E402

P = utils.init()
AOI = utils.load_aoi(P)
SEG = utils.cfg("segments")
SEGS = list(SEG["segments"])
THESIS_DIR = Path(__file__).resolve().parent.parent / "thesis" / "Chapters"
OUT = Path(os.environ.get("SCRATCHPAD", str(THESIS_DIR)))
TS = 8
CAP = 4500


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def aid(n):
    return utils.asset_id(P, n)


# --- zoning_kselect.csv (mirrors run_conservation_recal.py Stage 4) ------------
def gen_zoning_kselect():
    z = ee.Image(aid("feature_stack_250m_z"))
    raw = ee.Image(aid("feature_stack_250m"))
    suit_a = ee.Image(aid("suit_present"))
    realized = ee.Image(aid("feat_realized"))
    frac_bands = [f"rl_{r}_frac" for r in
                  ("soybean", "sugarcane", "other_crops", "pasture", "native")]
    bands = zoning.ZONING_BANDS
    log("zoning: sample + PCA + k-sweep + gap + stability (seed=42) ...")
    sample = zoning.build_sample(z, raw, suit_a, AOI, bands, segments=SEGS, seed=42,
                                 extra=realized.select(frac_bands))
    df = zoning.fc_to_df(sample)
    X = zoning.cluster_matrix(df, bands)
    pca = zoning.fit_pca(X, var_keep=0.90)
    S = pca.transform(X)
    sweep = zoning.kmeans_sweep(S, ks=range(2, 21), seed=42)
    gap = zoning.gap_statistic(S, ks=range(2, 21), B=10, seed=42)
    stab = zoning.stability_sweep(S, ks=range(2, 21), B=20, seed=42)
    swp = sweep.merge(gap, on="k").merge(stab, on="k")
    out = OUT / "zoning_kselect.csv"
    swp.to_csv(out, index=False)
    log(f"  wrote {out}\n" + swp.round(3).to_string(index=False))


# --- factor_variance.csv (mirrors run_ws_analysis.py D1) ----------------------
def gen_factor_variance():
    stack = ee.Image(aid("feature_stack_250m"))
    lc = ee.Image(aid("feat_landcover"))
    lonlat = ee.Image.pixelLonLat()
    extras = {"sit_": ee.Image(aid("feat_siting")),
              "rl_": ee.Image(aid("feat_realized")),
              "cv_": ee.Image(aid("feat_conservation"))}

    def sample_df(image, n=CAP, seed=5, scale=250):
        feats = (image.addBands(lonlat)
                 .sample(region=AOI, scale=scale, numPixels=n, seed=seed,
                         dropNulls=True, tileScale=TS)
                 .getInfo()["features"])
        return pd.DataFrame([f["properties"] for f in feats])

    log("variance: per-segment factor-variance decomposition ...")
    rows = []
    for name in SEGS:
        seg = SEG["segments"][name]
        mem = membership.segment_membership_image(stack, lc, seg, SEG, extras)
        pol = seg["mask"]
        if pol == "available":
            mem = mem.updateMask(lc.select("mask_available"))
        elif pol == "exclude_only":
            mem = mem.updateMask(lc.select("mask_excluded").Not())
        df = sample_df(mem, n=CAP, seed=5)
        cols = [f"mem_{b}" for b in seg["factors"]]
        df = df.dropna(subset=cols)
        M = df[cols].to_numpy()
        w = [seg["factors"][b]["weight"] for b in seg["factors"]]
        arith = seg.get("aggregate", "geomean") == "arithmetic"
        shares = membership.variance_shares(M, w, arithmetic=arith)
        for b, wi, sh in zip(seg["factors"], w, shares):
            rows.append({"segment": name, "factor": b, "weight": round(wi, 3),
                         "variance_share": round(sh, 3)})
        top = sorted(zip(seg["factors"], shares), key=lambda t: -t[1])[:3]
        log(f"  {name:12s} top drivers: " + ", ".join(f"{b} {s:.2f}" for b, s in top))
    out = OUT / "factor_variance.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    log(f"  wrote {out}")


# --- factor_variance_theme.csv (theme-grouped roll-up of factor_variance.csv,
# offline pandas only — no new GEE compute) ------------------------------------
# clim_soil_moist is provenance-climate (TerraClimate water balance) but
# thematically a soil/root-zone-moisture variable, not a spatial climate
# gradient — flagged separately so a reader doesn't mistake cattle's high
# "climate" share for genuine climatic discrimination (see discussion §Discussão).
THEME_RELABEL = {"clim_soil_moist": "terrain_soil"}


def _variance_theme_group(factor):
    if factor in THEME_RELABEL:
        return THEME_RELABEL[factor]
    if factor.startswith("clim_"):
        return "climate"
    if factor.startswith(("terr_", "soil_")):
        return "terrain_soil"
    return "other"


def gen_factor_variance_theme():
    src = OUT / "factor_variance.csv"
    if not src.exists():
        src = THESIS_DIR / "factor_variance.csv"
    df = pd.read_csv(src)
    df["theme_raw"] = df["factor"].apply(
        lambda f: "climate" if f.startswith("clim_")
        else ("terrain_soil" if f.startswith(("terr_", "soil_")) else "other"))
    df["theme"] = df["factor"].apply(_variance_theme_group)
    raw = (df.pivot_table(index="segment", columns="theme_raw", values="variance_share",
                           aggfunc="sum", fill_value=0.0)
             .reindex(columns=["climate", "terrain_soil", "other"], fill_value=0.0)
             .add_prefix("raw_"))
    relabelled = (df.pivot_table(index="segment", columns="theme", values="variance_share",
                                  aggfunc="sum", fill_value=0.0)
                    .reindex(columns=["climate", "terrain_soil", "other"], fill_value=0.0)
                    .add_prefix("theme_"))
    out_df = raw.join(relabelled).round(3).reset_index()
    out = OUT / "factor_variance_theme.csv"
    out_df.to_csv(out, index=False)
    log(f"  wrote {out}\n" + out_df.to_string(index=False))


# --- theme_roughness.csv (Point 5: spatial climate vs. terrain/soil local
# variability, companion to factor_variance.csv's pooled decomposition) -------
RADII_M = [250, 750, 4750]   # native cell, cv_ruggedness's own radius, TerraClimate's native cell
THEME_PREFIX = {
    "climate": ("clim_",),
    "terrain_soil": ("terr_", "soil_"),
    "water": ("water_",),
    "phenology": ("phen_",),
    "access": ("access_",),
}


def gen_theme_roughness():
    z = ee.Image(aid("feature_stack_250m_z"))
    names = z.bandNames().getInfo()
    groups = {g: [b for b in names if b.startswith(prefixes)]
              for g, prefixes in THEME_PREFIX.items()}
    log(f"roughness: local stdDev per theme group at radii {RADII_M} m ...")
    lonlat = ee.Image.pixelLonLat()
    # One .sample() call per radius (not all 3 at once): the r=4750 m kernel
    # (~19 px, ~1100 px/window) across 34 bands times out as a single combined
    # request even at tileScale=8. Splitting keeps each interactive call small;
    # tileScale=16 gives extra headroom for the heaviest (largest-radius) call.
    frames = []
    for r_m in RADII_M:
        rough = features.theme_roughness_image(z, groups, [r_m])
        log(f"  sampling r={r_m} m ...")
        feats = (rough.addBands(lonlat)
                 .sample(region=AOI, scale=250, numPixels=CAP, seed=5,
                         dropNulls=True, tileScale=16)
                 .getInfo()["features"])
        pts = pd.DataFrame([f["properties"] for f in feats])
        frames.append(pts)
        if r_m == RADII_M[-1]:
            # fig_4_12 needs a spatial map at this (headline, TerraClimate-
            # anchor) radius, but a full-AOI raster render of this moving-
            # window computation exceeds getThumbURL's interactive compute/
            # size limits. Reuse these already-sampled points (same call that
            # feeds the headline ratio below) as the map's spatial support
            # instead of exporting a new EE asset just to render a thumbnail.
            headline_cols = ["longitude", "latitude",
                              f"rough_climate_r{r_m}", f"rough_terrain_soil_r{r_m}"]
            pts_out = OUT / "theme_roughness_points.csv"
            pts[headline_cols].dropna().to_csv(pts_out, index=False)
            log(f"  wrote {pts_out}")
    df = pd.concat(frames, ignore_index=True, sort=False)
    rough_cols = [c for c in df.columns if c.startswith("rough_")]
    long = (df.melt(value_vars=rough_cols, var_name="band", value_name="value")
            .dropna(subset=["value"]))
    parsed = long["band"].str.extract(r"rough_(?P<group>.+)_r(?P<radius_m>\d+)$")
    long = pd.concat([long.drop(columns="band"), parsed], axis=1)
    long["radius_m"] = long["radius_m"].astype(int)
    summary = (long.groupby(["group", "radius_m"])["value"]
               .agg(mean_std="mean", median_std="median", n="count")
               .reset_index()
               .sort_values(["radius_m", "group"]))
    out = OUT / "theme_roughness.csv"
    summary.to_csv(out, index=False)
    log(f"  wrote {out}\n" + summary.round(3).to_string(index=False))


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    OUT.mkdir(parents=True, exist_ok=True)
    log(f"=== diagnostic CSVs (project={P}) -> {OUT} ===")
    if what in ("zoning", "all"):
        gen_zoning_kselect()
    if what in ("variance", "all"):
        gen_factor_variance()
        gen_factor_variance_theme()
    if what in ("roughness", "all"):
        gen_theme_roughness()
    log("=== done ===")


if __name__ == "__main__":
    main()
