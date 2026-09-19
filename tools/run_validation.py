"""Part 14 validation on the recalibrated surfaces (headless mirror of notebook 14).

Runs each validation block independently (per-block try/except so a heavy step's
failure doesn't lose the others) and prints a clean, thesis-ready summary:
  1. Spearman rho  — municipal mean suitability vs MOD17 NPP (cropland-restricted)
  2. within-crop suitability->season-GPP gradient (the repaired validator)
  3. soybean Boyce index / AUC (presence vs suitability)
  4. ANOVA of MOD17 proxy across the (new k=7) zones
  5. RF-vs-knowledge Cohen's kappa (soybean)

Run:  EE_PROJECT=probformer ../.venv/bin/python tools/run_validation.py
"""
from __future__ import annotations

import sys
import time

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


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def aid(n):
    return utils.asset_id(P, n)


suit = ee.Image(aid("suit_present"))
# Use the CACHED feat_realized asset (not the live 30 m MapBiomas remap) — the live
# graph is what blew the interactive memory quota when fed into 10-20k-pixel samples.
realized = ee.Image(aid("feat_realized"))
Z = ee.Image(aid("feature_stack_250m_z"))
TS = 8  # tileScale: trade compute-tiles for lower per-tile memory
# T8 (2026-09): CAP was 4500 to keep a plain `.sample(...).getInfo()` under the
# 5000-element collection-query cap. Retrieval now goes through zoning.fc_to_df's
# paged `computeFeatures` reader instead (same one Part 10 already uses), which
# is NOT subject to that cap, so the sample can be much larger. GRID adds spatial
# stratification (zoning.build_strat_band) on top of each block's existing
# per-class restriction, so both dimensions T8 asks for (spatial + per-segment/
# per-class) are covered — rf_kappa already stratified by class (`presence`).
CAP = 20000
GRID = zoning.build_strat_band(AOI, n_side=8)


def block(name, fn):
    log(f"--- {name} ---")
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        log(f"  !! {name} FAILED: {type(e).__name__}: {e}")


# 1. Spearman rho — municipal mean suitability vs MOD17 (cropland-restricted) -----
def spearman_mod17():
    proxy = external.mod17_proxy(AOI)
    crop = external.cropland_mask(realized)
    muni = external.municipal_fc()
    agg = suit.select([f"suit_{s}" for s in SEGS]).addBands(proxy).updateMask(crop)
    feats = (external.municipal_means(muni, agg)
             .select([f"suit_{s}" for s in SEGS] + ["mod17_npp"], None, False)
             .getInfo()["features"])  # 243 municipalities — under the cap
    df = pd.DataFrame([f["properties"] for f in feats]).dropna()
    print(f"  municipalities n={len(df)}")
    for s in SEGS:
        r = metrics.spearman(df[f"suit_{s}"], df["mod17_npp"])
        print(f"  {s:14s} rho={r['rho']:+.3f}  p={r['p']:.1e}  n={r['n']}")


# 2. within-crop season-GPP gradient (repaired validator) -------------------------
def within_crop():
    gpp = external.season_gpp(AOI)
    n_strata = 8 * 8
    for crop in ["soybean", "sugarcane", "other_crops"]:
        m = realized.select("rl_role").eq(external.ROLE_CODES[crop])
        smp = (suit.select(f"suit_{crop}").addBands(gpp).addBands(GRID).updateMask(m)
               .stratifiedSample(numPoints=max(1, CAP // n_strata), classBand="strat_grid",
                                 region=AOI, scale=250, seed=7, dropNulls=True, tileScale=TS))
        g = zoning.fc_to_df(smp)
        r = metrics.within_crop_gradient(g[f"suit_{crop}"], g["season_gpp"])
        print(f"  {crop:12s} rho={r['rho']:+.3f} p={r['p']:.1e} n={r['n']} "
              f"monotonic={r['monotonic']}  bin_gpp={[round(v,4) for v in r['bin_gpp']]}")


# 3. soybean Boyce / AUC ----------------------------------------------------------
def boyce_auc():
    n_strata = 8 * 8
    smp = (suit.select("suit_soybean").addBands(realized.select("rl_role")).addBands(GRID)
           .stratifiedSample(numPoints=max(1, CAP // n_strata), classBand="strat_grid",
                             region=AOI, scale=250, seed=1, dropNulls=True, tileScale=TS))
    sdf = zoning.fc_to_df(smp)
    pres = sdf[sdf.rl_role == external.ROLE_CODES["soybean"]]["suit_soybean"]
    print(f"  soybean presence pixels in sample: {len(pres)} / {len(sdf)}")
    print("  soybean Boyce index:",
          round(metrics.continuous_boyce(pres, sdf["suit_soybean"])["boyce"], 3))
    sdf["is_soy"] = (sdf.rl_role == external.ROLE_CODES["soybean"]).astype(int)
    print("  soybean AUC:", round(metrics.auc(sdf["is_soy"], sdf["suit_soybean"])["auc"], 3))


# 4. ANOVA of MOD17 across the new zones ------------------------------------------
def anova_zones():
    proxy = external.mod17_proxy(AOI)
    zones = ee.Image(aid("zones_present")).rename("zone")
    n_strata = 8 * 8
    zs = (proxy.addBands(zones).addBands(GRID)
          .stratifiedSample(numPoints=max(1, CAP // n_strata), classBand="strat_grid",
                            region=AOI, scale=1000, seed=2, dropNulls=True, tileScale=TS))
    zdf = zoning.fc_to_df(zs)
    groups = {int(z): g["mod17_npp"].values for z, g in zdf.groupby("zone")}
    a = metrics.anova(groups)
    print(f"  zones present in sample: {sorted(groups)}")
    print(f"  F={a['F']:.1f} p={a['p']:.1e}")
    for z, mu, n in zip(sorted(groups), a["group_means"], a["group_n"]):
        print(f"    zone {z}: mean NPP={mu:.4f}  n={n}")


# 5. RF-vs-knowledge Cohen kappa (soybean) ----------------------------------------
def rf_kappa():
    z = Z
    lbl = realized.select("rl_role").eq(external.ROLE_CODES["soybean"]).rename("presence")
    train = z.addBands(lbl).stratifiedSample(
        numPoints=6000, classBand="presence", region=AOI, scale=250, seed=3,
        dropNulls=True, tileScale=TS)
    rf = (ee.Classifier.smileRandomForest(100).setOutputMode("PROBABILITY")
          .train(train, "presence", z.bandNames()))
    rf_cls = z.classify(rf).gte(0.5).rename("rf_cls")
    cmp = rf_cls.addBands(suit.select("class_soybean").gte(2).rename("kb_cls"))
    n_strata = 8 * 8
    cs = (cmp.addBands(GRID)
          .stratifiedSample(numPoints=max(1, CAP // n_strata), classBand="strat_grid",
                            region=AOI, scale=250, seed=4, dropNulls=True, tileScale=TS))
    cdf = zoning.fc_to_df(cs)
    k = metrics.cohen_kappa(cdf["rf_cls"], cdf["kb_cls"])
    kb_share = cdf["kb_cls"].mean()
    rf_share = cdf["rf_cls"].mean()
    print(f"  soybean RF-vs-knowledge Cohen kappa = {k['kappa']:+.3f}  n={k['n']}")
    print(f"  knowledge S2+ share={kb_share:.3f}   RF high-prob share={rf_share:.3f}")


def main():
    log(f"=== Part 14 validation (recalibrated surfaces, project={P}) ===")
    block("1. Spearman rho vs MOD17 (municipal, cropland)", spearman_mod17)
    block("2. within-crop season-GPP gradient", within_crop)
    block("3. soybean Boyce / AUC", boyce_auc)
    block("4. ANOVA MOD17 across zones", anova_zones)
    block("5. RF-vs-knowledge Cohen kappa (soybean)", rf_kappa)
    log("=== validation complete ===")


if __name__ == "__main__":
    main()
