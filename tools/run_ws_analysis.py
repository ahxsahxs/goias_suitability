"""WS-B validation strengthening + WS-D diagnostics on the reconceptualized surfaces.

Headless, per-block try/except, cached assets + tileScale + capped samples (the
established compute-safe pattern from tools/run_validation.py). Emits the numbers the
examiner-proofing iteration adds to the thesis:

  B1. spatial-block ROC-AUC for the cash crops (pooled vs block-mean; guards W4)
  B2. RF-vs-knowledge Cohen's kappa under spatial-block (grouped) CV — out-of-block
  B3. multi-year (2016-2024) within-crop season-GPP gradient (grows the small samples; W2)
  D1. per-segment factor-variance decomposition (which factors actually discriminate; W6)

(k-selection + stability curves are emitted by tools/run_conservation_recal.py ->
zoning_kselect.csv.) Run AFTER the re-export cascade.

Run:  EE_PROJECT=probformer ../.venv/bin/python tools/run_ws_analysis.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "src")

import ee  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import utils  # noqa: E402
import external  # noqa: E402
import membership  # noqa: E402
import metrics  # noqa: E402

P = utils.init()
AOI = utils.load_aoi(P)
SEG = utils.cfg("segments")
SEGS = list(SEG["segments"])
SCRATCH = os.environ.get("SCRATCHPAD", os.getcwd())
TS = 8
CAP = 4500


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def aid(n):
    return utils.asset_id(P, n)


suit = ee.Image(aid("suit_present"))
realized = ee.Image(aid("feat_realized"))
lc = ee.Image(aid("feat_landcover"))
stack = ee.Image(aid("feature_stack_250m"))
Z = ee.Image(aid("feature_stack_250m_z"))
LONLAT = ee.Image.pixelLonLat()
EXTRAS = {"sit_": ee.Image(aid("feat_siting")), "rl_": ee.Image(aid("feat_realized")),
          "cv_": ee.Image(aid("feat_conservation"))}


def sample_df(image, n=CAP, seed=11, scale=250):
    feats = (image.addBands(LONLAT)
             .sample(region=AOI, scale=scale, numPixels=n, seed=seed,
                     dropNulls=True, tileScale=TS)
             .getInfo()["features"])
    return pd.DataFrame([f["properties"] for f in feats])


def block(name, fn):
    log(f"--- {name} ---")
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        log(f"  !! {name} FAILED: {type(e).__name__}: {e}")


# B1. spatial-block AUC for the cash crops ---------------------------------------
def spatial_auc():
    img = suit.select(["suit_soybean", "suit_sugarcane"]).addBands(
        realized.select("rl_role"))
    df = sample_df(img, n=CAP, seed=1)
    bl = metrics.block_id(df["longitude"], df["latitude"], block_deg=0.5)
    for crop in ["soybean", "sugarcane"]:
        y = (df["rl_role"] == external.ROLE_CODES[crop]).astype(int).values
        r = metrics.spatial_block_auc(y, df[f"suit_{crop}"].values, bl, min_pos=5, min_neg=5)
        log(f"  {crop:10s} pooled AUC={r['pooled_auc']:.3f}  "
            f"block-mean={r['block_auc_mean']:.3f}±{r['block_auc_std']:.3f}  "
            f"n_blocks={r['n_blocks']}  n_pres={int(y.sum())}")


# B2. RF-vs-knowledge kappa under spatial (grouped) CV ---------------------------
def rf_spatial_kappa():
    from sklearn.ensemble import RandomForestClassifier
    bands = Z.bandNames().getInfo()
    img = (Z.addBands(realized.select("rl_role"))
           .addBands(suit.select("class_soybean")))
    df = sample_df(img, n=CAP, seed=3)
    df = df.dropna(subset=bands)
    X = df[bands].to_numpy()
    y = (df["rl_role"] == external.ROLE_CODES["soybean"]).astype(int).to_numpy()
    kb = (df["class_soybean"] >= 2).astype(int).to_numpy()  # knowledge S2+
    bl = metrics.block_id(df["longitude"], df["latitude"], block_deg=0.5)
    folds = metrics.spatial_block_folds(bl, k=5, seed=42)
    rf_oob = np.full(len(df), -1)
    for f in np.unique(folds):
        tr, te = folds != f, folds == f
        if y[tr].sum() < 5 or (y[tr] == 0).sum() < 5:
            continue
        rf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
        rf.fit(X[tr], y[tr])
        rf_oob[te] = (rf.predict_proba(X[te])[:, 1] >= 0.5).astype(int)
    ok = rf_oob >= 0
    k = metrics.cohen_kappa(rf_oob[ok], kb[ok])
    log(f"  soybean RF-vs-knowledge kappa (spatial 5-fold, out-of-block) = "
        f"{k['kappa']:+.3f}  n={k['n']}")
    log(f"  knowledge S2+ share={kb[ok].mean():.3f}  RF high-prob share={rf_oob[ok].mean():.3f}")


# B3. multi-year within-crop season-GPP gradient ---------------------------------
def multiyear_gpp():
    gpp = external.season_gpp(AOI, year_range=[2016, 2024])
    for crop in ["soybean", "sugarcane", "other_crops"]:
        m = realized.select("rl_role").eq(external.ROLE_CODES[crop])
        df = sample_df(suit.select(f"suit_{crop}").addBands(gpp).updateMask(m),
                       n=CAP, seed=7)
        r = metrics.within_crop_gradient(df[f"suit_{crop}"], df["season_gpp"])
        log(f"  {crop:12s} rho={r['rho']:+.3f} p={r['p']:.1e} n={r['n']} "
            f"monotonic={r['monotonic']}  (2016-2024 pooled GPP)")


# D1. per-segment factor-variance decomposition ----------------------------------
def variance_decomp():
    rows = []
    for name in SEGS:
        seg = SEG["segments"][name]
        mem = membership.segment_membership_image(stack, lc, seg, SEG, EXTRAS)
        # restrict to eligible land via updateMask (drop ineligible), NOT apply_mask —
        # multiplying ineligible pixels to 0 would inject mask-driven variance into every
        # factor equally and wrongly credit saturated factors.
        pol = seg["mask"]
        if pol == "available":
            mem = mem.updateMask(lc.select("mask_available"))
        elif pol == "exclude_only":
            mem = mem.updateMask(lc.select("mask_excluded").Not())
        df = sample_df(mem, n=CAP, seed=5)
        cols = [f"mem_{b}" for b in seg["factors"]]
        df = df.dropna(subset=cols)
        M = df[cols].to_numpy()
        w = [seg["factors"][b]["weight"] for b in seg["factors"]]
        arith = seg.get("aggregate", "geomean") == "arithmetic"
        shares = membership.variance_shares(M, w, arithmetic=arith)
        for b, wi, sh in zip(seg["factors"], w, shares):
            rows.append({"segment": name, "factor": b, "weight": round(wi, 3),
                         "variance_share": round(sh, 3)})
        top = sorted(zip(seg["factors"], shares), key=lambda t: -t[1])[:3]
        log(f"  {name:12s} top drivers: " +
            ", ".join(f"{b} {s:.2f}" for b, s in top))
    out = os.path.join(SCRATCH, "factor_variance.csv")
    pd.DataFrame(rows).to_csv(out, index=False)
    log(f"  wrote {out}")


def main():
    log(f"=== WS-B/WS-D analysis (project={P}) ===")
    block("B1. spatial-block AUC (soybean, sugarcane)", spatial_auc)
    block("B2. RF-vs-knowledge kappa (spatial CV)", rf_spatial_kappa)
    block("B3. multi-year within-crop GPP gradient", multiyear_gpp)
    block("D1. factor-variance decomposition", variance_decomp)
    log("=== WS analysis complete ===")


if __name__ == "__main__":
    main()
