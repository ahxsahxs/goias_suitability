"""Headless build of every Earth Engine asset, Part 1 -> Part 13.

DAG (each stage is idempotent: it skips when its output asset exists, so an
interrupted run resumes on re-invocation):

  aoi -> feat_climate/terrain/soil/water/landcover/siting/conservation
      -> feature_stack_250m(_z) -> feat_realized
      -> suit_present/_comp/_sens (Part 9, weights from config/segments.yaml)
      -> zones_present (Part 10, needs calib_val_split)
      -> CMIP6 suit_future_*/delta_*/agreement_* (Part 11)
      -> realized_vs_potential (Part 13) -> municipal table (Part 12)

Environment (normally set by `pipeline.py build`):
  REBUILD_UNTIL  features|stack|realized|suit|zones|cmip6|all   stop after a stage
  REBUILD_FORCE  comma list of asset names (or "all") to rebuild even if present.
                 Forcing DELETES the asset before exporting: back up first.
  ZONE_K         pin the number of zones (read zoning_kselect.csv first)

Run:  EE_PROJECT=<your-project> uv run python pipeline.py build [--until ...]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ee  # noqa: E402
import utils  # noqa: E402
import features  # noqa: E402
import membership  # noqa: E402
import external  # noqa: E402
import cmip6  # noqa: E402
import zoning  # noqa: E402
from utils import log  # noqa: E402

PROJECT = utils.init()
SEG = utils.cfg("segments")
SEGS = list(SEG["segments"])
MUNICIPAL = utils.territory()["municipal_asset"]

FORCE = {n.strip() for n in os.environ.get("REBUILD_FORCE", "").split(",") if n.strip()}
FORCE_ALL = "all" in FORCE

# The holdout split was derived from `aoi` (block grid over its bounds) and from
# `feat_realized` (block roles). Re-exporting either while a half is selected would
# silently desynchronise calib_val_split from its own provenance -- refuse.
SPLIT_PINNED = {"aoi", "feat_realized"}
if os.environ.get("SPLIT_HALF") and (FORCE_ALL or SPLIT_PINNED & FORCE):
    raise SystemExit(
        f"REBUILD_FORCE would re-export {sorted(SPLIT_PINNED)}, which the calib/val "
        f"split is derived from, while SPLIT_HALF is set. Unset SPLIT_HALF and rebuild "
        f"the split afterwards (`pipeline.py split`), or drop them from REBUILD_FORCE.")

STAGES = ["features", "stack", "realized", "suit", "zones", "cmip6", "all"]
UNTIL = os.environ.get("REBUILD_UNTIL", "all").strip() or "all"
if UNTIL not in STAGES:
    raise SystemExit(f"REBUILD_UNTIL must be one of {STAGES}, got {UNTIL!r}")


def stop_after(stage):
    return STAGES.index(stage) >= STAGES.index(UNTIL)


def aid(name):
    return utils.asset_id(PROJECT, name)


def img(name):
    return ee.Image(aid(name))


def exists(name):
    """Skip decision: a forced asset counts as absent. (wait_for polls the raw
    existence instead, or it would never see a forced export land.)"""
    return False if (FORCE_ALL or name in FORCE) else utils.asset_exists(PROJECT, name)


def wait_for(names, tasks=(), timeout=28800):
    utils.wait_for(PROJECT, names, tasks=[t for t in tasks if t], timeout=timeout)


def export(image, name, region):
    log(f"  submit export {name}")
    return utils.export_image(image, PROJECT, name, region, overwrite=True)


def export_table(fc, name):
    log(f"  submit export {name}")
    return utils.export_table(fc, PROJECT, name, overwrite=True)


def main():
    log(f"=== rebuild Part 1->13 (project={PROJECT}, "
        f"territory={utils.territory()['name']}, until={UNTIL}) ===")

    # ---- Part 1: AOI (IBGE malha municipal) ---------------------------------
    utils.ensure_folder(PROJECT)
    if exists("aoi"):
        log("  aoi exists -- skip")
    else:
        wait_for("aoi", tasks=[export_table(features.aoi_dissolved_fc(), "aoi")])
    AOI = utils.load_aoi(PROJECT)
    log(f"  AOI area (km^2): {round(AOI.area(1000).divide(1e6).getInfo(), 1)}")

    # ---- Parts 2-7d: independent feature themes -----------------------------
    theme_jobs = [
        ("feat_climate", lambda: features.climate_features(AOI)),
        ("feat_terrain", lambda: features.terrain_features(AOI)),
        ("feat_soil", lambda: features.soil_features(AOI)),
        ("feat_water", lambda: features.water_features(AOI)),
        ("feat_landcover", lambda: features.landcover_features_mapbiomas(AOI)),
        ("feat_siting", lambda: features.siting_features(AOI)),
        ("feat_conservation", lambda: features.conservation_features(AOI)),
    ]
    theme_tasks = []
    for name, builder in theme_jobs:
        if exists(name):
            log(f"  {name} exists -- skip")
            continue
        theme_tasks.append(export(builder(), name, AOI))
    if theme_tasks:
        log("  waiting on Parts 2-7d feature exports ...")
        wait_for([n for n, _ in theme_jobs], tasks=theme_tasks, timeout=7200)
    if stop_after("features"):
        log("=== STOP after Parts 1-7d ===")
        return

    # ---- Part 8: feature stack (raw + z-scored) ------------------------------
    if exists("feature_stack_250m") and exists("feature_stack_250m_z"):
        log("  feature_stack_250m(_z) exist -- skip")
    else:
        raw, z = features.assemble_stack(features.load_stack_images(PROJECT), AOI)
        wait_for(["feature_stack_250m", "feature_stack_250m_z"],
                 tasks=[export(raw, "feature_stack_250m", AOI),
                        export(z, "feature_stack_250m_z", AOI)])
    if stop_after("stack"):
        log("=== STOP after Part 8 ===")
        return

    stack = img("feature_stack_250m")
    z = img("feature_stack_250m_z")
    lc = img("feat_landcover")

    # ---- Part 13 (early): feat_realized (suitability extras + zoning profiles)
    if exists("feat_realized"):
        log("  feat_realized exists -- skip")
    else:
        wait_for("feat_realized",
                 tasks=[export(external.realized_features(AOI), "feat_realized", AOI)])
    realized = img("feat_realized")
    if stop_after("realized"):
        log("=== STOP after feat_realized ===")
        return

    extras = {"sit_": img("feat_siting"), "rl_": realized, "cv_": img("feat_conservation")}

    # ---- Part 9: suitability + comparative + sensitivity ---------------------
    present = ["suit_present", "suit_present_comp", "suit_present_sens"]
    suit_tasks = []
    if all(exists(n) for n in present):
        log("  suit_present/_comp/_sens exist -- skip")
    else:
        suit = membership.suit_present(stack, lc, SEG, extras)
        comp = membership.comparative_present(suit, AOI, SEGS, scale=1000)
        sens = membership.sensitivity_present(stack, lc, SEG, extras)
        suit_tasks = [export(suit, "suit_present", AOI),
                      export(comp, "suit_present_comp", AOI),
                      export(sens, "suit_present_sens", AOI)]
    wait_for("suit_present", tasks=suit_tasks)   # zoning stratifies on it
    suit_a = img("suit_present")
    if stop_after("suit"):
        wait_for(present, tasks=suit_tasks)      # don't return with _comp/_sens in flight
        log("=== STOP after Part 9 ===")
        return

    # ---- Part 10: zoning (offline sklearn on a calib-fitted PCA) -------------
    if exists("zones_present"):
        log("  zones_present exists -- skip")
    else:
        log("  zoning: stratified sample + PCA + k=2..20 panel ...")
        bands = zoning.ZONING_BANDS
        df, pca, S, calib = zoning.holdout_sample(
            z, stack, suit_a, AOI, utils.split_image(PROJECT), realized, SEGS)
        log(f"  sample n={len(df)}  calib={int(calib.sum())}  val={int((~calib).sum())}")
        swp = zoning.kselect_panel(S, df["split"].to_numpy())
        kcsv = utils.out_path("zoning_kselect.csv")
        swp.to_csv(kcsv, index=False)
        log(f"  wrote {kcsv}\n" + swp.round(3).to_string(index=False))

        # Silhouette is near-flat, so argmax alone is not a decision: read the
        # panel and pin K with ZONE_K. The fallback uses the HOLDOUT column.
        if os.environ.get("ZONE_K"):
            K = int(os.environ["ZONE_K"])
            log(f"  K = {K} (pinned via ZONE_K)")
        else:
            cand = swp[swp.k >= 3]
            K = int(cand.loc[cand.silhouette_val.idxmax(), "k"])
            log(f"  K = {K} (fallback argmax silhouette_val, NOT pinned; "
                f"PCs={pca.n_components_}) -- review the panel and set ZONE_K")
        # Centroids from the calibration half; zones canonically numbered by
        # descending mean elevation; the raster covers the whole AOI.
        km = zoning.fit_kmeans(S[calib], K, seed=42,
                               order_by=df.loc[calib, zoning.CANONICAL_ORDER_BAND])
        pc_img = zoning.pca_project_image(z, bands, zoning.theme_weight_vector(bands), pca)
        zones = zoning.nearest_centroid_image(pc_img, zoning.pc_names(pca),
                                              km.cluster_centers_)
        prof = zoning.profile_zones(df, km.predict(S), bands, SEGS,
                                    realized_fracs=zoning.REALIZED_FRAC_BANDS)
        prof.to_csv(utils.out_path("zone_profiles.csv"), index=False)
        log("  zone profiles:\n" + prof[["zone", "n", "comparative_segment",
            "dominant_segment", "top_features"]].to_string(index=False))
        wait_for("zones_present", tasks=[export(zones.toByte(), "zones_present", AOI)])
    if stop_after("zones"):
        log("=== STOP after Part 10 ===")
        return

    # ---- Part 11: CMIP6 (independent of zones) -------------------------------
    cc = utils.cfg()["cmip6"]
    combos = [(s, w) for s in cc["scenarios"] for w in cc["windows"]]
    fut_names = [f"suit_future_{s}_{w}" for s, w in combos]
    delta_names = [f"delta_{s}_{w}" for s, w in combos]
    agree_names = [f"agreement_{s}_{w}" for s, w in combos]
    cmip_names = fut_names + delta_names + agree_names
    cmip_tasks = []
    if all(exists(n) for n in cmip_names):
        log("  CMIP6 suit_future/delta/agreement all exist -- skip")
    else:
        base = cmip6.baseline_monthly(AOI)
        sp_re = cmip6.suit_present_rederived(PROJECT, AOI, lc, SEG, extras=extras)
        for ssp, win_name in combos:
            win = cc["windows"][win_name]
            if not (exists(f"suit_future_{ssp}_{win_name}")
                    and exists(f"delta_{ssp}_{win_name}")):
                sf = cmip6.suit_future(PROJECT, cc["models"], ssp, win, AOI, lc, SEG,
                                       base=base, extras=extras)
                cmip_tasks.append(export(sf, f"suit_future_{ssp}_{win_name}", AOI))
                cmip_tasks.append(export(cmip6.delta(sf, sp_re, SEGS),
                                         f"delta_{ssp}_{win_name}", AOI))
        for ssp, win_name in combos:
            if not exists(f"agreement_{ssp}_{win_name}"):
                ag = cmip6.agreement(PROJECT, cc["models"], ssp, cc["windows"][win_name],
                                     AOI, sp_re, lc, SEG, base=base, extras=extras)
                cmip_tasks.append(export(ag, f"agreement_{ssp}_{win_name}", AOI))
    if stop_after("cmip6"):
        log("  waiting on CMIP6 exports ...")
        wait_for(cmip_names, tasks=cmip_tasks)
        log("=== STOP after Part 11 ===")
        return

    # ---- Part 13: realized_vs_potential --------------------------------------
    t_uu = None
    if exists("realized_vs_potential"):
        log("  realized_vs_potential exists -- skip")
    else:
        uu = external.underutilization(suit_a, realized, SEGS)
        t_uu = export(uu.toByte(), "realized_vs_potential", AOI)

    # ---- Part 12: municipal aggregation (needs zones + a delta asset) -------
    wait_for(["zones_present", "delta_ssp585_2051_2070"], tasks=cmip_tasks)
    t_muni = None
    if exists(MUNICIPAL):
        log(f"  {MUNICIPAL} exists -- skip")
    else:
        agg = (suit_a.select([f"suit_{s}" for s in SEGS])
               .addBands(img("zones_present").rename("zone"))
               .addBands(img("delta_ssp585_2051_2070")))
        t_muni = export_table(external.municipal_means(external.municipal_fc(), agg),
                              MUNICIPAL)

    log("  waiting on CMIP6 + realized_vs_potential + municipal table ...")
    wait_for(cmip_names + ["realized_vs_potential", MUNICIPAL],
             tasks=cmip_tasks + [t_uu, t_muni])
    log("=== REBUILD COMPLETE (Parts 1-13) ===")
    log("Next: pipeline.py verify, then pipeline.py validate (Part 14)")


if __name__ == "__main__":
    main()
