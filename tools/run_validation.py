"""Part 14 validation on the recalibrated surfaces (headless mirror of notebook 14).

Runs each validation block independently (per-block try/except so a heavy step's
failure doesn't lose the others) and prints a clean, thesis-ready summary:
  1. Spearman rho  — municipal mean suitability vs MOD17 NPP (cropland-restricted)
  2. within-crop suitability->season-GPP gradient (the repaired validator)
  3. presence discrimination (AUC / Boyce) for soybean, sugarcane, other_crops
  4. ANOVA of MOD17 proxy across the zones
  5. RF-vs-knowledge Cohen's kappa (soybean)

CALIBRATION / VALIDATION HOLDOUT
--------------------------------
Every metric is reported three times: on the calibration half, on the held-out
half, and on the full territory. The held-out column is the one the thesis should
quote, because the model's parameters -- membership breakpoints, sigma(mu) and
hence the AHP weights, the clustering centroids -- were estimated without seeing
that half.

WHAT (val - calib) IS, AND WHAT IT IS NOT
------------------------------------------
It is NOT an optimism gap, and must not be reported as one. Blocks 1-4 all score
ONE surface (`suit_present`) on two sets of pixels: the raster is identical for
both halves, so the difference between the columns is overwhelmingly a difference
between two halves of Goias -- composition, climate, realized land use -- not a
difference between in-sample and out-of-sample performance. With ~15 blocks per
half that territorial difference is large: it is why several metrics score HIGHER
on the held-out half, which no optimism gap can do.

Only block 5 is a genuine train/test contrast, because the random forest is the
only thing here actually fitted to pixel labels, and it is fitted on the
calibration half alone.

The column is therefore labelled `half_delta` and documented as a
between-halves difference. Isolating the estimation effect would need the same
surface re-derived from full-domain weights and re-scored on the held-out half;
that is a separate experiment, not something this table shows.

Each block draws its Earth Engine sample ONCE, carrying the `split` band, and
partitions it offline. Drawing twice would double the EE cost and -- worse -- the
two halves would come from different stratifiedSample realizations, so the
between-halves difference would be confounded with sampling noise. There is no
$SPLIT_HALF switch here for that reason.

The split is read from the cached `calib_val_split` asset via utils.split_image,
never recomputed, so every stage of the cascade sees bit-identical halves.

Results are written to thesis/Chapters/validation_metrics.csv and
validation_zone_anova.csv as well as printed, so the thesis tables and the
dashboard scorecard read the numbers instead of re-typing them. Zone ids are
reported 1-based (the zones_present raster is 0-based).

Run:  EE_PROJECT=probformer uv run python tools/run_validation.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

import ee  # noqa: E402
import pandas as pd  # noqa: E402
import utils  # noqa: E402
import external  # noqa: E402
import metrics  # noqa: E402
import zoning  # noqa: E402

P = utils.init()
AOI = utils.load_aoi(P)
SEGS = list(utils.cfg("segments")["segments"])

# House pattern: CSVs land in thesis/Chapters/; $SCRATCHPAD overrides.
REPO = Path(__file__).resolve().parent.parent
CHAPTERS = REPO / "thesis" / "Chapters"
OUT = Path(os.environ.get("SCRATCHPAD", str(CHAPTERS)))
OUT.mkdir(parents=True, exist_ok=True)

# Flat accumulator: every block appends {metric, segment, half, value, ...} rows
# here and main() writes them once, so a block that fails loses only its own rows.
METRICS: list[dict] = []

# Reporting domains. "full" is kept alongside the two halves because it is the
# number every previous run of this tool produced, so it is the continuity row
# against which the holdout's effect can be read.
HALVES = ("calib", "val", "full")


def record(metric, value, *, segment="", half="", n=None, p=None, extra=""):
    METRICS.append({"metric": metric, "segment": segment, "half": half,
                    "value": value, "n": n, "p": p, "extra": extra})


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def aid(n):
    return utils.asset_id(P, n)


def by_half(df):
    """Yield (half_label, subframe) for the three reporting domains.

    Offline partition of ONE sample -- see the module docstring on why the halves
    must not come from separate EE draws.
    """
    for half in HALVES:
        if half == "full":
            yield half, df
        elif half == "calib":
            yield half, df[df["split"] == 0]
        else:
            yield half, df[df["split"] == 1]


suit = ee.Image(aid("suit_present"))
# Use the CACHED feat_realized asset (not the live 30 m MapBiomas remap) — the live
# graph is what blew the interactive memory quota when fed into 10-20k-pixel samples.
realized = ee.Image(aid("feat_realized"))
Z = ee.Image(aid("feature_stack_250m_z"))
SPLIT = utils.split_image(P).rename("split")
TS = 8  # tileScale: trade compute-tiles for lower per-tile memory
# T8 (2026-09): CAP was 4500 to keep a plain `.sample(...).getInfo()` under the
# 5000-element collection-query cap. Retrieval now goes through zoning.fc_to_df's
# paged `computeFeatures` reader instead (same one Part 10 already uses), which
# is NOT subject to that cap, so the sample can be much larger. GRID adds spatial
# stratification (zoning.build_strat_band) on top of each block's existing
# per-class restriction, so both dimensions T8 asks for (spatial + per-segment/
# per-class) are covered — rf_kappa already stratified by class (`presence`).
CAP = 20000
# Presence metrics get their own, larger cap. other_crops covers ~0.6% of GO+DF,
# so a 20k draw yields ~100 presences -- ~50 per half, which cannot support an AUC.
# At 60k it is ~290 / ~145. Deliberately NOT a presence-stratified booster: AUC is
# prevalence-invariant, but metrics.continuous_boyce uses the BACKGROUND
# distribution as its expected-frequency denominator, so inflating presences would
# silently change what Boyce means. One unbiased draw at larger n is the only
# correct fix.
CAP_PRESENCE = 60000
GRID = zoning.build_strat_band(AOI, n_side=8)
N_STRATA = 8 * 8
PRESENCE_CROPS = ("soybean", "sugarcane", "other_crops")


def block(name, fn):
    log(f"--- {name} ---")
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        log(f"  !! {name} FAILED: {type(e).__name__}: {e}")


# 1. Spearman rho — municipal mean suitability vs MOD17 (cropland-restricted) -----
def spearman_mod17():
    """Municipal means, computed per half from that half's PIXELS.

    The holdout holds out PIXELS, not municipalities. n is NOT preserved at 247:
    a municipality enters a half's column only if it has cropland pixels in that
    half, and the dropna below removes the rest. Measured: 186 municipalities in
    the calibration column and 159 in the validation one, which sum to more than
    247 because 98 contribute to both.

    An earlier version of this docstring claimed n stayed at 247 because "most
    municipalities straddle a block boundary". That reasoning was written for the
    45 km grid and was not revised when the blocks became ~130 km. At 130 km the
    mean GO municipality (~1 380 km2, ~37 km across) usually sits WHOLLY inside
    one block, so its cropland pixels fall wholly in one half -- which is exactly
    why the two columns lose about a quarter of the municipalities each.

    The consequence is that at this block size, restricting pixels and assigning
    whole municipalities are nearly the same procedure. Pixels are still the
    better choice, for one reason only: it needs no arbitrary majority rule and
    it lets the 98 boundary-straddling municipalities inform both columns instead
    of being forced into one. It does NOT buy back the power that halving costs.

    The caveat that belongs in the caption: a half-restricted municipal mean is a
    noisier estimate of the municipality's true mean, which only weakens a
    correlation. That bias is DOWNWARD, i.e. conservative -- it can attenuate a
    real association but cannot manufacture one.
    """
    proxy = external.mod17_proxy(AOI)
    crop = external.cropland_mask(realized)
    muni = external.municipal_fc()
    base = suit.select([f"suit_{s}" for s in SEGS]).addBands(proxy)
    bands = [f"suit_{s}" for s in SEGS] + ["mod17_npp"]

    # One reduceRegions over a 3x-wide image: same municipalities, three pixel
    # domains, one server call.
    masks = {"calib": crop.And(SPLIT.eq(0)), "val": crop.And(SPLIT.eq(1)),
             "full": crop}
    img = ee.Image.cat([
        base.updateMask(m).rename([f"{b}__{h}" for b in bands])
        for h, m in masks.items()
    ])
    feats = (external.municipal_means(muni, img)
             .select([f"{b}__{h}" for h in masks for b in bands], None, False)
             .getInfo()["features"])  # 247 municipalities — under the cap
    raw = pd.DataFrame([f["properties"] for f in feats])

    for half in HALVES:
        cols = [f"{b}__{half}" for b in bands]
        df = raw[cols].dropna()
        df.columns = bands
        print(f"  [{half}] municipalities n={len(df)}")
        for s in SEGS:
            r = metrics.spearman(df[f"suit_{s}"], df["mod17_npp"])
            print(f"    {s:14s} rho={r['rho']:+.3f}  p={r['p']:.1e}  n={r['n']}")
            record("spearman_mod17", r["rho"], segment=s, half=half,
                   n=r["n"], p=r["p"])


# 2. within-crop season-GPP gradient (repaired validator) -------------------------
def within_crop():
    gpp = external.season_gpp(AOI)
    for crop in PRESENCE_CROPS:
        m = realized.select("rl_role").eq(external.ROLE_CODES[crop])
        smp = (suit.select(f"suit_{crop}").addBands(gpp).addBands(GRID)
               .addBands(SPLIT).updateMask(m)
               .stratifiedSample(numPoints=max(1, CAP // N_STRATA),
                                 classBand="strat_grid", region=AOI, scale=250,
                                 seed=7, dropNulls=True, tileScale=TS))
        g = zoning.fc_to_df(smp)
        for half, sub in by_half(g):
            if len(sub) < 50:
                print(f"  {crop:12s} [{half}] n={len(sub)} — too few, skipped")
                continue
            r = metrics.within_crop_gradient(sub[f"suit_{crop}"], sub["season_gpp"])
            print(f"  {crop:12s} [{half:5s}] rho={r['rho']:+.3f} p={r['p']:.1e} "
                  f"n={r['n']} monotonic={r['monotonic']}")
            record("within_crop_gpp_rho", r["rho"], segment=crop, half=half,
                   n=r["n"], p=r["p"], extra=f"monotonic={r['monotonic']}")


# 3. presence discrimination: AUC + Boyce, all three crops ------------------------
def presence_metrics():
    """One draw, three crops, three halves.

    Until 2026-10-03 soybean came from here (GRID-stratified, n~16k) while
    sugarcane and other_crops came from tools/extract_present.py with a UNIFORM
    .sample(numPixels=4500) -- different estimator, different n, different
    stratification, printed as three rows of one table. That is what let the
    thesis print AUC 0.871 against a CSV that said 0.846. One code path now.
    """
    smp = (suit.select([f"suit_{c}" for c in PRESENCE_CROPS])
           .addBands(realized.select("rl_role")).addBands(GRID).addBands(SPLIT)
           .stratifiedSample(numPoints=max(1, CAP_PRESENCE // N_STRATA),
                             classBand="strat_grid", region=AOI, scale=250,
                             seed=1, dropNulls=True, tileScale=TS))
    sdf = zoning.fc_to_df(smp)
    log(f"  presence sample n={len(sdf)}")
    for crop in PRESENCE_CROPS:
        code = external.ROLE_CODES[crop]
        for half, sub in by_half(sdf):
            score = sub[f"suit_{crop}"]
            is_p = (sub.rl_role == code).astype(int)
            n_pres = int(is_p.sum())
            if n_pres < 30:
                print(f"  {crop:12s} [{half:5s}] presences={n_pres} — too few, "
                      f"not reported")
                record("presence_underpowered", float("nan"), segment=crop,
                       half=half, n=len(sub), extra=f"presences={n_pres}")
                continue
            auc = metrics.auc(is_p, score)["auc"]
            boyce = metrics.continuous_boyce(score[is_p == 1], score)["boyce"]
            print(f"  {crop:12s} [{half:5s}] AUC={auc:.4f} Boyce={boyce:.4f} "
                  f"n={len(sub)} presences={n_pres}")
            record("auc", auc, segment=crop, half=half, n=len(sub),
                   extra=f"presences={n_pres}")
            record("boyce", boyce, segment=crop, half=half, n=len(sub),
                   extra=f"presences={n_pres}")


# 4. ANOVA of MOD17 across the zones ----------------------------------------------
def anova_zones():
    proxy = external.mod17_proxy(AOI)
    zones = ee.Image(aid("zones_present")).rename("zone")
    zs = (proxy.addBands(zones).addBands(GRID).addBands(SPLIT)
          .stratifiedSample(numPoints=max(1, CAP // N_STRATA),
                            classBand="strat_grid", region=AOI, scale=1000,
                            seed=2, dropNulls=True, tileScale=TS))
    zdf = zoning.fc_to_df(zs)
    rows = []
    for half, sub in by_half(zdf):
        # raster is 0-based, reporting is 1-based
        groups = {int(z) + 1: g["mod17_npp"].values for z, g in sub.groupby("zone")}
        groups = {k: v for k, v in groups.items() if len(v) >= 2}
        if len(groups) < 2:
            print(f"  [{half}] fewer than 2 populated zones — skipped")
            continue
        a = metrics.anova(groups)
        print(f"  [{half:5s}] zones={sorted(groups)} F={a['F']:.1f} p={a['p']:.1e}")
        for z, mu, n in zip(sorted(groups), a["group_means"], a["group_n"]):
            print(f"      zone {z}: mean NPP={mu:.4f}  n={n}")
            rows.append({"half": half, "zone": z, "mean_npp": mu, "n": n,
                         "F": a["F"], "p": a["p"]})
        record("anova_F", a["F"], half=half, extra=f"k={len(groups)}", p=a["p"])
    path = OUT / "validation_zone_anova.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  wrote {path}")


# 5. RF-vs-knowledge Cohen kappa (soybean) ----------------------------------------
def rf_kappa():
    """The one genuine train/test split in the suite.

    The RF is TRAINED on calibration-half pixels only and still CLASSIFIES the
    whole AOI -- it is a product-equivalent surface, and restricting the output
    extent would compare two different maps instead of two different samples of
    one map.

    This is the ONLY block whose (val - calib) is a genuine train/test contrast:
    everything else scores one fixed surface on two sets of pixels, so there the
    difference is territorial, not an optimism gap. Until 2026-10-03 training
    (seed 3) and evaluation (seed 4) were both drawn from the whole territory, so
    kappa = +0.268 was an in-sample number.
    """
    z = Z
    lbl = realized.select("rl_role").eq(external.ROLE_CODES["soybean"]).rename("presence")
    train = (z.addBands(lbl).updateMask(SPLIT.eq(0))
             .stratifiedSample(numPoints=6000, classBand="presence", region=AOI,
                               scale=250, seed=3, dropNulls=True, tileScale=TS))
    rf = (ee.Classifier.smileRandomForest(100).setOutputMode("PROBABILITY")
          .train(train, "presence", z.bandNames()))
    rf_cls = z.classify(rf).gte(0.5).rename("rf_cls")
    cmp = rf_cls.addBands(suit.select("class_soybean").gte(2).rename("kb_cls"))
    cs = (cmp.addBands(GRID).addBands(SPLIT)
          .stratifiedSample(numPoints=max(1, CAP // N_STRATA),
                            classBand="strat_grid", region=AOI, scale=250,
                            seed=4, dropNulls=True, tileScale=TS))
    cdf = zoning.fc_to_df(cs)
    for half, sub in by_half(cdf):
        k = metrics.cohen_kappa(sub["rf_cls"], sub["kb_cls"])
        kb_share = sub["kb_cls"].mean()
        rf_share = sub["rf_cls"].mean()
        print(f"  [{half:5s}] kappa={k['kappa']:+.4f} n={k['n']}  "
              f"knowledge S2+ share={kb_share:.4f}  RF high-prob share={rf_share:.4f}")
        record("cohen_kappa_rf", k["kappa"], segment="soybean", half=half, n=k["n"],
               extra="trained on calib half")
        record("kb_s2plus_share", kb_share, segment="soybean", half=half, n=k["n"])
        record("rf_highprob_share", rf_share, segment="soybean", half=half, n=k["n"])


def half_delta_table(df):
    """val - calib per (metric, segment).

    A BETWEEN-HALVES difference, not an optimism gap -- see the module docstring.
    """
    piv = df.pivot_table(index=["metric", "segment"], columns="half",
                         values="value", aggfunc="first")
    if not {"calib", "val"}.issubset(piv.columns):
        return None
    piv["half_delta"] = piv["val"] - piv["calib"]
    return piv.reset_index()


def main():
    log(f"=== Part 14 validation (holdout-aware, project={P}) ===")
    log(f"    split asset: {aid(utils.SPLIT_ASSET)}  (0=calib, 1=val)")
    block("1. Spearman rho vs MOD17 (municipal, cropland)", spearman_mod17)
    block("2. within-crop season-GPP gradient", within_crop)
    block("3. presence discrimination (AUC / Boyce)", presence_metrics)
    block("4. ANOVA MOD17 across zones", anova_zones)
    block("5. RF-vs-knowledge Cohen kappa", rf_kappa)
    if METRICS:
        df = pd.DataFrame(METRICS)
        path = OUT / "validation_metrics.csv"
        df.to_csv(path, index=False)
        log(f"wrote {path} ({len(df)} rows)")
        tab = half_delta_table(df)
        if tab is not None:
            pd.set_option("display.width", 200)
            log("between-halves difference (val - calib; NOT an optimism "
                "gap -- see the module docstring):\n"
                + tab[["metric", "segment", "calib", "val", "full",
                       "half_delta"]].round(4).to_string(index=False))
    else:
        log("!! no metrics recorded -- every block failed")
    log("=== validation complete ===")


if __name__ == "__main__":
    main()
