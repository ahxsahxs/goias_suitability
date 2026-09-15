"""Offline validation statistics for Part 14.

Operates on numpy arrays / pandas Series pulled from Earth Engine reductions —
no EE dependency, so it is import-/syntax-checkable and unit-testable locally.
Provides the RQ1-validation statistics named in the methodology: Spearman rho,
one-way ANOVA, Cohen's kappa, ROC-AUC, and the continuous Boyce index.
"""
from __future__ import annotations

import numpy as np


def _clean_pair(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    return x[ok], y[ok]


def spearman(x, y) -> dict:
    """Spearman rank correlation of ``x`` vs ``y`` (finite pairs only)."""
    from scipy.stats import spearmanr

    x, y = _clean_pair(x, y)
    rho, p = spearmanr(x, y)
    return {"rho": float(rho), "p": float(p), "n": int(x.size)}


def within_crop_gradient(suit, gpp, n_bins: int = 5) -> dict:
    """Within-crop suitability→productivity gradient (the repaired validator).

    Given per-pixel suitability and growing-season GPP **restricted to one crop's
    own realized pixels**, report Spearman(suitability, season-GPP) plus the mean
    GPP per suitability quantile bin (should rise monotonically). This replaces the
    confounded across-land-cover municipal NPP correlation: because it stays within
    a single crop and its canopy season, the sign should be **non-negative** for the
    extensive crops (removing the spurious −0.34). Validates *how much* crops
    produce — distinct from the presence AUC/Boyce (``auc``/``continuous_boyce``)
    that validate *where* they go.
    """
    import pandas as pd

    x, y = _clean_pair(suit, gpp)                 # x=suitability, y=season-GPP
    g = spearman(x, y)
    if x.size < n_bins:
        return {**g, "bin_gpp": [], "bin_suit": [], "monotonic": None}
    q = pd.qcut(pd.Series(x), n_bins, labels=False, duplicates="drop")
    dfb = pd.DataFrame({"b": q, "x": x, "y": y}).groupby("b")
    bin_suit = dfb["x"].mean().tolist()
    bin_gpp = dfb["y"].mean().tolist()
    monotonic = bool(np.all(np.diff(bin_gpp) >= 0)) if len(bin_gpp) > 1 else None
    return {"rho": g["rho"], "p": g["p"], "n": g["n"],
            "bin_suit": bin_suit, "bin_gpp": bin_gpp, "monotonic": monotonic}


def anova(groups) -> dict:
    """One-way ANOVA across a list/dict of value arrays (e.g. proxy by zone)."""
    from scipy.stats import f_oneway

    arrs = list(groups.values()) if isinstance(groups, dict) else list(groups)
    arrs = [np.asarray(a, dtype=float) for a in arrs]
    arrs = [a[np.isfinite(a)] for a in arrs]
    f, p = f_oneway(*arrs)
    return {"F": float(f), "p": float(p),
            "group_means": [float(np.mean(a)) for a in arrs],
            "group_n": [int(a.size) for a in arrs]}


def cohen_kappa(a, b) -> dict:
    """Cohen's kappa between two categorical labelings (e.g. FAO class vs RF class)."""
    from sklearn.metrics import cohen_kappa_score

    a = np.asarray(a)
    b = np.asarray(b)
    ok = np.array([ai is not None and bi is not None for ai, bi in zip(a, b)])
    return {"kappa": float(cohen_kappa_score(a[ok], b[ok])), "n": int(ok.sum())}


def auc(y_true, score) -> dict:
    """ROC-AUC of a continuous ``score`` (e.g. suitability) against binary presence."""
    from sklearn.metrics import roc_auc_score

    y = np.asarray(y_true, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(y) & np.isfinite(s)
    return {"auc": float(roc_auc_score(y[ok], s[ok])), "n": int(ok.sum())}


# --- spatial cross-validation (WS-B: guard against spatial sorting bias) -----
def block_id(lon, lat, block_deg: float = 0.5):
    """Spatial-block label per point: floor lon/lat onto a ``block_deg`` grid.

    Presence-only AUC/Boyce and a trained RF are both inflated by spatial
    autocorrelation when nearby train/test points leak information. Grouping points
    into coarse spatial blocks (default ~0.5° ≈ 55 km) lets the metric be evaluated
    *across* blocks (``spatial_block_auc`` / ``spatial_block_folds``), so agreement
    reflects genuine, spatially-transferable discrimination — not clustering.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    bx = np.floor(lon / block_deg).astype(int)
    by = np.floor(lat / block_deg).astype(int)
    return bx * 100000 + by


def spatial_block_auc(y_true, score, blocks, min_pos: int = 10, min_neg: int = 10) -> dict:
    """ROC-AUC resolved by spatial block: mean ± SD of within-block AUC (blocks with
    both classes and ≥ ``min_pos``/``min_neg`` counts) plus the pooled AUC.

    If discrimination holds *within* blocks the block-mean stays high and near the
    pooled value; a pooled AUC driven only by presences clustering in a few regions
    collapses block-wise. Reported alongside the pooled AUC (Table 4.11) to answer
    the spatial-autocorrelation critique (W4)."""
    from sklearn.metrics import roc_auc_score

    y = np.asarray(y_true, dtype=float)
    s = np.asarray(score, dtype=float)
    bl = np.asarray(blocks)
    ok = np.isfinite(y) & np.isfinite(s)
    y, s, bl = y[ok], s[ok], bl[ok]
    per = []
    for b in np.unique(bl):
        m = bl == b
        yb = y[m]
        if yb.sum() >= min_pos and (yb == 0).sum() >= min_neg:
            per.append(roc_auc_score(yb, s[m]))
    per = np.asarray(per, dtype=float)
    pooled = (float(roc_auc_score(y, s))
              if y.sum() > 0 and (y == 0).sum() > 0 else float("nan"))
    return {"pooled_auc": pooled,
            "block_auc_mean": float(per.mean()) if per.size else float("nan"),
            "block_auc_std": float(per.std()) if per.size else float("nan"),
            "n_blocks": int(per.size), "block_aucs": per.tolist()}


def spatial_block_folds(blocks, k: int = 5, seed: int = 42):
    """Assign whole spatial ``blocks`` to ``k`` CV folds (grouped CV).

    Returns a fold id per point (aligned to ``blocks``); a classifier trained on
    k−1 folds and scored on the held-out fold never sees a training point in the
    same spatial block as a test point — the out-of-block evaluation that removes
    the in-sample optimism spatial autocorrelation grants the RF (used for the
    RF-vs-knowledge Cohen's κ)."""
    bl = np.asarray(blocks)
    uniq = np.unique(bl)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(uniq))
    fold_of = {b: int(perm[i] % k) for i, b in enumerate(uniq)}
    return np.array([fold_of[b] for b in bl])


def continuous_boyce(presence_scores, background_scores, n_bins: int = 10,
                     window: float = 0.1) -> dict:
    """Continuous Boyce index (Hirzel et al. 2006).

    Predicted-to-expected (P/E) ratio across a moving suitability window, then
    Spearman correlation between the P/E curve and window position. B ~ +1 means
    presences concentrate monotonically in high-suitability classes (a good model);
    B ~ 0 means no better than random.

    ``presence_scores``  suitability at presence (e.g. cropland) pixels
    ``background_scores`` suitability at background (all/available) pixels
    """
    from scipy.stats import spearmanr

    p = np.asarray(presence_scores, dtype=float)
    b = np.asarray(background_scores, dtype=float)
    p = p[np.isfinite(p)]
    b = b[np.isfinite(b)]
    lo, hi = float(np.nanmin(b)), float(np.nanmax(b))
    centers = np.linspace(lo + window / 2, hi - window / 2, n_bins)
    pe = []
    for c in centers:
        a, z = c - window / 2, c + window / 2
        fp = np.mean((p >= a) & (p <= z))   # observed frequency of presences
        fe = np.mean((b >= a) & (b <= z))   # expected frequency (background)
        pe.append(fp / fe if fe > 0 else np.nan)
    pe = np.asarray(pe)
    ok = np.isfinite(pe)
    boyce, _ = spearmanr(centers[ok], pe[ok])
    return {"boyce": float(boyce), "pe_curve": pe[ok].tolist(),
            "centers": centers[ok].tolist(), "n_presence": int(p.size)}
