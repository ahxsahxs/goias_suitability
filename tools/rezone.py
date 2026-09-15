"""Re-fit the zoning at a chosen k and re-export zones_present + municipal_godf.

The cascade's max-silhouette auto-pick is fragile when the silhouette is near-flat
(GO+DF is weakly clustered): k=7 and k=8 tie at silhouette 0.181, and the tie-break
landed on k=8. But k=7 **dominates** k=8 on the validity+stability panel
(zoning_kselect.csv): better Davies-Bouldin (1.557 vs 1.586), equal silhouette, and
higher subsample stability (ARI 0.836 vs 0.802) — and it matches the thesis narrative.
So we fix k deliberately (ZONE_K, default 7), re-fit, re-export zones_present, and
re-aggregate the municipal table on the corrected zones.

Clustering input is unchanged (same z-stack + ZONING_BANDS + seed), so this only
re-labels; it does not touch the suitability/CMIP6 assets.

Run:  ZONE_K=7 EE_PROJECT=probformer ../.venv/bin/python tools/rezone.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "src")

import ee  # noqa: E402
import utils  # noqa: E402
import zoning  # noqa: E402
import external  # noqa: E402

P = utils.init()
AOI = utils.load_aoi(P)
SEGS = list(utils.cfg("segments")["segments"])
K = int(os.environ.get("ZONE_K", "7"))


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def aid(n):
    return utils.asset_id(P, n)


def img(n):
    return ee.Image(aid(n))


def wait_for(name, task, timeout=3600, poll=30):
    t0 = time.time()
    while True:
        try:
            ee.data.getAsset(aid(name))
            log(f"  ready: {name}")
            return
        except ee.EEException:
            pass
        st = task.status()
        if st["state"] in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"{name} {st['state']}: {st.get('error_message','')}")
        if time.time() - t0 > timeout:
            raise TimeoutError(name)
        time.sleep(poll)


def main():
    log(f"=== rezone at K={K} (project={P}) ===")
    z = img("feature_stack_250m_z")
    stack = img("feature_stack_250m")
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
    log(f"  PCs={pca.n_components_}; fitting KMeans k={K}")
    km = zoning.fit_kmeans(S, K, seed=42)
    theme_w = zoning.theme_weight_vector(bands)
    pc_img = zoning.pca_project_image(z, bands, theme_w, pca)
    zones = zoning.nearest_centroid_image(pc_img, zoning.pc_names(pca), km.cluster_centers_)
    prof = zoning.profile_zones(df, km.labels_, bands, SEGS, realized_fracs=frac_bands)
    prof.to_csv("zone_profiles.csv", index=False)
    log("  zone profiles:\n" + prof[["zone", "n", "comparative_segment",
        "dominant_segment", "top_features"]].to_string(index=False))

    t_z = utils.export_image(zones.toByte(), P, "zones_present", AOI, overwrite=True)
    wait_for("zones_present", t_z)

    # re-aggregate municipal on the corrected zones (delete-first: table has no overwrite)
    zones_a = img("zones_present").rename("zone")
    delta_a = img("delta_ssp585_2051_2070")
    agg = suit_a.select([f"suit_{s}" for s in SEGS]).addBands(zones_a).addBands(delta_a)
    muni = external.municipal_means(external.municipal_fc(), agg)
    try:
        ee.data.deleteAsset(aid("municipal_godf"))
        log("  deleted stale municipal_godf")
    except ee.EEException:
        pass
    t_m = utils.export_table(muni, P, "municipal_godf")
    log("  submitted municipal_godf; waiting ...")
    t0 = time.time()
    while time.time() - t0 < 2400:
        try:
            ee.data.getAsset(aid("municipal_godf"))
            log("  ready: municipal_godf")
            break
        except ee.EEException:
            st = t_m.status()
            if st["state"] in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"municipal_godf {st['state']}")
            time.sleep(30)
    log(f"=== rezone complete (K={K}); zones_present + municipal_godf re-exported ===")


if __name__ == "__main__":
    main()
