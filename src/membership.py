"""Part 9 — knowledge-based suitability engine (FAO land evaluation + AHP).

Standardize each factor of `feature_stack_250m` to a [0,1] fuzzy membership,
combine per segment with a **weighted geometric mean** (AHP weights; limiting-
factor behavior), mask with the Part-7b land-cover masks, and classify into FAO
**S1/S2/S3/N**. Everything is config-driven from ``config/segments.yaml`` and
returns an ``ee.Image`` already on the 250 m grid.

Builders are lazy (no server call until a value is pulled), so this module is
import-/syntax-checkable without Earth Engine authentication. Pass the segments
config in (``utils.cfg('segments')``) — this keeps the module decoupled.

Asset inputs: raw stack ``feature_stack_250m`` (Part 8) + ``feat_landcover``
(Part 7b masks). Land cover feeds suitability only via conservation's sanctioned
``lc_tree_frac`` supportive factor (see segments.yaml guardrail note).
"""
from __future__ import annotations

import ee

# Factor bands whose name carries one of these prefixes are sourced from a side
# image rather than the feature stack (keeps solar/pisci siting bands and the
# conservation native-veg factor OUT of the clustering/suitability stack while
# still consumable by the membership engine). ``lc_`` -> feat_landcover always;
# ``sit_``/``rl_`` -> the images passed in ``extras`` (siting / realized-use).
# Guardrail: only conservation's sanctioned native/tree factor and the two
# siting segments use side images; nothing enters the stack or clusterer.
_LC_PREFIX = "lc_"


def _source_image(band, stack, lc, extras):
    """Pick the image a factor band is read from, by name prefix."""
    if band.startswith(_LC_PREFIX):
        return lc
    if extras:
        for prefix, img in extras.items():
            if band.startswith(prefix):
                return img
    return stack


# --- fuzzy membership shapes -------------------------------------------------
def _ramp_up(x, a, b):
    """0 for x<=a, linear to 1 at x>=b."""
    return x.subtract(a).divide(b - a).clamp(0, 1)


def _ramp_down(x, a, b):
    """1 for x<=a, linear to 0 at x>=b."""
    return ee.Image(b).subtract(x).divide(b - a).clamp(0, 1)


def membership(img, band, spec):
    """One factor -> [0,1] suitability image per its membership ``spec``."""
    x = img.select(band)
    t, p = spec["type"], spec["points"]
    if t == "increasing":
        m = _ramp_up(x, p[0], p[1])
    elif t == "decreasing":
        m = _ramp_down(x, p[0], p[1])
    elif t == "range":
        m = _ramp_up(x, p[0], p[1]).min(_ramp_down(x, p[2], p[3]))
    else:
        raise ValueError(f"unknown membership type {t!r} for band {band}")
    return m.clamp(0, 1).rename("m")


# --- aggregation -------------------------------------------------------------
def weighted_geomean(images, weights, eps=1e-3):
    """Weighted geometric mean of [0,1] images: exp(sum w_i * ln m_i).

    Weights need not be pre-normalized; they are normalized to sum 1 here so the
    result stays in [0,1]. The ``eps`` floor keeps a fully-limiting factor a
    strong-but-finite penalty (avoids log(0) -> NaN); hard exclusion is the
    mask's job, not the membership's.
    """
    tot = float(sum(weights))
    log_sum = None
    for im, w in zip(images, weights):
        term = im.clamp(0, 1).max(eps).log().multiply(w / tot)
        log_sum = term if log_sum is None else log_sum.add(term)
    return log_sum.exp()


def weighted_arithmetic(images, weights):
    """Weighted arithmetic mean of [0,1] images: Σ w_i m_i (weights normalized).

    The **compensatory** aggregation (a weighted linear combination, the standard in
    GIS-MCDA / systematic conservation planning): a high score on one criterion
    *compensates* for a low score on another, so land has value if it is strong on
    *any* of several criteria. This is the correct aggregation for a **value/priority
    index** (conservation), as opposed to the limiting-factor geometric mean used for
    biophysical growth-*suitability* (a crop needs every requirement met at once).
    """
    tot = float(sum(weights))
    acc = None
    for im, w in zip(images, weights):
        term = im.clamp(0, 1).multiply(w / tot)
        acc = term if acc is None else acc.add(term)
    return acc


_AGGREGATORS = {"geomean": weighted_geomean, "arithmetic": weighted_arithmetic}


def apply_mask(suit, lc, policy):
    """Apply a land-cover masking policy to a suitability image."""
    if policy == "available":
        return suit.multiply(lc.select("mask_available"))
    if policy == "exclude_only":
        return suit.multiply(lc.select("mask_excluded").Not())
    if policy == "none":
        return suit
    raise ValueError(f"unknown mask policy {policy!r}")


def classify_fao(suit, breaks):
    """Continuous [0,1] suitability -> FAO class code (N=0, S3=1, S2=2, S1=3)."""
    return suit.gte(breaks[0]).add(suit.gte(breaks[1])).add(suit.gte(breaks[2]))


# --- per-segment & full suitability -----------------------------------------
def _factor_images(stack, lc, factors, extras=None):
    """Build the membership image + weight for each factor of a segment.

    ``extras`` optionally maps a band-name prefix (e.g. ``"sit_"``, ``"rl_"``) to
    a side image so siting / realized-use factors can be sourced without entering
    the feature stack (see ``_source_image``).
    """
    images, weights = [], []
    for band, spec in factors.items():
        src = _source_image(band, stack, lc, extras)
        images.append(membership(src, band, spec))
        weights.append(spec["weight"])
    return images, weights


def _aggregate(images, weights, seg_spec, cfg):
    """Combine factor memberships by the segment's aggregation rule.

    ``aggregate: geomean`` (default) is the limiting-factor weighted geometric mean —
    correct for biophysical growth-suitability. ``aggregate: arithmetic`` is the
    compensatory weighted linear combination — used by conservation, a value/priority
    index where strength on one criterion offsets weakness on another (§3.2.2)."""
    if seg_spec.get("aggregate", "geomean") == "arithmetic":
        return weighted_arithmetic(images, weights)
    return weighted_geomean(images, weights, cfg["aggregation"]["epsilon"])


def segment_suitability(stack, lc, seg_spec, cfg, extras=None):
    """Masked [0,1] suitability for one segment."""
    images, weights = _factor_images(stack, lc, seg_spec["factors"], extras)
    suit = _aggregate(images, weights, seg_spec, cfg)
    return apply_mask(suit, lc, seg_spec["mask"])


def suit_present(stack, lc, cfg, extras=None):
    """7-segment suitability image: `suit_<seg>` (0-1) + `class_<seg>` (FAO code).

    ``extras`` (dict prefix->image) supplies side-image factors — pass
    ``{"sit_": siting_img, "rl_": realized_img}`` for the rescaled solar/pisci
    siting factors and conservation's native-veg factor. ``None`` reproduces the
    original stack+lc behavior exactly.
    """
    breaks = cfg["fao_classes"]["breaks"]
    bands = []
    for name, seg in cfg["segments"].items():
        suit = segment_suitability(stack, lc, seg, cfg, extras).rename(f"suit_{name}")
        cls = classify_fao(suit, breaks).rename(f"class_{name}")
        bands += [suit, cls]
    return ee.Image.cat(bands)


# --- comparative best-use (unequal-permissiveness footing) ------------------
def comparative_present(suit, region, segments, scale=1000):
    """Per-segment z-normalized suitability + a `best_use` argmax band.

    Segments differ in permissiveness (cattle saturates high, solar low), so the
    *absolute* argmax is uninformative. Standardizing each ``suit_<seg>`` to zero
    mean / unit std over the region puts them on common footing; ``comp_<seg>`` is
    the standardized surface and ``best_use`` is the argmax segment **index** (into
    ``segments`` order). Masked-out pixels (suit==0) get a strongly negative
    comp and never win, so ``best_use`` respects each segment's eligibility mask.
    Stats use only positive (eligible) pixels per band. Lazy; evaluate via export.
    """
    bands = [f"suit_{s}" for s in segments]
    s = suit.select(bands)
    pos = s.updateMask(s.gt(0))
    rr = dict(geometry=region, scale=scale, maxPixels=int(1e13),
              bestEffort=True, tileScale=16)
    mean = pos.reduceRegion(ee.Reducer.mean(), **rr)
    std = pos.reduceRegion(ee.Reducer.stdDev(), **rr)
    mean_img = ee.Image.constant(mean.values(bands)).rename(bands)
    std_img = ee.Image.constant(std.values(bands)).rename(bands).max(1e-6)
    comp = s.subtract(mean_img).divide(std_img)
    comp_named = comp.rename([f"comp_{seg}" for seg in segments])
    best = comp.toArray().arrayArgmax().arrayGet([0]).rename("best_use")
    return comp_named.addBands(best)


# --- factor-variance decomposition (which factors actually discriminate) ----
def segment_membership_image(stack, lc, seg_spec, cfg, extras=None):
    """Per-factor membership image (``mem_<factor>`` bands), the memberships *before*
    the weighted geomean — sample it, then feed ``variance_shares`` to see which
    factors drive a segment's spatial variance (WS-D; defends the 'saturated climate
    factor as feasibility gate' design and the soil-dependence, W6)."""
    images, _ = _factor_images(stack, lc, seg_spec["factors"], extras)
    bands = [im.rename(f"mem_{b}") for im, b in zip(images, seg_spec["factors"].keys())]
    return ee.Image.cat(bands)


def variance_shares(M, weights, eps=1e-3, arithmetic=False):
    """Per-factor share of the spatial variance of suitability (sums to 1).

    For the geometric mean S = exp(Σ wᵢ ln mᵢ), the transformed total is ln S =
    Σ wᵢ ln mᵢ, so Var(ln S) = Σᵢ wᵢ Cov(ln mᵢ, ln S) and shareᵢ = wᵢ·Cov(ln mᵢ, ln S)/
    Var(ln S). For the compensatory arithmetic mean (``arithmetic=True``, conservation)
    S = Σ wᵢ mᵢ directly, so shareᵢ = wᵢ·Cov(mᵢ, S)/Var(S). Either way the shares sum to
    exactly 1 and quantify how much each factor drives the surface's spatial variation:
    a saturated (near-constant) membership contributes ≈0 regardless of its nominal AHP
    weight, exposing which factors are the real discriminators.

    ``M`` is an (n_samples, n_factors) array of memberships in [0,1]; ``weights``
    aligns to its columns. Returns a list of shares in column order.
    """
    import numpy as np

    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    T = np.clip(np.asarray(M, dtype=float), 0.0, 1.0)
    if not arithmetic:
        T = np.log(np.clip(T, eps, 1.0))             # transform to the additive scale
    total = T @ w                                    # (n,)
    var = float(total.var())
    if var <= 0:
        return [0.0] * len(w)
    cov = np.array([np.cov(T[:, i], total)[0, 1] for i in range(T.shape[1])])
    return (w * cov / var).tolist()


# --- siting screens (low-variance segments) ---------------------------------
def segment_spatial_std(suit, region, segments, scale=1000):
    """Per-segment spatial std of suitability over eligible land (the variance
    test). A segment with σ ≲ 0.15 is honestly presented as a feasibility/siting
    screen rather than a graded productivity surface. Returns an ``ee.Dictionary``
    ``suit_<seg> -> σ``."""
    bands = [f"suit_{s}" for s in segments]
    s = suit.select(bands)
    s = s.updateMask(s.gt(0))
    return s.reduceRegion(
        reducer=ee.Reducer.stdDev(), geometry=region, scale=scale,
        maxPixels=int(1e13), bestEffort=True, tileScale=16)


def feasibility_screen(suit_band, cut=0.5):
    """Near-binary siting screen: 1 where suitable-or-better (>= ``cut``), else 0.

    The honest rendering for an irradiance-homogeneous (solar) or point/reservoir-
    sited (pisciculture) use whose graded surface has near-zero spatial variance —
    low variance is then reported as a finding, not hidden (robustness_plan §4)."""
    return suit_band.gte(cut)


# --- weight-sensitivity (robustness) ----------------------------------------
def _perturbed_weights(weights, delta):
    """One-at-a-time +/-delta perturbations of each weight (renormalized later)."""
    scenarios = []
    for i in range(len(weights)):
        for s in (1.0 + delta, 1.0 - delta):
            w = list(weights)
            w[i] = weights[i] * s
            scenarios.append(w)
    return scenarios


def segment_sensitivity(stack, lc, seg_spec, cfg, extras=None):
    """Robustness band = spread (max-min) of suitability over +/-delta AHP sweeps.

    Smaller = more robust to the AHP weights. Memberships are reused across
    scenarios; only the weights change.
    """
    images, weights = _factor_images(stack, lc, seg_spec["factors"], extras)
    delta = cfg["aggregation"]["sensitivity_delta"]

    def masked(w):
        return apply_mask(_aggregate(images, w, seg_spec, cfg), lc, seg_spec["mask"])

    base = masked(weights)
    mn, mx = base, base
    for w in _perturbed_weights(weights, delta):
        s = masked(w)
        mn, mx = mn.min(s), mx.max(s)
    return mx.subtract(mn)


def sensitivity_present(stack, lc, cfg, extras=None):
    """`sens_<seg>` robustness band per segment (heavier compute than suit_present)."""
    bands = [
        segment_sensitivity(stack, lc, seg, cfg, extras).rename(f"sens_{name}")
        for name, seg in cfg["segments"].items()
    ]
    return ee.Image.cat(bands)


# --- AHP utilities (offline; for thesis-grade weight elicitation) ------------
def consistency_ratio(matrix):
    """AHP consistency ratio + priority vector from a Saaty pairwise matrix.

    Returns ``(cr, weights)``. ``cr <= 0.10`` is the acceptability threshold.
    Weights in segments.yaml are elicited priorities used directly; this helper
    is available to back them with a pairwise matrix when one is provided.
    """
    import numpy as np

    A = np.asarray(matrix, dtype=float)
    n = A.shape[0]
    w = (A / A.sum(axis=0)).mean(axis=1)        # column-normalized priority vector
    lam = float((A @ w / w).mean())             # principal eigenvalue (approx)
    ci = (lam - n) / (n - 1) if n > 1 else 0.0
    ri = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12,
          6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}.get(n, 1.49)
    cr = ci / ri if ri else 0.0
    return cr, w.tolist()
