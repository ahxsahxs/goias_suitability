"""Full headless rebuild, Part 1 -> Part 13 (2026-09-19).

Rebuilds the whole cascade from the AOI up, because Part 1 now derives the AOI
from the IBGE malha municipal mesh instead of GAUL (src/ibge_mesh.py) -- every
downstream export region shifts, however slightly, so everything that depends
on `aoi` must be re-exported, not just the T8/T10/recalibration-affected parts.

Combines in one pass:
  - the pending IBGE-mesh AOI rebuild (CLAUDE.md S4/S7),
  - T10 (feat_landcover now sourced from MapBiomas instead of ESA WorldCover),
  - T8 (larger/stratified sampling for zoning -- already in zoning.build_sample),
  - the 2026-09 fuzzy-membership/AHP recalibration (config/segments.yaml).

DAG (each stage idempotent: skips if its output asset already exists, so a
crash mid-run resumes cleanly on re-invocation):

  aoi -> feat_climate/terrain/soil/water/phenology/access/landcover/siting/conservation
       -> feature_stack_250m(_z)
       -> feat_realized (Part 13, needed by zoning profiling + suit extras)
       -> suit_present/_comp/_sens (Part 9)
       -> zones_present (Part 10, T8 stratified sample)
       -> CMIP6 suit_future_*/delta_*/agreement_* (Part 11)
       -> realized_vs_potential (Part 13)
       -> municipal_godf (Part 12, IBGE join key)

Run (background):  EE_PROJECT=probformer uv run python tools/run_rebuild_full.py
Monitor:            uv run earthengine task list   (+ the printed log)
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "src")

import ee  # noqa: E402
import utils  # noqa: E402
import features  # noqa: E402
import membership  # noqa: E402
import external  # noqa: E402
import cmip6  # noqa: E402
import zoning  # noqa: E402

PROJECT = utils.init()
SEG = utils.cfg("segments")
SEGS = list(SEG["segments"])


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def aid(name):
    return utils.asset_id(PROJECT, name)


def img(name):
    return ee.Image(aid(name))


# REBUILD_FORCE: comma-separated asset names (or "all") to rebuild even when the
# asset already exists. Each stage short-circuits on exists(), so without this the
# script can only ever fill gaps -- it cannot re-run a stage whose output is there.
# Forcing goes through utils.export_image(overwrite=True), which DELETES the asset
# up front and only then submits the export -- so a failed task leaves no asset at
# all. Always run tools/backup_assets.py first (CLAUDE.md S4).
FORCE = {n.strip() for n in os.environ.get("REBUILD_FORCE", "").split(",") if n.strip()}
FORCE_ALL = "all" in FORCE

# REBUILD_UNTIL: stop cleanly after a named stage instead of running to Part 12.
# Used to gate a from-scratch run: rebuild Parts 1-8, stop, diff the features
# against the backup (tools/diff_vs_backup.py), and only then let Part 9+ run.
STAGES = ["features", "stack", "realized", "suit", "zones", "cmip6", "all"]
UNTIL = os.environ.get("REBUILD_UNTIL", "all").strip() or "all"
if UNTIL not in STAGES:
    raise SystemExit(f"REBUILD_UNTIL must be one of {STAGES}, got {UNTIL!r}")


def stop_after(stage):
    """True when ``stage`` is the last one REBUILD_UNTIL asks for."""
    return STAGES.index(stage) >= STAGES.index(UNTIL)


def forced(name):
    return FORCE_ALL or name in FORCE


def asset_exists(name):
    """Raw server-side check: is the asset there right now?"""
    try:
        ee.data.getAsset(aid(name))
        return True
    except ee.EEException:
        return False


def exists(name):
    """Skip decision for a build stage -- a forced asset is treated as absent.

    Deliberately NOT what wait_for() uses: a forced asset is reported absent for as
    long as REBUILD_FORCE names it, so polling on this would never see the new export
    land. wait_for() calls asset_exists() instead.
    """
    return False if forced(name) else asset_exists(name)


def wait_for(names, tasks=None, timeout=28800, poll=45):
    names = [names] if isinstance(names, str) else names
    tasks = tasks or []
    t0 = time.time()
    while True:
        have = [n for n in names if asset_exists(n)]
        if len(have) == len(names):
            log(f"  ready: {', '.join(names)}")
            return
        for t in tasks:
            st = t.status()
            if st["state"] in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"task {st.get('description')} {st['state']}: "
                                   f"{st.get('error_message', '')}")
        if time.time() - t0 > timeout:
            raise TimeoutError(f"timeout waiting for {set(names) - set(have)}")
        time.sleep(poll)


def export(image, name, region):
    log(f"  submit export {name}")
    return utils.export_image(image, PROJECT, name, region, overwrite=True)


def export_table_fresh(fc, name):
    try:
        ee.data.deleteAsset(aid(name))
        log(f"  deleted stale {name}")
    except ee.EEException:
        pass
    log(f"  submit export {name}")
    return utils.export_table(fc, PROJECT, name)


def main():
    log(f"=== full rebuild Part 1->13 (project={PROJECT}) ===")

    # ---- Part 1: AOI (IBGE malha municipal) ---------------------------------
    utils.ensure_folder(PROJECT)
    if exists("aoi"):
        log("  aoi exists -- skip")
    else:
        t_aoi = export_table_fresh(features.aoi_dissolved_fc(), "aoi")
        wait_for("aoi", tasks=[t_aoi])
    AOI = utils.load_aoi(PROJECT)
    log(f"  AOI area (km^2): {round(AOI.area(1000).divide(1e6).getInfo(), 1)}")

    # ---- Parts 2-7d: independent feature themes -----------------------------
    theme_jobs = [
        ("feat_climate", lambda: features.climate_features(AOI)),
        ("feat_terrain", lambda: features.terrain_features(AOI)),
        ("feat_soil", lambda: features.soil_features(AOI)),
        ("feat_water", lambda: features.water_features(AOI)),
        ("feat_phenology", lambda: features.phenology_features(AOI)),
        ("feat_access", lambda: features.access_features(AOI)),
        ("feat_landcover", lambda: features.landcover_features_mapbiomas(AOI)),  # T10
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
        log("=== STOP after Parts 1-7d (REBUILD_UNTIL=features) ===")
        return

    # ---- Part 8: feature stack (raw + z-scored) ------------------------------
    if exists("feature_stack_250m") and exists("feature_stack_250m_z"):
        log("  feature_stack_250m(_z) exist -- skip")
    else:
        imgs = features.load_stack_images(PROJECT)
        raw, z = features.assemble_stack(imgs, AOI)
        t1 = export(raw, "feature_stack_250m", AOI)
        t2 = export(z, "feature_stack_250m_z", AOI)
        wait_for(["feature_stack_250m", "feature_stack_250m_z"], tasks=[t1, t2])

    if stop_after("stack"):
        log("=== STOP after Part 8 (REBUILD_UNTIL=stack) ===")
        log("Next: EE_PROJECT=probformer uv run python tools/diff_vs_backup.py "
            "--backup <folder> <assets...>")
        return

    stack = img("feature_stack_250m")
    z = img("feature_stack_250m_z")
    lc = img("feat_landcover")

    # ---- Part 13 (early): feat_realized (needed for extras + zoning profiling)
    if exists("feat_realized"):
        log("  feat_realized exists -- skip")
    else:
        realized_img = external.realized_features(AOI)
        t_r = export(realized_img, "feat_realized", AOI)
        wait_for("feat_realized", tasks=[t_r])
    realized = img("feat_realized")

    if stop_after("realized"):
        log("=== STOP after feat_realized (REBUILD_UNTIL=realized) ===")
        return

    siting = img("feat_siting")
    consv = img("feat_conservation")
    extras = {"sit_": siting, "rl_": realized, "cv_": consv}

    # ---- Part 9: suitability + comparative + sensitivity ---------------------
    present = ["suit_present", "suit_present_comp", "suit_present_sens"]
    if all(exists(n) for n in present):
        log("  suit_present/_comp/_sens exist -- skip")
        t_suit = None
    else:
        suit = membership.suit_present(stack, lc, SEG, extras)
        comp = membership.comparative_present(suit, AOI, SEGS, scale=1000)
        sens = membership.sensitivity_present(stack, lc, SEG, extras)
        t_suit = export(suit, "suit_present", AOI)
        export(comp, "suit_present_comp", AOI)
        export(sens, "suit_present_sens", AOI)
    wait_for("suit_present", tasks=[t_suit] if t_suit else [])
    suit_a = img("suit_present")

    if stop_after("suit"):
        log("=== STOP after Part 9 (REBUILD_UNTIL=suit) ===")
        log("Next: pick K from the full validity+stability panel, then rerun "
            "with ZONE_K=<k>.")
        return

    # ---- Part 10: zoning (offline sklearn; T8 stratified sample) -------------
    if exists("zones_present"):
        log("  zones_present exists -- skip")
    else:
        log("  zoning: stratified sample + PCA + k-sweep ...")
        frac_bands = [f"rl_{r}_frac" for r in
                      ("soybean", "sugarcane", "other_crops", "pasture", "native")]
        bands = zoning.ZONING_BANDS
        sample = zoning.build_sample(z, stack, suit_a, AOI, bands, segments=SEGS, seed=42,
                                     extra=realized.select(frac_bands))
        df = zoning.fc_to_df(sample)
        X = zoning.cluster_matrix(df, bands)
        pca = zoning.fit_pca(X, var_keep=0.90)
        S = pca.transform(X)
        # Full validity + stability panel over k = 2..20, identical to
        # tools/gen_diag_csvs.py:gen_zoning_kselect() -- which is the tool that
        # wrote thesis/Chapters/zoning_kselect.csv. The two used to disagree: this
        # script swept only k = 2..10 and computed no ARI, so the K it exported and
        # the K the thesis justified came from different procedures. One sweep now
        # serves both, and the CSV is written from the same run that exports the asset.
        ks = range(2, 21)
        sweep = zoning.kmeans_sweep(S, ks=ks, seed=42)
        gap = zoning.gap_statistic(S, ks=ks, B=10, seed=42)
        stab = zoning.stability_sweep(S, ks=ks, B=20, seed=42)
        swp = sweep.merge(gap, on="k").merge(stab, on="k")
        kcsv = os.path.join(os.path.dirname(__file__), "..", "thesis", "Chapters")
        kcsv = os.path.join(os.environ.get("SCRATCHPAD", os.path.normpath(kcsv)),
                            "zoning_kselect.csv")
        swp.to_csv(kcsv, index=False)
        log(f"  wrote {kcsv}")
        log("  k panel (decorrelated PC space):\n" + swp.round(3).to_string(index=False))

        # ZONE_K pins k deliberately (same mechanism as tools/rezone.py). The
        # silhouette here is near-flat, so argmax-silhouette alone is a coin flip
        # between adjacent k -- it is a fallback, not a decision procedure. Read the
        # panel (silhouette + Davies-Bouldin + gap + ARI) and pin the result.
        if os.environ.get("ZONE_K"):
            K = int(os.environ["ZONE_K"])
            log(f"  K = {K} (pinned via ZONE_K)")
        else:
            cand = swp[swp.k >= 3]
            K = int(cand.loc[cand.silhouette.idxmax(), "k"])
            log(f"  K = {K} (fallback: argmax silhouette over k>=3, NOT pinned) "
                f"(PCs={pca.n_components_}); review the panel above")
        km = zoning.fit_kmeans(S, K, seed=42)
        theme_w = zoning.theme_weight_vector(bands)
        pc_img = zoning.pca_project_image(z, bands, theme_w, pca)
        zones = zoning.nearest_centroid_image(pc_img, zoning.pc_names(pca), km.cluster_centers_)
        prof = zoning.profile_zones(df, km.labels_, bands, SEGS, realized_fracs=frac_bands)
        prof.to_csv("zone_profiles.csv", index=False)
        log("  zone profiles:\n" + prof[["zone", "n", "comparative_segment",
            "dominant_segment", "top_features"]].to_string(index=False))
        t_zones = export(zones.toByte(), "zones_present", AOI)
        wait_for("zones_present", tasks=[t_zones])

    if stop_after("zones"):
        log("=== STOP after Part 10 (REBUILD_UNTIL=zones) ===")
        return

    # ---- Part 11: CMIP6 (independent of zones) -------------------------------
    cc = utils.cfg()["cmip6"]
    fut_names = [f"suit_future_{s}_{w}" for s in cc["scenarios"] for w in cc["windows"]]
    delta_names = [f"delta_{s}_{w}" for s in cc["scenarios"] for w in cc["windows"]]
    agree_names = [f"agreement_{s}_{w}" for s in cc["scenarios"] for w in cc["windows"]]
    if all(exists(n) for n in fut_names + delta_names + agree_names):
        log("  CMIP6 suit_future/delta/agreement all exist -- skip")
        cmip_tasks = []
    else:
        base = cmip6.baseline_monthly(AOI)
        sp_re = cmip6.suit_present_rederived(PROJECT, AOI, lc, SEG, extras=extras)
        cmip_tasks = []
        for ssp in cc["scenarios"]:
            for win_name, win in cc["windows"].items():
                if exists(f"suit_future_{ssp}_{win_name}") and exists(f"delta_{ssp}_{win_name}"):
                    continue
                sf = cmip6.suit_future(PROJECT, cc["models"], ssp, win, AOI, lc, SEG,
                                       base=base, extras=extras)
                dl = cmip6.delta(sf, sp_re, SEGS)
                cmip_tasks.append(export(sf, f"suit_future_{ssp}_{win_name}", AOI))
                cmip_tasks.append(export(dl, f"delta_{ssp}_{win_name}", AOI))
        for ssp in cc["scenarios"]:
            for win_name, win in cc["windows"].items():
                if exists(f"agreement_{ssp}_{win_name}"):
                    continue
                ag = cmip6.agreement(PROJECT, cc["models"], ssp, win, AOI, sp_re, lc, SEG,
                                     base=base, extras=extras)
                cmip_tasks.append(export(ag, f"agreement_{ssp}_{win_name}", AOI))

    if stop_after("cmip6"):
        log("  waiting on CMIP6 exports ...")
        wait_for(fut_names + delta_names + agree_names, tasks=cmip_tasks)
        log("=== STOP after Part 11 (REBUILD_UNTIL=cmip6) ===")
        return

    # ---- Part 13: realized_vs_potential --------------------------------------
    if exists("realized_vs_potential"):
        log("  realized_vs_potential exists -- skip")
        t_uu = None
    else:
        uu = external.underutilization(suit_a, realized, SEGS)
        t_uu = export(uu.toByte(), "realized_vs_potential", AOI)

    # ---- Part 12: municipal aggregation (needs zones + a delta asset) -------
    wait_for(["zones_present", "delta_ssp585_2051_2070"], tasks=cmip_tasks)
    if exists("municipal_godf"):
        log("  municipal_godf exists -- skip")
        t_muni = None
    else:
        zones_a = img("zones_present").rename("zone")
        delta_a = img("delta_ssp585_2051_2070")
        agg = suit_a.select([f"suit_{s}" for s in SEGS]).addBands(zones_a).addBands(delta_a)
        muni = external.municipal_means(external.municipal_fc(), agg)
        t_muni = export_table_fresh(muni, "municipal_godf")

    log("  waiting on CMIP6 + realized_vs_potential + municipal_godf ...")
    wait_for(fut_names + delta_names + agree_names + ["realized_vs_potential", "municipal_godf"],
             tasks=cmip_tasks + ([t_uu] if t_uu else []) + ([t_muni] if t_muni else []))

    log("=== FULL REBUILD COMPLETE (Parts 1-13) ===")
    log("Next: EE_PROJECT=probformer uv run python tools/verify_assets.py")
    log("Then: EE_PROJECT=probformer uv run python tools/run_validation.py  (Part 14)")


if __name__ == "__main__":
    main()
