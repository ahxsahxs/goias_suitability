"""Re-export zones_present with the current ZONING_BANDS / k (overwrite=True).

Reproduces exactly the same pipeline as notebook 10:
  stratified sample (n=40k, seed=42) → PCA (>=90%) → KMeans(k=auto by silhouette)
  → nearest-centroid server-side classification → export zones_present (overwrite).

Run when the asset already exists from a previous run:
    EE_PROJECT=probformer uv run python tools/reexport_zones.py
"""
from __future__ import annotations
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import ee
import utils, zoning

P   = utils.init()
AOI = utils.load_aoi(P)
SEGS = list(utils.cfg("segments")["segments"])

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def main():
    bands = zoning.ZONING_BANDS
    log(f"bands={len(bands)}  ZONING_BANDS={bands}")

    z    = ee.Image(utils.asset_id(P, "feature_stack_250m_z"))
    raw  = ee.Image(utils.asset_id(P, "feature_stack_250m"))
    suit = ee.Image(utils.asset_id(P, "suit_present"))

    log("Sampling (stratified n=40k seed=42) ...")
    fc = zoning.build_sample(z, raw, suit, AOI, bands, segments=SEGS,
                              stratify=True, n=40000, seed=42)
    df = zoning.fc_to_df(fc)
    log(f"  {len(df)} rows")

    X   = zoning.cluster_matrix(df, bands)
    pca = zoning.fit_pca(X, var_keep=0.90)
    S   = pca.transform(X)
    log(f"  PCA: {pca.n_components_} components")

    sweep = zoning.kmeans_sweep(S, ks=range(2, 11), seed=42)
    K = int(sweep.loc[sweep.silhouette.idxmax(), "k"])
    log(f"  chosen K={K} (silhouette={sweep.loc[sweep.silhouette.idxmax(),'silhouette']:.3f})")

    km = zoning.fit_kmeans(S, K, seed=42,
                           order_by=df[zoning.CANONICAL_ORDER_BAND])
    log(f"  zone sizes: {list(map(int, __import__('numpy').bincount(km.labels_)))}")

    theme_w = zoning.theme_weight_vector(bands)
    pc_img  = zoning.pca_project_image(z, bands, theme_w, pca)
    zones   = zoning.nearest_centroid_image(pc_img, zoning.pc_names(pca), km.cluster_centers_)

    log("Submitting export (overwrite=True) ...")
    task = utils.export_image(zones.toByte(), P, "zones_present", AOI, overwrite=True)
    log(f"  task_id={task.status()['id']}  state={task.status()['state']}")
    log("Done. Monitor: EE_PROJECT=probformer uv run earthengine task list")

if __name__ == "__main__":
    main()
