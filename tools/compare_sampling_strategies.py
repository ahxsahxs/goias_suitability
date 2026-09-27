"""Compare KMeans clustering fitted on stratified vs. random equal-size samples.

Quantifies whether the sampling strategy (stratified by 8×8 grid × dominant
segment vs. uniform random) produces meaningfully different cluster structures.
Uses the 13-band ZONING_BANDS from src/zoning.py (s2 must be done first).

Protocol
--------
1. Draw stratified sample (n=40 000, seed=42) → df_strat
2. Draw random sample    (n=40 000, seed=42) → df_rand
3. Fit PCA on df_strat (var_keep=0.90)        → pca_A
4. Project BOTH samples through pca_A          → S_strat, S_rand
5. Fit KMeans(k=13, n_init=10) on S_strat     → km_A
6. Fit KMeans(k=13, n_init=10) on S_rand      → km_B
7. Draw held-out test set (n=5 000, seed=99)   → S_test
8. Label test set with both models             → labels_A, labels_B
9. ARI(labels_A, labels_B)
10. Greedy centroid nearest-match → mean matched distance in pca_A space

Run (s2 must be done first):
    EE_PROJECT=probformer uv run python tools/compare_sampling_strategies.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import ee      # noqa: E402
import utils   # noqa: E402
import zoning  # noqa: E402

P = utils.init()
AOI = utils.load_aoi(P)
SEGS = list(utils.cfg("segments")["segments"])


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def greedy_centroid_match(
    A: np.ndarray, B: np.ndarray
) -> list[tuple[int, int, float]]:
    """Greedy nearest-match between two (k × p) centroid arrays.

    For each row in A (order 0..k-1) assigns the closest unmatched row in B.
    O(k²) — fine for k ≤ 20.  Returns list of (i_A, i_B, euclidean_distance).
    """
    from scipy.spatial.distance import cdist

    D = cdist(A, B, metric="euclidean")
    k = len(A)
    used: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for i in range(k):
        row = D[i].copy()
        for j in used:
            row[j] = np.inf
        j_best = int(np.argmin(row))
        matches.append((i, j_best, float(D[i, j_best])))
        used.add(j_best)
    return matches


def main() -> None:
    bands = zoning.ZONING_BANDS
    assert len(bands) == 13, (
        f"Expected 13 bands after s2, got {len(bands)}: {bands}\n"
        "Run s2 first: edit ZONING_BANDS in src/zoning.py."
    )
    log(f"=== sampling-strategy comparison  k=13  13-band ZONING_BANDS ===")

    z    = ee.Image(utils.asset_id(P, "feature_stack_250m_z"))
    raw  = ee.Image(utils.asset_id(P, "feature_stack_250m"))
    suit = ee.Image(utils.asset_id(P, "suit_present"))

    # Steps 1–2: draw both samples
    log("Drawing stratified sample (n=40 000, seed=42) ...")
    strat_fc = zoning.build_sample(
        z, raw, suit, AOI, bands, segments=SEGS,
        stratify=True, n=40000, seed=42,
    )
    df_strat = zoning.fc_to_df(strat_fc)
    log(f"  stratified: {len(df_strat)} rows")

    log("Drawing random sample (n=40 000, seed=42) ...")
    rand_fc = zoning.build_sample(
        z, raw, suit, AOI, bands, segments=SEGS,
        stratify=False, n=40000, seed=42,
    )
    df_rand = zoning.fc_to_df(rand_fc)
    log(f"  random: {len(df_rand)} rows")

    # Step 3: PCA on stratified sample
    X_strat = zoning.cluster_matrix(df_strat, bands)
    X_rand  = zoning.cluster_matrix(df_rand,  bands)
    log("Fitting PCA on stratified design matrix ...")
    pca_A = zoning.fit_pca(X_strat, var_keep=0.90)
    log(f"  PCA_A: {pca_A.n_components_} components (>=90% var)")

    # Step 4: project both samples through pca_A
    S_strat = pca_A.transform(X_strat)
    S_rand  = pca_A.transform(X_rand)

    # Steps 5–6: KMeans on each in the same PC space
    log("Fitting KMeans(k=13) on stratified PCs ...")
    km_A = zoning.fit_kmeans(S_strat, 13, seed=42)

    log("Fitting KMeans(k=13) on random PCs ...")
    km_B = KMeans(n_clusters=13, random_state=42, n_init=10).fit(S_rand)
    log(f"  inertia_A={km_A.inertia_:.1f}  inertia_B={km_B.inertia_:.1f}")

    # Step 7: held-out test set (neither training set)
    log("Drawing held-out test set (n=5 000, seed=99) ...")
    test_fc = zoning.build_sample(
        z, raw, suit, AOI, bands,
        stratify=False, n=5000, seed=99,
    )
    df_test = zoning.fc_to_df(test_fc)
    X_test  = zoning.cluster_matrix(df_test, bands)
    S_test  = pca_A.transform(X_test)
    log(f"  test set: {len(df_test)} rows")

    # Steps 8–9: label + ARI
    labels_A = km_A.predict(S_test)
    labels_B = km_B.predict(S_test)
    ari = adjusted_rand_score(labels_A, labels_B)

    # Step 10: centroid distances (greedy nearest-match in pca_A space)
    matches   = greedy_centroid_match(km_A.cluster_centers_, km_B.cluster_centers_)
    mean_dist = float(np.mean([m[2] for m in matches]))

    # Report
    sep = "=" * 64
    print(f"\n{sep}")
    print(f"Sampling-strategy comparison  k=13  n_train=40k  n_test=5k")
    print(sep)
    print(f"ARI(stratified labels, random labels)  = {ari:.4f}")
    print(f"Mean matched centroid distance (pca_A) = {mean_dist:.4f}")
    if ari > 0.80:
        print("VERDICT: equivalent cluster structure (ARI > 0.80).")
        print("Stratification does not distort the biophysical zonation.")
    else:
        print(f"WARNING: ARI = {ari:.4f} < 0.80 — sampling strategy affects structure.")
        print("Consider investigating which zones differ between the two strategies.")
    print("\nPer-matched-pair centroid distances (PC space):")
    for i_a, i_b, d in matches:
        print(f"  km_A[{i_a:2d}] ↔ km_B[{i_b:2d}]  dist={d:.4f}")
    print(sep)


if __name__ == "__main__":
    main()
