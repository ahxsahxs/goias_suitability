"""Part 11 — CMIP6 delta-change future suitability & shift.

Delta-change (change-factor) projection. NEX-GDDP-CMIP6 monthly change factors —
a **ratio** for precip and an **additive Δ** for tasmax/tasmin — are computed per
GCM (future window vs. model historical), ensemble-averaged, and applied to the
**observed TerraClimate 1991-2020 monthly climatology**. The climate feature
bands are then re-derived with the *same* ``features.derive_climate_bands`` and the
Part-9 ``membership`` engine is re-run on a future feature stack (terrain / soil /
water / phenology / access static; only the climate block moves).

Because the baseline and the future bands share one derivation,
``suit_future - suit_present`` is a **pure climate signal** — identity factors
(ratio=1, Δ=0) reproduce ``feat_climate`` exactly. Delta-change also cancels most
GCM bias, which is why it is the standard, defensible downscaling here.

PET for the future uses a **Hargreaves ratio** applied to the observed baseline
PET: PET ∝ Ra·(Tmean+17.8)·√(Tmax−Tmin), and the 0.0023·Ra factor **cancels in
the future/baseline ratio**, so no solar-geometry / latitude term is needed.
Aridity then follows from future P and future PET. ``srad`` and soil moisture are
held at baseline — rsds is outside the pr/tasmax/tasmin ensemble, and soil
moisture needs a full water balance beyond delta-change scope; both are documented
caveats (srad feeds only solar suitability, soil moisture only cattle).

Ensemble-mean factors drive ``suit_future`` (one membership run); per-GCM factors
drive the ``agreement`` (sign-of-change) confidence layer. Builders are lazy (no
server call at import), so the module is import-/syntax-checkable without EE auth.
"""
from __future__ import annotations

import ee

import features
import membership
import utils


def _cfg() -> dict:
    return utils.cfg()["cmip6"]


# --- CMIP6 monthly climatologies & change factors ---------------------------
def _monthly_mean(model, scenario, years, band, aoi):
    """12-image month-tagged climatology of one NEX-GDDP band.

    Monthly mean of daily values for ``model``+``scenario`` over the inclusive
    ``years`` window, at the native ~0.25° grid (the change-factor field is smooth
    and is bilinearly resampled to 250 m later).
    """
    c = _cfg()
    coll = (
        ee.ImageCollection(c["id"])
        .filter(ee.Filter.eq("model", model))
        .filter(ee.Filter.eq("scenario", scenario))
        .filter(ee.Filter.calendarRange(years[0], years[1], "year"))
        .filterBounds(aoi)
        .select(band)
    )
    months = ee.List.sequence(1, 12)

    def per(m):
        m = ee.Number(m)
        return (
            coll.filter(ee.Filter.calendarRange(m, m, "month"))
            .mean()
            .rename(band)
            .set("month", m)
        )

    return ee.ImageCollection(months.map(per))


def _get(coll, m):
    """The single image of a month-tagged collection for month ``m``."""
    return ee.Image(coll.filter(ee.Filter.eq("month", m)).first())


def model_factors(model, scenario, window, aoi):
    """Per-GCM monthly change factors as 12 month-tagged images.

    Bands: ``pr_ratio`` (future/historical precip), ``dtmax`` / ``dtmin``
    (additive temperature change; K and °C are identical for a difference).
    """
    hist = _cfg()["historical"]
    pr_f = _monthly_mean(model, scenario, window, "pr", aoi)
    pr_h = _monthly_mean(model, "historical", hist, "pr", aoi)
    tx_f = _monthly_mean(model, scenario, window, "tasmax", aoi)
    tx_h = _monthly_mean(model, "historical", hist, "tasmax", aoi)
    tn_f = _monthly_mean(model, scenario, window, "tasmin", aoi)
    tn_h = _monthly_mean(model, "historical", hist, "tasmin", aoi)
    months = ee.List.sequence(1, 12)

    def fac(m):
        m = ee.Number(m)
        ratio = _get(pr_f, m).divide(_get(pr_h, m).max(1e-6)).rename("pr_ratio")
        dtmax = _get(tx_f, m).subtract(_get(tx_h, m)).rename("dtmax")
        dtmin = _get(tn_f, m).subtract(_get(tn_h, m)).rename("dtmin")
        return ee.Image.cat([ratio, dtmax, dtmin]).set("month", m)

    return ee.ImageCollection(months.map(fac))


def ensemble_factors(models, scenario, window, aoi):
    """Ensemble-mean monthly change factors (per-month average across GCMs)."""
    per_model = [model_factors(m, scenario, window, aoi) for m in models]
    months = ee.List.sequence(1, 12)

    def avg(m):
        m = ee.Number(m)
        imgs = ee.ImageCollection([_get(c, m) for c in per_model])
        return imgs.mean().set("month", m)

    return ee.ImageCollection(months.map(avg))


# --- apply factors to the observed baseline ---------------------------------
def baseline_monthly(aoi):
    """Observed TerraClimate 1991-2020 monthly climatology dict (reused unchanged)."""
    return features._terraclimate_monthly_dict(aoi)


def future_monthly(baseline: dict, factors, aoi):
    """Apply monthly change factors to the baseline TerraClimate monthly dict.

    Precip scaled by ``pr_ratio``; tmmx/tmmn shifted by ``dtmax``/``dtmin``; PET
    scaled by the Hargreaves ratio. ``def``/``aet``/``soil``/``vpd``/``srad`` are
    carried from baseline (held static — see module docstring). The factor fields
    are bilinearly resampled so the coarse 0.25° change signal interpolates
    smoothly onto the finer baseline grid. Returns a monthly dict in the exact
    shape ``features.derive_climate_bands`` consumes.
    """
    c_hg = float(_cfg()["hargreaves_c"])
    months = ee.List.sequence(1, 12)

    def _shift(key, op):
        def per(m):
            m = ee.Number(m)
            return op(_get(baseline[key], m), _get(factors, m)).rename(key).set("month", m)

        return ee.ImageCollection(months.map(per))

    fut_pr = _shift("pr", lambda b, f: b.multiply(f.select("pr_ratio").resample("bilinear")))
    fut_tx = _shift("tmmx", lambda b, f: b.add(f.select("dtmax").resample("bilinear")))
    fut_tn = _shift("tmmn", lambda b, f: b.add(f.select("dtmin").resample("bilinear")))

    def pet_per(m):
        m = ee.Number(m)
        txb, tnb = _get(baseline["tmmx"], m), _get(baseline["tmmn"], m)
        f = _get(factors, m)
        dtx = f.select("dtmax").resample("bilinear")
        dtn = f.select("dtmin").resample("bilinear")
        tmean_b = txb.add(tnb).divide(2)
        tmean_f = tmean_b.add(dtx.add(dtn).divide(2))
        range_b = txb.subtract(tnb).max(0.1)
        range_f = txb.add(dtx).subtract(tnb.add(dtn)).max(0.1)
        # PET_future / PET_baseline (0.0023*Ra cancels):
        pet_ratio = (
            tmean_f.add(c_hg)
            .divide(tmean_b.add(c_hg))
            .multiply(range_f.divide(range_b).sqrt())
        )
        return _get(baseline["pet"], m).multiply(pet_ratio).rename("pet").set("month", m)

    fut = dict(baseline)  # def/aet/soil/vpd/srad carried unchanged
    fut.update(pr=fut_pr, tmmx=fut_tx, tmmn=fut_tn, pet=ee.ImageCollection(months.map(pet_per)))
    return fut


def future_climate_image(baseline: dict, factors, aoi):
    """Future 14-band climate image on the 250 m grid (feature_stack layout)."""
    fut = future_monthly(baseline, factors, aoi)
    bands = features.derive_climate_bands(fut, utils.cfg()["climate"]["params"])
    return utils.to_grid_bilinear(bands).clip(aoi)


def stack_with_climate(project, climate, aoi):
    """Raw 34-band stack with ``climate`` swapped in for the climate block, in
    ``feature_stack_250m`` band order so ``membership`` consumes it unchanged.

    Used for both the future stack (CMIP6-adjusted climate) and the **rederived
    present** stack (on-the-fly ``features.climate_features``) — running both
    through one assembler is what lets the baseline cancel in the Δ (see
    ``suit_present_rederived``)."""
    imgs = features.load_stack_images(project)
    imgs["climate"] = climate
    ordered = [imgs[t] for t in features.STACK_THEMES]
    return ee.Image.cat(ordered).clip(aoi)


# --- future suitability, shift, agreement -----------------------------------
# ``extras`` (dict prefix->image, e.g. {"sit_": feat_siting, "rl_": realized}) carries
# the static side-image factors (solar clearness, pisci seasonal-water distance,
# conservation native-veg) through to the membership engine. They are **held at
# baseline** in the future exactly like srad/soil-moisture: clearness keys on
# baseline srad, the seasonal-water distance is static, and realized native cover is
# a present observation — so Δ reflects only the climate-driven factors (incl.
# solar's new ``clim_twarm_q`` heat de-rating, which *does* move with the future
# stack). The SAME ``extras`` must feed both present-rederived and future so they
# cancel in Δ.
def suit_future(project, models, scenario, window, aoi, lc, seg_cfg, base=None, extras=None):
    """Ensemble future suitability image (7 ``suit_*`` + 7 ``class_*`` bands)."""
    base = base if base is not None else baseline_monthly(aoi)
    fac = ensemble_factors(models, scenario, window, aoi)
    fclim = future_climate_image(base, fac, aoi)
    return membership.suit_present(stack_with_climate(project, fclim, aoi), lc, seg_cfg, extras)


def suit_present_rederived(project, aoi, lc, seg_cfg, extras=None):
    """Present suitability **recomputed on-the-fly** (rebuilt climate + cached
    static themes), the correct reference for ΔSuitability.

    ``delta`` must subtract *this*, not the exported ``suit_present`` asset:
    comparing the on-the-fly future against the stored asset injects a constant
    export-reprojection offset (verified — identity factors give Δ≈0 vs the
    rederived present but a spurious ±0.05–0.3 vs the asset). Subtracting a
    same-path present makes the baseline derivation cancel analytically, leaving a
    pure climate signal. Numerically ≈ the asset (to resampling noise)."""
    return membership.suit_present(
        stack_with_climate(project, features.climate_features(aoi), aoi), lc, seg_cfg, extras
    )


def delta(suit_future_img, suit_present_img, segments):
    """Per-segment ΔSuitability (future − present) as ``delta_<segment>`` bands."""
    bands = [
        suit_future_img.select(f"suit_{s}")
        .subtract(suit_present_img.select(f"suit_{s}"))
        .rename(f"delta_{s}")
        for s in segments
    ]
    return ee.Image.cat(bands)


def agreement(project, models, scenario, window, aoi, suit_present_img, lc, seg_cfg, base=None, extras=None):
    """Ensemble agreement = fraction of GCMs whose ΔSuitability sign matches the
    ensemble-mean sign, per segment (``agreement_<segment>`` in [0,1]).

    >0.5 ⇒ a majority of models agree on the direction of change at that pixel.
    Heavier than ``suit_future`` (one membership run **per GCM**) — export
    separately and/or coarsen the scale under tight quota.
    """
    base = base if base is not None else baseline_monthly(aoi)
    segs = list(seg_cfg["segments"])

    def _sign(suit_img):
        return ee.Image.cat([
            suit_img.select(f"suit_{s}").subtract(suit_present_img.select(f"suit_{s}")).rename(s)
            for s in segs
        ]).gt(0)

    ens = suit_future(project, models, scenario, window, aoi, lc, seg_cfg, base=base, extras=extras)
    ens_sign = _sign(ens)

    matches = []
    for m in models:
        fclim = future_climate_image(base, model_factors(m, scenario, window, aoi), aoi)
        sf = membership.suit_present(stack_with_climate(project, fclim, aoi), lc, seg_cfg, extras)
        matches.append(_sign(sf).eq(ens_sign))

    return ee.ImageCollection(matches).mean().rename([f"agreement_{s}" for s in segs])


# --- hindcast bias sanity (delta-change cancels bias; this is a report) -----
def hindcast_bias(models, aoi, scale=25000):
    """AOI-mean bias of the CMIP6 ensemble **historical** climate vs. observed
    TerraClimate (1991-2014/1991-2020 normals): annual precip (mm) and mean
    temperature (°C). Delta-change removes additive/multiplicative bias, so this
    is a *sanity* report, not part of the projection — magnitudes should be
    bounded/plausible, not zero. Returns a dict via ``reduceRegion``.
    """
    hist = _cfg()["historical"]

    def _model_annual(model):
        pr = _monthly_mean(model, "historical", hist, "pr", aoi)
        tx = _monthly_mean(model, "historical", hist, "tasmax", aoi)
        tn = _monthly_mean(model, "historical", hist, "tasmin", aoi)
        pr_ann = pr.map(lambda im: im.multiply(86400 * 30.4)).sum().rename("pr")  # mm/yr
        months = ee.List.sequence(1, 12)
        tmean = (
            ee.ImageCollection(
                months.map(lambda m: _get(tx, ee.Number(m)).add(_get(tn, ee.Number(m))).divide(2))
            )
            .mean()
            .subtract(273.15)
            .rename("tmean")
        )
        return pr_ann.addBands(tmean)

    cmip = ee.ImageCollection([_model_annual(m) for m in models]).mean()

    base = baseline_monthly(aoi)
    obs_pr = base["pr"].sum().rename("pr")
    obs_tmean = (
        ee.ImageCollection(
            ee.List.sequence(1, 12).map(
                lambda m: _get(base["tmmx"], ee.Number(m)).add(_get(base["tmmn"], ee.Number(m))).divide(2)
            )
        )
        .mean()
        .rename("tmean")
    )

    bias = cmip.subtract(ee.Image.cat([obs_pr, obs_tmean]))
    return bias.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=aoi, scale=scale,
        maxPixels=int(1e12), bestEffort=True, tileScale=16,
    )
