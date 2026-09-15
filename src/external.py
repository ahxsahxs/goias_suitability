"""Phase-B data builders (Parts 12-14, GEE-only): GAUL-L2 municipal units,
MapBiomas realized-use masks/fractions, and the MODIS MOD17 productivity proxy.

Guardrail: land cover / productivity are **mask + validation + descriptive
profiling only** — never a suitability or clustering input (circularity). The
realized-use masks may *replace* the coarse Part-7b WorldCover mask for a
higher-fidelity re-run of the Part-9 membership, but MapBiomas never enters the
feature stack or the clusterer.

Builders are lazy (no server call until a value is pulled), so this module is
import-/syntax-checkable without Earth Engine authentication — mirroring
``src/features.py``.
"""
from __future__ import annotations

import ee

from utils import cfg, grid_projection, to_grid_bilinear

# Segment-role codes for the majority-role band `rl_role` (0 = other/none).
ROLE_CODES = {
    "soybean": 1,
    "sugarcane": 2,
    "other_crops": 3,
    "pisciculture": 4,
    "pasture": 5,
    "native": 6,
}

# MOD17A3HGF Npp valid raw range is [-30000, 32700]; 32761-32767 are fills.
_MOD17_FILL_MIN = 32701
# MOD17A2H Gpp valid raw range is [0, 30000]; 32761-32767 are fills.
_MOD17_GPP_FILL_MIN = 32761

# Austral summer crop canopy window for the growing-season GPP validator: the
# months when annual summer crops (soy / corn / cotton / sorghum) carry green
# canopy in the Cerrado. Integrating GPP over this window (not the whole year)
# removes the dry-season bare-fallow artifact that made annual NPP anti-correlate
# with crop suitability. Sugarcane (near year-round) overrides with all 12 months.
GROWING_MONTHS = [10, 11, 12, 1, 2, 3]


# =============================================================================
# Part 12 — municipal units (GAUL level-2)
# =============================================================================
def municipal_fc() -> "ee.FeatureCollection":
    """GO+DF ADM2 municipal units from GAUL level-2 (243 features)."""
    g = cfg()["gaul_l2"]
    return (
        ee.FeatureCollection(g["asset"])
        .filter(ee.Filter.eq("ADM0_NAME", g["adm0_name"]))
        .filter(ee.Filter.inList("ADM1_NAME", g["adm1_names"]))
    )


def municipal_means(fc, img, scale: int = 250):
    """Per-municipality mean of every band of ``img`` (``reduceRegions``).

    Keeps the join key (``ADM2_NAME``) and ADM1 name; drops geometry-heavy
    properties. The result is a FeatureCollection ready for an ``Export.table``
    to CSV or a small ``getInfo`` for offline joins/rankings.
    """
    return img.reduceRegions(
        collection=fc, reducer=ee.Reducer.mean(), scale=scale, tileScale=8
    )


# =============================================================================
# Part 13 — MapBiomas realized use (masks + per-role fractions + majority role)
# =============================================================================
def _mapbiomas_band(year: int | None = None) -> str:
    mb = cfg()["mapbiomas"]
    return mb["band_pattern"].format(year=year or mb["current_year"])


def mapbiomas_year(aoi, year: int | None = None) -> "ee.Image":
    """The raw (30 m) MapBiomas class band for ``year``, clipped to AOI."""
    mb = cfg()["mapbiomas"]
    return ee.Image(mb["asset"]).select(_mapbiomas_band(year)).clip(aoi)


def realized_features(aoi, year: int | None = None) -> "ee.Image":
    """250 m realized-use image (Brazil-specific parallel to Part-7b).

    Bands:
      ``rl_mode``            majority MapBiomas class in the 250 m cell
      ``rl_role``            majority-class remapped to a segment role (see ROLE_CODES)
      ``mask_available``     majority class is convertible foreground (crop/pasture/grass)
      ``mask_excluded``      majority class is never eligible (urban/mining/water/bare-nonveg)
      ``rl_<role>_frac``     area fraction of each realized role within the cell

    The two ``mask_*`` bands are drop-in for ``membership.apply_mask`` — pass this
    image (with conservation's ``lc_tree_frac`` carried from the WorldCover layer,
    see ``hybrid_lc``) to ``membership.suit_present`` for a MapBiomas-masked re-run.
    """
    remap_cfg = cfg("mapbiomas_classes")
    realized = remap_cfg["realized"]
    excluded = remap_cfg["excluded"]
    available = remap_cfg["available"]

    lc = ee.Image(cfg()["mapbiomas"]["asset"]).select(_mapbiomas_band(year))
    proj = grid_projection()

    mode = (
        lc.reduceResolution(ee.Reducer.mode(), maxPixels=1024)
        .reproject(proj)
        .rename("rl_mode")
    )

    # majority class -> segment role (unmapped classes -> 0 = other/none)
    role_from, role_to = [], []
    for role, codes in realized.items():
        for c in codes:
            role_from.append(int(c))
            role_to.append(ROLE_CODES[role])
    rl_role = mode.remap(role_from, role_to, 0).rename("rl_role")

    mask_excluded = mode.remap(excluded, [1] * len(excluded), 0).rename("mask_excluded")
    mask_available = mode.remap(available, [1] * len(available), 0).rename("mask_available")

    def role_frac(codes, name):
        return (
            lc.remap([int(c) for c in codes], [1] * len(codes), 0)
            .reduceResolution(ee.Reducer.mean(), maxPixels=1024)
            .reproject(proj)
            .rename(name)
        )

    fracs = [role_frac(codes, f"rl_{role}_frac") for role, codes in realized.items()]

    return ee.Image.cat([mode, rl_role, mask_available, mask_excluded, *fracs]).clip(aoi)


def hybrid_lc(worldcover_lc, realized):
    """Swap the WorldCover masks for the MapBiomas masks, keep ``lc_tree_frac``.

    Produces an ``lc`` image consumable unchanged by ``membership.suit_present``:
    the crop/pasture foreground fidelity comes from MapBiomas, while conservation's
    sanctioned supportive factor (``lc_tree_frac``) is retained from WorldCover.
    """
    return worldcover_lc.addBands(
        realized.select(["mask_available", "mask_excluded"]), overwrite=True
    )


# =============================================================================
# Part 13 — potential-vs-realized (RQ2 core)
# =============================================================================
def underutilization(suit, realized, segments, min_class: int = 2):
    """Per-segment under-utilization mask: suitable-or-better (FAO class >= S2)
    **and** not currently in that realized use.

    Returns one 0/1 band ``underused_<seg>`` per segment that carries a realized
    role (crops / pisciculture / pasture-cattle). Descriptive RQ2 layer — never
    fed back into suitability.
    """
    role = realized.select("rl_role")
    bands = []
    for seg in segments:
        if seg not in ROLE_CODES:
            continue
        hi = suit.select(f"class_{seg}").gte(min_class)
        not_this = role.neq(ROLE_CODES[seg])
        bands.append(hi.And(not_this).rename(f"underused_{seg}"))
    return ee.Image.cat(bands)


# =============================================================================
# Part 14 — MODIS MOD17 productivity proxy (validation only; never a feature)
# =============================================================================
def mod17_proxy(aoi) -> "ee.Image":
    """Multi-year-mean MOD17 annual NPP on the 250 m grid (fills removed).

    A *vegetation primary-productivity* surrogate for yield — coarse, and never a
    suitability/clustering input. Used only for the cropland-restricted Spearman
    validation against municipal mean suitability.
    """
    p = cfg()["productivity"]["npp"]
    y0, y1 = cfg()["productivity"]["period"]
    coll = (
        ee.ImageCollection(p["id"])
        .filterDate(f"{y0}-01-01", f"{y1 + 1}-01-01")
        .filterBounds(aoi)
    )

    def clean(img):
        raw = img.select(p["band"])
        return raw.updateMask(raw.lt(_MOD17_FILL_MIN)).multiply(p["scale"]).rename("mod17_npp")

    mean = coll.map(clean).mean()
    return to_grid_bilinear(mean).rename("mod17_npp").clip(aoi)


def season_gpp(aoi, months=None, year_range=None) -> "ee.Image":
    """Growing-season MOD17A2H **GPP** on the 250 m grid — the repaired crop validator.

    Mean 8-day GPP over the crop's canopy window (``months``; default
    ``GROWING_MONTHS``) pooled across years, so the dry-season fallow composites
    that made annual NPP anti-correlate with crop suitability are excluded. Mask
    it to a single crop's realized MapBiomas pixels (``realized.rl_role == code``)
    at the call site and correlate against that crop's suitability — the
    **within-crop** productivity gradient (``metrics.within_crop_gradient``). This
    validates *how much* crops produce; presence AUC/Boyce validates *where*.
    Still shares residual signal with the in-stack ``phen_integral`` (documented).
    """
    p = cfg()["productivity"]["gpp"]
    months = months or GROWING_MONTHS
    y0, y1 = year_range or cfg()["productivity"]["period"]
    mfilter = ee.Filter.Or(*[ee.Filter.calendarRange(m, m, "month") for m in months])
    coll = (
        ee.ImageCollection(p["id"])
        .filterDate(f"{y0}-01-01", f"{y1 + 1}-01-01")
        .filterBounds(aoi)
        .filter(mfilter)
    )

    def clean(img):
        raw = img.select(p["band"])
        return raw.updateMask(raw.lt(_MOD17_GPP_FILL_MIN)).multiply(p["scale"]).rename("season_gpp")

    mean = coll.map(clean).mean()
    return to_grid_bilinear(mean).rename("season_gpp").clip(aoi)


def cropland_mask(realized):
    """1 where the majority realized role is an annual/perennial crop or pasture.

    Restricts the MOD17 comparison to managed land (the potential-vs-realized
    *productivity* domain), following the Phase-B plan.
    """
    role = realized.select("rl_role")
    crop_pasture = [ROLE_CODES[r] for r in ("soybean", "sugarcane", "other_crops", "pasture")]
    return role.remap(crop_pasture, [1] * len(crop_pasture), 0).rename("cropland")
