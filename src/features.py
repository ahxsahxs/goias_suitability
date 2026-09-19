"""Feature builders for Phase-A Parts 1-8.

Every builder returns an ``ee.Image`` already harmonized to the 250 m grid and
clipped to the AOI. Builders are lazy (no server call until a value is pulled),
so this module imports without Earth Engine authentication.
"""
from __future__ import annotations

import math

import ee

from utils import (
    cfg,
    grid_projection,
    scale_m,
    to_grid_bilinear,
    to_grid_mean,
)

_TWO_PI = 2.0 * math.pi
_DEG2RAD = math.pi / 180.0


# =============================================================================
# Part 1 — AOI
# =============================================================================
def aoi_fc() -> "ee.FeatureCollection":
    """Goiás + DF municipalities from the IBGE 2025 malha municipal mesh."""
    import ibge_mesh

    return ibge_mesh.municipal_ee_fc()


def aoi_geometry() -> "ee.Geometry":
    """Dissolved GO+DF outer boundary — see ibge_mesh.aoi_ee_geometry."""
    import ibge_mesh

    return ibge_mesh.aoi_ee_geometry()


def aoi_dissolved_fc() -> "ee.FeatureCollection":
    return ee.FeatureCollection([ee.Feature(aoi_geometry())])


# =============================================================================
# Part 2 — Climate & water-balance features (TerraClimate)
# =============================================================================
def _terraclimate_monthly(aoi) -> "ee.ImageCollection":
    c = cfg()["climate"]["terraclimate"]
    bands = list(c["bands"].keys())
    factors = [c["bands"][b]["scale"] for b in bands]
    coll = (
        ee.ImageCollection(c["id"])
        .filterDate(c["period"][0], c["period"][1])
        .filterBounds(aoi)
        .select(bands)
    )

    def scale_img(img):
        scaled = img.multiply(ee.Image.constant(factors)).rename(bands)
        return scaled.copyProperties(img, ["system:time_start"])

    return coll.map(scale_img)


def _monthly_clim(coll, band) -> "ee.ImageCollection":
    """12-image collection: climatological mean of ``band`` for each month."""
    months = ee.List.sequence(1, 12)

    def per(m):
        m = ee.Number(m)
        return (
            coll.select(band)
            .filter(ee.Filter.calendarRange(m, m, "month"))
            .mean()
            .rename(band)
            .set("month", m)
        )

    return ee.ImageCollection(months.map(per))


def _terraclimate_monthly_dict(aoi) -> dict:
    """Baseline 12-month TerraClimate climatology per band (month-tagged collections)."""
    coll = _terraclimate_monthly(aoi)
    keys = ["pr", "pet", "def", "aet", "soil", "vpd", "srad", "tmmx", "tmmn"]
    return {k: _monthly_clim(coll, k) for k in keys}


def derive_climate_bands(monthly: dict, params: dict) -> "ee.Image":
    """The 14-band climate feature image from month-tagged monthly climatologies.

    ``monthly`` maps each TerraClimate band name to a 12-image month-tagged
    collection (one band per image). Returns the **ungridded** ``ee.Image.cat`` of
    the 14 climate bands. Factored out of ``climate_features`` so the *identical*
    derivation runs on the baseline **and** on CMIP6-adjusted future monthly fields
    (Part 11) — that is what makes ``suit_future - suit_present`` a pure climate
    signal rather than a methodology artifact (identity factors reproduce
    ``feat_climate`` exactly).
    """
    pr_m, pet_m, def_m = monthly["pr"], monthly["pet"], monthly["def"]
    aet_m, soil_m, vpd_m = monthly["aet"], monthly["soil"], monthly["vpd"]
    srad_m, tmx_m, tmn_m = monthly["srad"], monthly["tmmx"], monthly["tmmn"]

    # annual aggregates (sum of 12 monthly means)
    ann_pr = pr_m.sum().rename("clim_pr_annual")
    ann_pet = pet_m.sum().rename("clim_pet_annual")
    ann_def = def_m.sum().rename("clim_def_annual")          # climate water deficit (CWD)
    ann_aet = aet_m.sum().rename("clim_aet_annual")

    # precip seasonality CV = stdDev / mean across the 12 monthly means
    pr_mean = pr_m.mean()
    pr_std = pr_m.reduce(ee.Reducer.stdDev())
    cv = pr_std.divide(pr_mean.max(0.001)).rename("clim_pr_cv")

    # dry-season length = number of months with mean P < threshold
    thr = params["dry_month_pr_mm"]
    dry_len = (
        pr_m.map(lambda im: im.lt(thr)).sum().rename("clim_dry_months")
    )

    # wet-season precip = sum of months wetter than the overall monthly mean
    wet = (
        pr_m.map(lambda im: im.updateMask(im.gte(pr_mean)).unmask(0))
        .sum()
        .rename("clim_pr_wet")
    )

    # aridity index = annual P / annual PET
    aridity = ann_pr.divide(ann_pet.max(0.001)).rename("clim_aridity")

    soil_mean = soil_m.mean().rename("clim_soil_moist")
    vpd_mean = vpd_m.mean().rename("clim_vpd")
    srad_mean = srad_m.mean().rename("clim_srad")

    # monthly mean-temperature climatology -> GDD, warmest/coldest quarter
    months = ee.List.sequence(1, 12)

    def tmean_month(m):
        m = ee.Number(m)
        tx = tmx_m.filter(ee.Filter.eq("month", m)).first()
        tn = tmn_m.filter(ee.Filter.eq("month", m)).first()
        return tx.add(tn).divide(2).rename("tmean").set("month", m)

    tmean_m = ee.ImageCollection(months.map(tmean_month))

    base = params["gdd_base_c"]

    def gdd_month(m):
        m = ee.Number(m)
        t = tmean_m.filter(ee.Filter.eq("month", m)).first()
        return t.subtract(base).max(0).multiply(30.4).rename("gdd")

    gdd = ee.ImageCollection(months.map(gdd_month)).sum().rename("clim_gdd")

    def quarter_mean(m):
        m = ee.Number(m)
        idx = ee.List([m, m.add(1), m.add(2)]).map(
            lambda x: ee.Number(x).subtract(1).mod(12).add(1)
        )
        return tmean_m.filter(ee.Filter.inList("month", idx)).mean().rename("q")

    quarters = ee.ImageCollection(months.map(quarter_mean))
    t_warm = quarters.max().rename("clim_twarm_q")
    t_cold = quarters.min().rename("clim_tcold_q")

    return ee.Image.cat(
        [ann_pr, ann_pet, ann_def, ann_aet, cv, dry_len, wet, aridity,
         soil_mean, vpd_mean, srad_mean, gdd, t_warm, t_cold]
    )


def climate_features(aoi) -> "ee.Image":
    monthly = _terraclimate_monthly_dict(aoi)
    out = derive_climate_bands(monthly, cfg()["climate"]["params"])
    return to_grid_bilinear(out).clip(aoi)


# =============================================================================
# Part 3 — Terrain features (SRTM + HydroSHEDS)
# =============================================================================
def terrain_features(aoi) -> "ee.Image":
    t = cfg()["terrain"]
    dem = ee.Image(t["srtm"])
    elev = dem.select("elevation")
    products = ee.Terrain.products(dem)
    slope = products.select("slope")          # degrees
    aspect = products.select("aspect")        # degrees

    northing = aspect.multiply(_DEG2RAD).cos().rename("terr_northing")
    easting = aspect.multiply(_DEG2RAD).sin().rename("terr_easting")

    # coarsen 30 m terrain -> 250 m grid first, then derive TPI/TWI on the grid
    # (a 2-pixel kernel at 250 m, instead of a ~33-pixel kernel at 30 m)
    base = ee.Image.cat(
        [elev.rename("terr_elev"), slope.rename("terr_slope"), northing, easting]
    )
    base250 = to_grid_mean(base)

    # TPI on the 250 m grid: pixel-based kernel + reproject so the result is
    # scale-stable (a meters kernel collapses to 0 px when sampled coarser).
    elev250 = base250.select("terr_elev")
    tpi_px = max(1, round(t["tpi_radius_m"] / scale_m()))
    tpi = (
        elev250.subtract(
            elev250.focalMean(radius=tpi_px, kernelType="circle", units="pixels")
        )
        .reproject(grid_projection())
        .rename("terr_tpi")
    )

    # TWI = ln( specific-catchment-area / tan(slope) ) using HydroSHEDS flow accum
    acc = ee.Image(t["hydrosheds_acc"]).select(0)
    tan_slope = base250.select("terr_slope").multiply(_DEG2RAD).tan().max(0.001)
    twi = (
        acc.add(1).multiply(scale_m()).divide(tan_slope).log().rename("terr_twi")
    )
    twi250 = to_grid_bilinear(twi)

    return ee.Image.cat([base250, tpi, twi250]).clip(aoi)


# =============================================================================
# Part 4 — Soil features (OpenLandMap, 0-30 cm)
# =============================================================================
def soil_features(aoi) -> "ee.Image":
    s = cfg()["soil"]
    depths = s["depths_bands"]
    layers = []
    for key, spec in s["layers"].items():
        img = (
            ee.Image(spec["id"])
            .select(depths)
            .reduce(ee.Reducer.mean())
            .multiply(spec["scale"])
            .rename(f"soil_{key}")
        )
        layers.append(img)
    return to_grid_bilinear(ee.Image.cat(layers)).clip(aoi)


# =============================================================================
# Part 5 — Hydrology & water-access features (JRC GSW + HydroSHEDS)
# =============================================================================
def water_features(aoi) -> "ee.Image":
    w = cfg()["water"]
    gsw = ee.Image(w["gsw"])
    permanent = gsw.select("occurrence").gt(w["occurrence_threshold"])

    # distance-to-permanent-water (m), computed on the 250 m grid
    perm250 = permanent.unmask(0).reproject(grid_projection())
    dist_px = perm250.fastDistanceTransform(1024, "pixels").sqrt()
    dist_m = dist_px.multiply(scale_m()).rename("water_dist")

    seas = to_grid_bilinear(gsw.select("seasonality").unmask(0)).rename(
        "water_seasonality"
    )

    # drainage density: fraction of stream cells in a neighborhood
    acc = ee.Image(w["hydrosheds_acc"]).select(0)
    streams = acc.gt(w["stream_acc_threshold"]).unmask(0)
    dd = streams.reduceNeighborhood(
        ee.Reducer.mean(), ee.Kernel.circle(w["drainage_radius_m"], "meters")
    ).rename("water_drain_density")
    dd250 = to_grid_bilinear(dd)

    return ee.Image.cat([dist_m, seas, dd250]).clip(aoi)


# =============================================================================
# Part 6 — Vegetation phenology features (MODIS MOD13Q1, harmonic fit)
# =============================================================================
def phenology_features(aoi) -> "ee.Image":
    """Phenometrics from a harmonic fit to the **12-month NDVI climatology**.

    Fitting to a monthly climatology (12 images) instead of every 16-day
    composite (~460 images) is ~38x cheaper for the same seasonal-cycle
    metrics (mean / amplitude / peak timing), which keeps the export within
    Earth Engine's per-task compute budget.
    """
    ph = cfg()["phenology"]
    sc = ph["ndvi_scale"]
    qa = ph["qa_band"]
    n_harm = ph["harmonics"]

    coll = (
        ee.ImageCollection(ph["modis"])
        .filterDate(ph["period"][0], ph["period"][1])
        .filterBounds(aoi)
        .map(lambda img: img.select("NDVI").multiply(sc).rename("NDVI")
             .updateMask(img.select(qa).lte(1))
             .copyProperties(img, ["system:time_start"]))
    )

    months = ee.List.sequence(1, 12)

    def monthly(m):
        m = ee.Number(m)
        ndvi = (
            coll.filter(ee.Filter.calendarRange(m, m, "month")).mean().rename("NDVI")
        )
        t = m.subtract(0.5).divide(12)  # fraction of year at month centre
        regressors = ee.Image.cat(
            [
                ee.Image(1).rename("constant"),
                ee.Image(t.multiply(_TWO_PI)).cos().rename("cos1"),
                ee.Image(t.multiply(_TWO_PI)).sin().rename("sin1"),
                ee.Image(t.multiply(2 * _TWO_PI)).cos().rename("cos2"),
                ee.Image(t.multiply(2 * _TWO_PI)).sin().rename("sin2"),
            ]
        )
        return regressors.addBands(ndvi).set("month", m)

    clim = ee.ImageCollection(months.map(monthly))

    independents = ["constant", "cos1", "sin1"]
    if n_harm >= 2:
        independents += ["cos2", "sin2"]

    reg = clim.select(independents + ["NDVI"]).reduce(
        ee.Reducer.linearRegression(numX=len(independents), numY=1)
    )
    coeffs = reg.select("coefficients").arrayProject([0]).arrayFlatten([independents])

    a1, b1 = coeffs.select("cos1"), coeffs.select("sin1")
    amp = a1.hypot(b1).rename("phen_amplitude")
    phase = b1.atan2(a1)
    peak_month = (
        phase.divide(_TWO_PI).multiply(12).add(12).mod(12).add(1).rename("phen_peak_month")
    )
    mean_ndvi = clim.select("NDVI").mean().rename("phen_mean")
    integral = mean_ndvi.multiply(365).rename("phen_integral")  # NDVI-days proxy

    out = ee.Image.cat([mean_ndvi, amp, peak_month, integral])
    return to_grid_bilinear(out).clip(aoi)


# =============================================================================
# Part 7 — Market-access feature (Oxford accessibility)
# =============================================================================
def access_features(aoi) -> "ee.Image":
    a = cfg()["access"]
    acc = ee.Image(a["oxford"]).select(a["band"])
    log_acc = acc.max(0).add(1).log().rename("access_logtt")
    return to_grid_bilinear(log_acc).clip(aoi)


# =============================================================================
# Part 7b — Generic land-cover mask (ESA WorldCover)  [mask/context only]
# =============================================================================
def landcover_features(aoi) -> "ee.Image":
    lc = cfg()["landcover"]
    cls = lc["classes"]
    coll = ee.ImageCollection(lc["worldcover"])
    native = coll.first().projection()  # 10 m; mosaic() drops the default projection
    wc = coll.mosaic().select(lc["band"]).setDefaultProjection(native)
    proj = grid_projection()

    mode = (
        wc.reduceResolution(ee.Reducer.mode(), maxPixels=1024)
        .reproject(proj)
        .rename("lc_mode")
    )

    def frac(code, name):
        return (
            wc.eq(code)
            .reduceResolution(ee.Reducer.mean(), maxPixels=1024)
            .reproject(proj)
            .rename(name)
        )

    tree = frac(cls["tree"], "lc_tree_frac")
    crop = frac(cls["crop"], "lc_crop_frac")
    grass = frac(cls["grass"], "lc_grass_frac")

    excluded = mode.remap(lc["excluded"], [1] * len(lc["excluded"]), 0).rename(
        "mask_excluded"
    )
    available = mode.remap(lc["available"], [1] * len(lc["available"]), 0).rename(
        "mask_available"
    )

    return ee.Image.cat([mode, tree, crop, grass, excluded, available]).clip(aoi)


# =============================================================================
# Part 7c — Siting features (solar/pisciculture; NOT in the stack) [2026-07-14]
# =============================================================================
# Catalog-only biophysical bands that give the two low-variance segments real
# discriminating structure. Deliberately kept OUT of STACK_THEMES so the 34-band
# feature stack and the zoning are unchanged; consumed by the membership engine
# via the `sit_` band-routing (see src/membership._source_image). Guardrail: these
# are biophysical/irradiance/hydrology fields, never land use.

def _extraterrestrial_radiation(aoi) -> "ee.Image":
    """Annual-mean top-of-atmosphere shortwave Ra (W/m²), FAO-56 (Allen 1998).

    Function of latitude + day-of-year only (no data). Used to normalize observed
    surface ``srad`` into a clearness index Kt = Rs/Ra (a cloudiness proxy that
    injects genuine spatial structure the near-uniform surface srad lacks).
    """
    lat = ee.Image.pixelLonLat().select("latitude").multiply(_DEG2RAD)
    gsc = 0.0820  # solar constant, MJ m-2 min-1
    months = ee.List.sequence(1, 12)

    def ra_month(m):
        m = ee.Number(m)
        j = m.multiply(30.4).subtract(15)          # mid-month day-of-year
        dr = j.multiply(_TWO_PI / 365.0).cos().multiply(0.033).add(1)   # inverse Earth-Sun dist
        dec = j.multiply(_TWO_PI / 365.0).subtract(1.39).sin().multiply(0.409)  # solar declination
        ws = lat.tan().multiply(-1).multiply(dec.tan()).clamp(-1, 1).acos()      # sunset hour angle
        ra = (
            ws.multiply(lat.sin()).multiply(dec.sin())
            .add(lat.cos().multiply(dec.cos()).multiply(ws.sin()))
            .multiply(dr)
            .multiply(24 * 60 / math.pi * gsc)     # MJ m-2 day-1
        )
        return ra.rename("ra")

    ra_ann = ee.ImageCollection(months.map(ra_month)).mean()
    return ra_ann.multiply(11.574)                 # MJ m-2 day-1 -> W m-2


def siting_features(aoi) -> "ee.Image":
    """``feat_siting`` — solar/pisciculture siting bands on the 250 m grid.

    - ``sit_clearness``       clearness index Kt = surface srad / extraterrestrial Ra
                              (0-1; higher = clearer sky = better PV yield).
    - ``sit_water_dist_seas`` distance (m) to **semi-permanent** water (GSW occurrence
                              > ``seasonal_occurrence_threshold``); un-floors pisciculture,
                              whose old factor keyed on 13-km-distant permanent water.
    """
    proj = grid_projection()

    # surface srad (annual mean, W/m²) — identical derivation to clim_srad
    srad = _monthly_clim(_terraclimate_monthly(aoi), "srad").mean()
    ra = _extraterrestrial_radiation(aoi)
    clearness = to_grid_bilinear(
        srad.divide(ra.max(1e-6)).clamp(0, 1).rename("sit_clearness")
    )

    thr = cfg()["water"].get("seasonal_occurrence_threshold", 50)
    gsw = ee.Image(cfg()["water"]["gsw"]).select("occurrence")
    wet = gsw.gt(thr).unmask(0).reproject(proj)
    dist = (
        wet.fastDistanceTransform(1024, "pixels").sqrt()
        .multiply(scale_m())
        .rename("sit_water_dist_seas")
    )

    return ee.Image.cat([clearness, dist]).clip(aoi)


# =============================================================================
# Part 7d — Conservation-value side bands (feat_conservation; NOT in the stack) [2026-07-25]
# =============================================================================
# Catalog-only conservation-VALUE / priority factors that ground conservation in
# systematic-conservation-planning criteria (connectivity, habitat heterogeneity,
# carbon service) rather than "where native vegetation currently is". Deliberately
# kept OUT of STACK_THEMES so the 34-band stack and the zoning are unchanged;
# consumed by the membership engine via the ``cv_`` band-routing (see
# src/membership._source_image). Guardrail: WDPA is a *governance* layer, not land
# cover; ruggedness is terrain; biomass carbon is an ecosystem-service value — none
# is a land-use class. Conservation's remaining land-cover input is the DEMOTED
# ``rl_native_frac`` (the single sanctioned exception), routed separately via ``rl_``.

def conservation_features(aoi) -> "ee.Image":
    """``feat_conservation`` — conservation-value side bands on the 250 m grid.

    - ``cv_pa_dist``    distance (m) to the nearest protected area (WDPA polygons);
                        a connectivity / consolidation proxy (0 inside a reserve,
                        growing outward). Decreasing membership → near reserves scores
                        high. Governance layer, not land cover (mild remoteness caveat).
    - ``cv_ruggedness`` neighbourhood std of elevation (m) — terrain heterogeneity
                        (microhabitat diversity) and low arability. Increasing.
    - ``cv_carbon``     aboveground biomass carbon density (Mg C/ha) — a carbon-storage
                        ecosystem-service value. Increasing. (Mildly correlated with
                        forest cover — a documented caveat; kept at modest weight.)
    """
    c = cfg()["conservation"]
    proj = grid_projection()

    # distance to protected areas (WDPA polygons -> binary raster -> distance transform,
    # identical idiom to water_dist / sit_water_dist_seas)
    pa = ee.FeatureCollection(c["wdpa"]).filterBounds(aoi)
    pa_img = ee.Image().byte().paint(pa, 1).unmask(0).reproject(proj)
    pa_dist = (
        pa_img.fastDistanceTransform(1024, "pixels").sqrt()
        .multiply(scale_m())
        .rename("cv_pa_dist")
    )

    # terrain ruggedness = neighbourhood std of elevation on the 250 m grid
    # (reproject so a pixel kernel is scale-stable, as for terr_tpi)
    dem = ee.Image(cfg()["terrain"]["srtm"]).select("elevation")
    elev250 = to_grid_mean(dem)
    r_px = int(c.get("ruggedness_radius_px", 3))
    ruggedness = (
        elev250.reduceNeighborhood(
            ee.Reducer.stdDev(), ee.Kernel.circle(r_px, "pixels")
        )
        .reproject(proj)
        .rename("cv_ruggedness")
    )

    # aboveground biomass carbon density (ecosystem-service value)
    b = c["biomass"]
    carbon = ee.ImageCollection(b["id"]).mosaic().select(b["band"])
    carbon250 = to_grid_bilinear(carbon.unmask(0)).rename("cv_carbon")

    return ee.Image.cat([pa_dist, ruggedness, carbon250]).clip(aoi)


# =============================================================================
# Part 8 — Feature-stack assembly (250 m): raw + z-scored
# =============================================================================
# Continuous themes that enter the clustering stack (land cover excluded — it is
# a mask/context layer, never a clustering feature).
STACK_THEMES = ("climate", "terrain", "soil", "water", "phenology", "access")

THEME_BUILDERS = {
    "climate": climate_features,
    "terrain": terrain_features,
    "soil": soil_features,
    "water": water_features,
    "phenology": phenology_features,
    "access": access_features,
    "landcover": landcover_features,
    "siting": siting_features,        # Part 7c; consumed via membership sit_ routing, not stacked
    "conservation": conservation_features,  # Part 7d; consumed via membership cv_ routing, not stacked
}

# Cached per-theme asset names (Part 8 loads these rather than recomputing —
# keeps the stack export cheap and matches the plan's caching intent).
# NOTE: `siting` is a cached feat_* asset but is deliberately absent from
# STACK_THEMES — it feeds solar/pisciculture membership only, never the stack.
THEME_ASSETS = {
    "climate": "feat_climate",
    "terrain": "feat_terrain",
    "soil": "feat_soil",
    "water": "feat_water",
    "phenology": "feat_phenology",
    "access": "feat_access",
    "siting": "feat_siting",
    "conservation": "feat_conservation",   # Part 7d; feeds conservation membership only, never the stack
}


def load_stack_images(project: str) -> dict:
    """Load the cached feat_* assets for the continuous stack themes."""
    import utils

    return {
        t: ee.Image(utils.asset_id(project, THEME_ASSETS[t])) for t in STACK_THEMES
    }


def assemble_stack(images: dict, aoi, stats_scale: int | None = None):
    """Concatenate per-theme 250 m images -> (raw stack, z-scored stack).

    ``images`` maps theme name -> ee.Image (already on the grid). Only the
    continuous STACK_THEMES are used; z-scoring uses AOI mean/std per band.
    The z output stays at 250 m; the mean/std are estimated at ``stats_scale``
    (default 1 km — ~identical statistics, far cheaper than 250 m).
    """
    ordered = [images[t] for t in STACK_THEMES if t in images]
    raw = ee.Image.cat(ordered).clip(aoi)
    bn = raw.bandNames()

    rr = dict(geometry=aoi, scale=stats_scale or scale_m() * 4, maxPixels=int(1e13),
              bestEffort=True, tileScale=16)
    means = raw.reduceRegion(reducer=ee.Reducer.mean(), **rr)
    stds = raw.reduceRegion(reducer=ee.Reducer.stdDev(), **rr)

    mean_img = ee.Image.constant(means.values(bn)).rename(bn)
    std_img = ee.Image.constant(stds.values(bn)).rename(bn)
    z = raw.subtract(mean_img).divide(std_img).clip(aoi)
    return raw, z


# =============================================================================
# Revision point 5 — spatial magnitude of climate vs. terrain/soil local
# variability (companion to membership.variance_shares' pooled decomposition).
# =============================================================================
def local_std(z_img, bands, radius_px, proj=None):
    """Neighbourhood stdDev of each band in ``bands`` of a z-scored image.

    Generalizes the ``cv_ruggedness`` idiom (this module, conservation_features)
    from a single band (elevation) to an arbitrary band list. One output band
    per input band, named ``<band>_std``.
    """
    proj = proj or grid_projection()
    return (
        z_img.select(bands)
        .reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.circle(radius_px, "pixels"))
        .reproject(proj)
        .rename([f"{b}_std" for b in bands])
    )


def theme_roughness_image(z_img, theme_bands, radii_m, scale=None):
    """Per-theme-group local roughness at multiple window radii.

    ``theme_bands`` maps group name -> list of z-scored band names (e.g.
    ``{"climate": [...14 clim_* bands], "terrain_soil": [...12 terr_/soil_
    bands], "water": [...], "phenology": [...], "access": [...]}``). Bands are
    already z-scored, so the mean local stdDev across a group's bands is
    directly comparable across groups without further normalization — the same
    rationale ``membership.variance_shares`` uses to pool across AHP factors.

    Returns one ``ee.Image`` with bands ``rough_<group>_r<radius_m>``.
    """
    scale = scale or scale_m()
    proj = grid_projection()
    out = []
    for r_m in radii_m:
        r_px = max(1, round(r_m / scale))
        kernel = ee.Kernel.circle(r_px, "pixels")
        for group, bands in theme_bands.items():
            # Accumulate one band at a time (never hold all of a group's N
            # per-band stdDev results as a single N-band Image): a multi-band
            # intermediate node at this kernel radius blows getThumbURL's
            # per-node output-size cap (observed: 14 climate bands at ~1M
            # output pixels ~= 112 MiB > 80 MiB), even though the final output
            # here is just one averaged band.
            acc = ee.Image.constant(0).float()
            for b in bands:
                std = (z_img.select(b)
                       .reduceNeighborhood(ee.Reducer.stdDev(), kernel)
                       .reproject(proj))
                acc = acc.add(std)
            out.append(acc.divide(len(bands)).rename(f"rough_{group}_r{r_m}"))
    return ee.Image.cat(out)
