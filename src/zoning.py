"""Part 10 — unsupervised biophysical zoning + zone profiling.

Cluster the **z-scored** feature stack (``feature_stack_250m_z``) into biophysical
zones, then profile each zone (mean of every feature + the comparative best-fit
segment, ranked from ``suit_present``).

Clustering is done **offline with scikit-learn** rather than EE's weka clusterer:
weka ``SimpleKMeans`` collapses to a single cluster on this 34-band, highly
collinear stack (fails for >~4 inputs regardless of the ``init`` mode), whereas
sklearn KMeans is robust and is already needed for the elbow/silhouette/gap
k-selection the plan calls for. We fit centroids offline on a sample, then
classify the **full image server-side by nearest-centroid band math** — fully
deterministic and label-identical to sklearn (Euclidean metric, same centroids).

**Decorrelated zoning (2026-07-14 robustness iteration).** Clustering the raw
34-band stack resolved only 3 low-expressiveness zones: GO/DF is climatically
near-uniform (annual precip 1373–1635 mm, dry-months a spatial constant), yet the
14 collinear climate bands each carried a full unit of Euclidean weight and
swamped the soil/relief/hydrology structure that actually separates the land. The
iteration clusters on a **curated subset** (``ZONING_BANDS``, ~15 bands, near-
duplicates dropped) with **theme-block weighting** (each band's z divided by
√bands-in-theme so climate cannot outvote water/access) followed by **PCA**
(≥ ``var_keep`` variance) so KMeans runs on orthogonal PCs. k is re-selected on
the decorrelated space by silhouette + Davies–Bouldin + the gap statistic. The
server-side path is unchanged: PCA projection is linear band-math, so we build a
PC-score image and reuse the same nearest-centroid classify. **Do NOT** revert to
``ee.Clusterer.wekaKMeans`` (CLAUDE.md §11).

GUARDRAIL: only the biophysical z-features feed the clusterer. The raw stack,
``suit_present`` bands and (optional) realized-use fractions ride along in the
sample **for profiling only** — land cover and suitability are never clustering
inputs (see CLAUDE.md Conventions).

EE-side builders are lazy (no server call at import), so the module is import-/
syntax-checkable without Earth Engine auth; sklearn/pandas/numpy are imported
inside the offline helpers so EE-only callers don't need them.
"""
from __future__ import annotations

import math

import ee

# z-scored clustering bands get this prefix in the combined sample so they don't
# collide with the same-named raw bands carried for profiling.
Z_PREFIX = "z_"

# --- curated, decorrelated zoning subset (2026-07-14) -----------------------
# ~15 bands with real spatial structure; near-duplicates and near-uniform climate
# dropped (aridity kept over pr/pet; one thermal index; clay kept over sand/bdod;
# phen_amplitude kept over the NDVI-integral duplicate). Land cover excluded as
# always. The theme of each band is its name prefix (clim/terr/soil/water/phen/
# access), used for the √(bands-in-theme) block weighting.
ZONING_BANDS = [
    # climate (4) — the axes that still carry gradient in an otherwise-uniform territory
    "clim_aridity", "clim_soil_moist", "clim_twarm_q", "clim_def_annual",
    # terrain (3)
    "terr_elev", "terr_slope", "terr_twi",
    # soil (4)
    "soil_clay", "soil_soc", "soil_ph", "soil_awc",
    # water (2)
    "water_dist", "water_drain_density",
    # phenology (1) — separates cropland (high amplitude) from native (low)
    "phen_amplitude",
    # access (1)
    "access_logtt",
]


def zbands(band_names):
    """Prefixed names of the z-scored clustering columns."""
    return [Z_PREFIX + b for b in band_names]


def _theme_of(band):
    """Theme key = the band-name prefix (clim/terr/soil/water/phen/access)."""
    return band.split("_", 1)[0]


def theme_weight_vector(band_names):
    """Per-band block weight 1/√(bands-in-theme), aligned to ``band_names``.

    Divides each theme's contribution to the Euclidean distance by the number of
    bands it contributes, so a large near-collinear block (climate) cannot outvote
    a small one (water, access). Returns a plain list (offline + server-side use).
    """
    from collections import Counter

    counts = Counter(_theme_of(b) for b in band_names)
    return [1.0 / math.sqrt(counts[_theme_of(b)]) for b in band_names]


# --- EE-side: sampling + classification ------------------------------------
def build_strat_band(region, n_side=8, name="strat_grid"):
    """Coarse ``n_side`` x ``n_side`` spatial-grid cell id over ``region``'s bounds.

    Stratification-only band (never a clustering input): one small ``getInfo`` on
    the bounding box, then per-pixel bin math. Used so a training/validation
    sample is spread across the territory instead of wherever a uniform draw
    happens to land (T8, 2026-09 — CLAUDE.md §10 revision cycle).
    """
    coords = ee.Geometry(region).bounds().coordinates().get(0).getInfo()
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    lon0, lon1 = min(lons), max(lons)
    lat0, lat1 = min(lats), max(lats)
    ll = ee.Image.pixelLonLat()
    gx = (ll.select("longitude").subtract(lon0).divide((lon1 - lon0) / n_side)
          .floor().clamp(0, n_side - 1))
    gy = (ll.select("latitude").subtract(lat0).divide((lat1 - lat0) / n_side)
          .floor().clamp(0, n_side - 1))
    return gx.multiply(n_side).add(gy).rename(name)


def dominant_segment_band(suit, segments, name="strat_segment"):
    """Per-pixel argmax segment index (0..len(segments)-1) over ``suit_<seg>``.

    Stratification-only: identifies each pixel's single best-fit segment so a
    sample keeps proportional representation of every segment's high-suitability
    niche (e.g. pisciculture's narrow riparian band) instead of being swamped by
    whichever segment's suitable area is largest. Never an input to the
    clusterer itself — only to the sampling stratum (T8, 2026-09).
    """
    stacked = ee.Image.cat([suit.select(f"suit_{s}") for s in segments]).rename(segments)
    return stacked.toArray().arrayArgmax().arrayGet([0]).rename(name)


def build_sample(z, raw, suit, region, band_names, segments=None,
                 n=40000, scale=250, seed=42, tile_scale=4, extra=None,
                 stratify=True, n_grid=8, points_per_stratum=None):
    """One aligned sample carrying z-features (clustering) + raw + suit (profiling).

    Returns a FeatureCollection with, per point: ``z_<band>`` (clustering),
    ``<band>`` (raw, interpretable profiling means) and ``suit_<segment>``. If
    ``extra`` (an ``ee.Image``, e.g. realized-use fractions) is given, its bands
    ride along for descriptive zone composition — profiling only, never clustered.

    **Stratified by default (T8, 2026-09 revision).** With ``stratify=True``
    (default), draws via ``ee.Image.stratifiedSample`` on a combined stratum =
    coarse spatial-grid cell (``build_strat_band``, ``n_grid`` x ``n_grid`` over
    ``region``) x dominant comparative segment (``dominant_segment_band``, when
    ``segments`` is given; grid-only otherwise) — both spatial and per-segment
    representation, instead of one uniform ``.sample()`` draw that can under-
    represent a segment's small, specialized niche. ``n`` is the total target
    sample size, split across strata as ``points_per_stratum`` (derived from
    ``n`` when not given explicitly). Pass ``stratify=False`` for the original
    uniform-sample behavior.
    """
    zp = z.select(band_names).rename(zbands(band_names))
    combo = zp.addBands(raw.select(band_names)).addBands(suit)
    if extra is not None:
        combo = combo.addBands(extra)

    if not stratify:
        return combo.sample(region=region, scale=scale, numPixels=n, seed=seed,
                            tileScale=tile_scale, dropNulls=True, geometries=False)

    grid = build_strat_band(region, n_side=n_grid)
    if segments:
        dom = dominant_segment_band(suit, segments)
        n_strata = n_grid * n_grid * len(segments)
        strat = grid.multiply(len(segments)).add(dom).rename("strat").toInt()
    else:
        n_strata = n_grid * n_grid
        strat = grid.rename("strat").toInt()

    pts = points_per_stratum or max(1, n // n_strata)
    fc = combo.addBands(strat).stratifiedSample(
        numPoints=pts, classBand="strat", region=region, scale=scale, seed=seed,
        tileScale=tile_scale, dropNulls=True, geometries=False,
    )
    return fc.select(combo.bandNames())


def nearest_centroid_image(z, band_names, centroids, name="zone"):
    """Classify the z-stack to the nearest KMeans centroid (server-side argmin).

    ``centroids`` is a (k x len(band_names)) array-like in ``band_names`` order
    (e.g. ``sklearn`` ``cluster_centers_``). Uses negative squared distance +
    ``arrayArgmax`` so the label equals sklearn's Euclidean assignment. When
    ``band_names`` are PC names and ``z`` is a PC-score image (see
    ``pca_project_image``), this classifies in the decorrelated PC space.
    """
    zimg = z.select(band_names)
    neg = []
    for row in centroids:
        c = ee.Image.constant([float(v) for v in row]).rename(band_names)
        neg.append(zimg.subtract(c).pow(2).reduce(ee.Reducer.sum()).multiply(-1))
    return ee.Image.cat(neg).toArray().arrayArgmax().arrayGet([0]).rename(name)


def pca_project_image(z, band_names, theme_w, pca, pc_prefix="pc"):
    """Server-side PC-score image: project theme-weighted z-bands onto PCA loadings.

    Reproduces ``pca.transform(theme_weighted_X)`` as linear band-math:
    ``PC_j = Σ_b components_[j,b] · (w_b · z_b − mean_b)`` where ``w_b`` is the
    theme weight and ``mean_b`` the PCA (weighted-space) mean. Returns an image
    with one band ``pc0..pc{n-1}`` per retained component, consumable by
    ``nearest_centroid_image`` — so the offline-fit → server-side-classify
    architecture carries over unchanged into PC space.
    """
    comps = pca.components_          # (n_pc, n_band)
    mean = pca.mean_                 # (n_band,) in theme-weighted space
    zsel = z.select(band_names)
    centered = [
        zsel.select([b]).multiply(float(theme_w[i])).subtract(float(mean[i]))
        for i, b in enumerate(band_names)
    ]
    pcs = []
    for j in range(comps.shape[0]):
        acc = None
        for i in range(len(band_names)):
            term = centered[i].multiply(float(comps[j, i]))
            acc = term if acc is None else acc.add(term)
        pcs.append(acc.rename(f"{pc_prefix}{j}"))
    return ee.Image.cat(pcs)


def pc_names(pca, pc_prefix="pc"):
    """Band names of the PC-score image for a fitted ``pca``."""
    return [f"{pc_prefix}{j}" for j in range(pca.components_.shape[0])]


# --- offline: decorrelation, k-selection, fit, profiling --------------------
def fc_to_df(sample, page_size=5000):
    """Pull a sampled FeatureCollection's properties into a DataFrame.

    Uses the paged ``computeFeatures`` table reader (``PANDAS_DATAFRAME`` makes a
    request per page until the whole table is fetched), so it is **not** capped by
    the 5000-element limit that aborts a plain ``FeatureCollection.getInfo()``
    ("Collection query aborted after accumulating over 5000 elements"). Property
    names become DataFrame columns: ``z_<band>`` / ``<band>`` / ``suit_<segment>``.
    """
    df = ee.data.computeFeatures({
        "expression": sample,
        "fileFormat": "PANDAS_DATAFRAME",
        "pageSize": page_size,
    })
    # geometries=False in build_sample, but drop any stray geometry column so the
    # frame is properties-only (downstream selects by name, so this is belt-and-braces).
    return df.drop(columns=[c for c in ("geo", "geometry") if c in df.columns])


def cluster_matrix(df, band_names=ZONING_BANDS, theme_weighted=True):
    """The z-feature design matrix, columns in canonical ``band_names`` order.

    With ``theme_weighted`` (default) each column is scaled by its
    ``theme_weight_vector`` entry, matching what ``pca_project_image`` applies
    server-side — so the offline fit and the server classify see the same space.
    """
    import numpy as np

    X = df[zbands(band_names)].to_numpy()
    if theme_weighted:
        X = X * np.asarray(theme_weight_vector(band_names))
    return X


def fit_pca(X, var_keep=0.90, seed=42):
    """Fit PCA on the (theme-weighted) matrix, retaining ``var_keep`` variance."""
    from sklearn.decomposition import PCA

    return PCA(n_components=var_keep, svd_solver="full", random_state=seed).fit(X)


def kmeans_sweep(X, ks=range(2, 11), seed=42, sil_sample=5000):
    """Internal-validity sweep over k (DataFrame: k, inertia, silhouette,
    davies_bouldin) on the decorrelated (PC) space. Lower Davies–Bouldin and
    higher silhouette are better; inertia is the elbow. Gap is a separate call
    (``gap_statistic``) because it needs reference resampling."""
    import numpy as np
    import pandas as pd
    from sklearn.cluster import KMeans
    from sklearn.metrics import davies_bouldin_score, silhouette_score

    rng = np.random.default_rng(seed)
    rows = []
    for k in ks:
        km = KMeans(n_clusters=k, random_state=seed, n_init=10).fit(X)
        m = min(sil_sample, len(X))
        idx = rng.choice(len(X), m, replace=False) if len(X) > m else slice(None)
        rows.append({
            "k": k,
            "inertia": km.inertia_,
            "silhouette": silhouette_score(X[idx], km.labels_[idx]),
            "davies_bouldin": davies_bouldin_score(X, km.labels_),
        })
    return pd.DataFrame(rows)


def gap_statistic(X, ks=range(2, 11), B=10, seed=42, n_init=5):
    """Tibshirani gap statistic over k (DataFrame: k, gap, s_k).

    gap(k) = mean_b log(W_kb*) − log(W_k), where W is the within-cluster dispersion
    and the reference sets are uniform draws over each PC's observed range. The
    first k with ``gap(k) ≥ gap(k+1) − s_{k+1}`` is the recommended elbow-free k.
    Kept light (``B``, ``n_init`` small) because it runs at re-export time, not
    interactively.
    """
    import numpy as np
    import pandas as pd
    from sklearn.cluster import KMeans

    rng = np.random.default_rng(seed)

    def dispersion(data, k):
        km = KMeans(n_clusters=k, random_state=seed, n_init=n_init).fit(data)
        return km.inertia_  # sum of squared distances to nearest centroid

    lo, hi = X.min(axis=0), X.max(axis=0)
    rows = []
    for k in ks:
        logw = math.log(dispersion(X, k))
        ref = np.empty(B)
        for b in range(B):
            Xb = rng.uniform(lo, hi, size=X.shape)
            ref[b] = math.log(dispersion(Xb, k))
        gap = ref.mean() - logw
        sk = ref.std() * math.sqrt(1.0 + 1.0 / B)
        rows.append({"k": k, "gap": gap, "s_k": sk})
    return pd.DataFrame(rows)


def cluster_stability(X, k, B=20, sample_frac=0.8, seed=42, n_init=5):
    """Subsample cluster **stability** = mean pairwise Adjusted Rand Index (ARI)
    across ``B`` KMeans fits, each on a random ``sample_frac`` subsample but
    relabelling the *full* ``X``.

    A partition that is real (not an artefact of one particular sample) reproduces
    under resampling, so the label vectors agree and ARI → 1; an unstable k gives
    low ARI. This is the companion to the internal-validity indices
    (``kmeans_sweep`` / ``gap_statistic``): it certifies that the chosen k is
    *reproducible*, answering the "why exactly k?" critique (W5). Returns
    ``(mean_ari, std_ari)``.
    """
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score

    rng = np.random.default_rng(seed)
    n = len(X)
    m = int(sample_frac * n)
    labels = []
    for b in range(B):
        idx = rng.choice(n, m, replace=False)
        km = KMeans(n_clusters=k, random_state=seed + b, n_init=n_init).fit(X[idx])
        labels.append(km.predict(X))
    aris = [
        adjusted_rand_score(labels[i], labels[j])
        for i in range(len(labels)) for j in range(i + 1, len(labels))
    ]
    return float(np.mean(aris)), float(np.std(aris))


def stability_sweep(X, ks=range(2, 11), B=20, sample_frac=0.8, seed=42):
    """ARI ``cluster_stability`` across a range of k (DataFrame: k, ari, ari_std).

    Reported alongside ``kmeans_sweep`` + ``gap_statistic`` so the k choice rests
    on internal validity **and** reproducibility, not one index alone."""
    import pandas as pd

    rows = []
    for k in ks:
        mean, std = cluster_stability(X, k, B=B, sample_frac=sample_frac, seed=seed)
        rows.append({"k": k, "ari": mean, "ari_std": std})
    return pd.DataFrame(rows)


def fit_kmeans(X, k, seed=42):
    """Fit the final sklearn KMeans; returns the model (``.cluster_centers_``)."""
    from sklearn.cluster import KMeans

    return KMeans(n_clusters=k, random_state=seed, n_init=10).fit(X)


def comparative_suitability(df, segments):
    """Per-segment z-normalized suitability over the sample (comparative footing).

    Each ``suit_<seg>`` column is standardized to zero mean / unit std across the
    sample, so segments of unequal permissiveness (cattle saturates high; solar
    low) are compared on common ground. Returns a DataFrame of ``z`` columns.
    """
    suit_cols = [f"suit_{s}" for s in segments]
    s = df[suit_cols]
    return (s - s.mean()) / s.std(ddof=0).replace(0, 1e-9)


def profile_zones(df, labels, band_names, segments, realized_fracs=None):
    """Zone profile cards: size, mean of every feature, per-segment mean
    suitability, and comparative/absolute best-use labels.

    - ``dominant_segment`` — absolute argmax of mean suitability (the most
      permissive segment tends to win, so it is rarely discriminative).
    - ``comparative_segment`` — argmax of zone-mean **z-normalized** suitability
      (see ``comparative_suitability``): the segment a zone is *comparatively* best
      suited to, on common footing. This replaces the earlier ad-hoc
      "distinctive_segment" (zone-mean − AOI-mean) and is the zone's headline label.
    - ``top_features`` — the 3 z-features whose zone mean deviates most from the
      AOI (the |largest| standardized departures): what makes the zone distinct.
    - ``rl_*`` — mean realized-use fractions if ``realized_fracs`` band names are
      present in ``df`` (descriptive composition; never clustered).
    """
    import pandas as pd

    d = df.copy()
    d["zone"] = labels
    g = d.groupby("zone")
    suit_cols = [f"suit_{s}" for s in segments]

    prof = g[band_names].mean()
    prof.insert(0, "n", g.size())

    suit = g[suit_cols].mean()
    prof["dominant_segment"] = suit.idxmax(axis=1).str.replace("suit_", "", regex=False)

    # comparative best-use: argmax of zone-mean z-normalized suitability
    comp = comparative_suitability(df, segments)
    comp["zone"] = labels
    comp_mean = comp.groupby("zone")[suit_cols].mean()
    prof["comparative_segment"] = comp_mean.idxmax(axis=1).str.replace(
        "suit_", "", regex=False)

    # de-meaned 7-segment signature (comparative radar, not absolute means)
    rel = (suit - df[suit_cols].mean()).add_prefix("rel_")

    # top discriminating z-features per zone (z is ~0-mean over the AOI already)
    zcols = zbands(band_names)
    zmean = g[zcols].mean()
    top = zmean.abs().apply(
        lambda r: ", ".join(r.abs().sort_values(ascending=False).head(3).index
                            .str.replace(Z_PREFIX, "", regex=False)), axis=1)
    prof["top_features"] = top

    out = [prof, suit, rel]
    if realized_fracs:
        cols = [c for c in realized_fracs if c in df.columns]
        if cols:
            out.append(g[cols].mean())
    return pd.concat(out, axis=1).reset_index()
