"""Re-export the conservation-affected goias assets under the 2026-07-25
conservation-reconceptualization config (docs/weaknesses_mitigation.md WS-A).

Adapted from tools/run_recal.py. Only the conservation segment changed, but it is
bundled into the 7-segment suit_present / CMIP6 images, so those are re-exported in
full; crops/cattle/solar/pisci bands are numerically identical to the current assets.
Cluster *assignments* are unchanged (conservation is not a clustering input), but the
sample is re-profiled with the new suit_present so the comparative-best label updates,
and the k-selection + stability diagnostics (WS-D) are emitted for the thesis.

New upstream asset: feat_conservation (cv_pa_dist / cv_ruggedness / cv_carbon), exported
separately beforehand and loaded here as a cached `cv_` side image (held static in CMIP6
exactly like sit_/rl_, so Δ isolates conservation's two moving climate factors
clim_aridity + clim_twarm_q).

DAG:
  feat_conservation ┐
  feat_siting ───────┼─> suit_present/comp/sens ─┬─> zones_present + profile ─┐
  feat_realized ─────┘   └─> CMIP6 (12) ────delta─┼─> municipal_godf (delete-first)
                          suit_present ─> realized_vs_potential ──────────────┘

Run (background):  EE_PROJECT=probformer ../.venv/bin/python tools/run_conservation_recal.py
Monitor:           ../.venv/bin/earthengine task list   (+ the printed log)
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
AOI = utils.load_aoi(PROJECT)
SEG = utils.cfg("segments")
SEGS = list(SEG["segments"])
SCRATCH = os.environ.get("SCRATCHPAD", os.getcwd())


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def aid(name):
    return utils.asset_id(PROJECT, name)


def img(name):
    return ee.Image(aid(name))


def exists(name):
    try:
        ee.data.getAsset(aid(name))
        return True
    except ee.EEException:
        return False


def wait_for(names, tasks=None, timeout=18000, poll=45):
    names = [names] if isinstance(names, str) else names
    tasks = tasks or []
    t0 = time.time()
    while True:
        have = [n for n in names if exists(n)]
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


def export(image, name):
    log(f"  submit export {name}")
    return utils.export_image(image, PROJECT, name, AOI, overwrite=True)


def main():
    log(f"=== conservation re-export (project={PROJECT}) ===")

    # ---- Stage 0: feat_conservation must exist (exported separately) --------
    if not exists("feat_conservation"):
        raise RuntimeError("feat_conservation asset missing — export it first "
                           "(features.conservation_features).")

    extras = {"sit_": img("feat_siting"), "rl_": img("feat_realized"),
              "cv_": img("feat_conservation")}
    lc = img("feat_landcover")
    stack = img("feature_stack_250m")

    # ---- Stage 2: present suitability + comparative + sensitivity -----------
    suit = membership.suit_present(stack, lc, SEG, extras)
    comp = membership.comparative_present(suit, AOI, SEGS, scale=1000)
    sens = membership.sensitivity_present(stack, lc, SEG, extras)
    t_suit = export(suit, "suit_present")
    export(comp, "suit_present_comp")
    export(sens, "suit_present_sens")

    # ---- Stage 3: CMIP6 (rederived present + static extras -> Δ) ------------
    base = cmip6.baseline_monthly(AOI)
    sp_re = cmip6.suit_present_rederived(PROJECT, AOI, lc, SEG, extras=extras)
    cc = utils.cfg()["cmip6"]
    cmip_tasks = []
    for ssp in cc["scenarios"]:
        for win_name, win in cc["windows"].items():
            sf = cmip6.suit_future(PROJECT, cc["models"], ssp, win, AOI, lc, SEG,
                                   base=base, extras=extras)
            dl = cmip6.delta(sf, sp_re, SEGS)
            cmip_tasks.append(export(sf, f"suit_future_{ssp}_{win_name}"))
            cmip_tasks.append(export(dl, f"delta_{ssp}_{win_name}"))
    for ssp in cc["scenarios"]:
        for win_name, win in cc["windows"].items():
            ag = cmip6.agreement(PROJECT, cc["models"], ssp, win, AOI, sp_re, lc, SEG,
                                 base=base, extras=extras)
            cmip_tasks.append(export(ag, f"agreement_{ssp}_{win_name}"))

    # ---- Stage 4: zoning re-profile + WS-D diagnostics ---------------------
    # Cluster assignments are UNCHANGED (stack untouched); we re-run deterministically
    # (seed=42) to (a) re-profile with the new suit_present conservation band and
    # (b) emit the k-selection + stability curves for the thesis k-defense (WS-D).
    wait_for("suit_present", tasks=[t_suit])
    log("  zoning: sample + PCA + k-sweep + stability ...")
    z = img("feature_stack_250m_z")
    suit_a = img("suit_present")
    realized = img("feat_realized")
    frac_bands = [f"rl_{r}_frac" for r in
                  ("soybean", "sugarcane", "other_crops", "pasture", "native")]
    bands = zoning.ZONING_BANDS
    sample = zoning.build_sample(z, stack, suit_a, AOI, bands, n=15000, seed=42,
                                 extra=realized.select(frac_bands))
    df = zoning.fc_to_df(sample)
    X = zoning.cluster_matrix(df, bands)
    pca = zoning.fit_pca(X, var_keep=0.90)
    S = pca.transform(X)
    sweep = zoning.kmeans_sweep(S, ks=range(2, 11), seed=42)
    gap = zoning.gap_statistic(S, ks=range(2, 11), B=10, seed=42)
    stab = zoning.stability_sweep(S, ks=range(2, 11), B=20, seed=42)
    swp = sweep.merge(gap, on="k").merge(stab, on="k")
    swp.to_csv(os.path.join(SCRATCH, "zoning_kselect.csv"), index=False)
    log("  k sweep (decorrelated PC space):\n" + swp.round(3).to_string(index=False))
    cand = swp[swp.k >= 3]
    K = int(cand.loc[cand.silhouette.idxmax(), "k"])
    log(f"  chosen K = {K} (PCs={pca.n_components_})")
    km = zoning.fit_kmeans(S, K, seed=42)
    theme_w = zoning.theme_weight_vector(bands)
    pc_img = zoning.pca_project_image(z, bands, theme_w, pca)
    zones = zoning.nearest_centroid_image(pc_img, zoning.pc_names(pca), km.cluster_centers_)
    prof = zoning.profile_zones(df, km.labels_, bands, SEGS, realized_fracs=frac_bands)
    prof.to_csv("zone_profiles.csv", index=False)
    log("  zone profiles:\n" + prof[["zone", "n", "comparative_segment",
        "dominant_segment", "top_features"]].to_string(index=False))
    t_zones = export(zones.toByte(), "zones_present")

    # ---- Stage 5: realized_vs_potential (RQ2) ------------------------------
    uu = external.underutilization(suit_a, realized, SEGS)
    t_uu = export(uu.toByte(), "realized_vs_potential")

    # ---- Stage 6: municipal aggregation (delete-first: export_table has no overwrite)
    wait_for(["zones_present", "delta_ssp585_2051_2070"], tasks=[t_zones] + cmip_tasks)
    zones_a = img("zones_present").rename("zone")
    delta_a = img("delta_ssp585_2051_2070")
    agg = suit_a.select([f"suit_{s}" for s in SEGS]).addBands(zones_a).addBands(delta_a)
    muni = external.municipal_means(external.municipal_fc(), agg)
    try:
        ee.data.deleteAsset(aid("municipal_godf"))
        log("  deleted stale municipal_godf (export_table has no overwrite)")
    except ee.EEException:
        pass
    log("  submit export municipal_godf")
    t_muni = utils.export_table(muni, PROJECT, "municipal_godf")

    # ---- wait for the remaining batch tasks --------------------------------
    log("  waiting on CMIP6 + realized + municipal to finish ...")
    wait_for([f"suit_future_{s}_{w}" for s in cc["scenarios"] for w in cc["windows"]]
             + [f"delta_{s}_{w}" for s in cc["scenarios"] for w in cc["windows"]]
             + [f"agreement_{s}_{w}" for s in cc["scenarios"] for w in cc["windows"]]
             + ["realized_vs_potential", "municipal_godf"],
             tasks=cmip_tasks + [t_uu, t_muni])

    log("=== ALL CONSERVATION RE-EXPORTS COMPLETE ===")
    log(f"chosen zoning K = {K}; zone_profiles.csv + zoning_kselect.csv written")


if __name__ == "__main__":
    main()
