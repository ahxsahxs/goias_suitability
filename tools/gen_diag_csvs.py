"""Regenerate the two diagnostic CSVs that feed fig_4_10 / fig_4_11.

  zoning_kselect.csv  — cluster-validity + stability sweep over k (fig_4_10)
  factor_variance.csv — per-segment factor share of suitability variance (fig_4_11)

Both are normally emitted as a side effect of the heavy re-export cascades
(``tools/run_conservation_recal.py`` Stage 4 and ``tools/run_ws_analysis.py`` D1).
This tool reproduces *only* those two computations from the already-built assets —
no asset is written, no export is submitted. The zoning sweep is deterministic
(seed=42) and label-identical to the cascade; the variance decomposition uses the
same capped-sample pattern.

Output goes where ``tools/make_figures.py`` looks for it: ``$SCRATCHPAD`` if set,
otherwise ``docs/thesis/``.

Run:
    EE_PROJECT=probformer uv run python tools/gen_diag_csvs.py [zoning|variance|all]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ee  # noqa: E402
import pandas as pd  # noqa: E402

import utils  # noqa: E402
import external  # noqa: E402
import membership  # noqa: E402
import zoning  # noqa: E402

P = utils.init()
AOI = utils.load_aoi(P)
SEG = utils.cfg("segments")
SEGS = list(SEG["segments"])
THESIS_DIR = Path(__file__).resolve().parent.parent / "docs" / "thesis"
OUT = Path(os.environ.get("SCRATCHPAD", str(THESIS_DIR)))
TS = 8
CAP = 4500


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def aid(n):
    return utils.asset_id(P, n)


# --- zoning_kselect.csv (mirrors run_conservation_recal.py Stage 4) ------------
def gen_zoning_kselect():
    z = ee.Image(aid("feature_stack_250m_z"))
    raw = ee.Image(aid("feature_stack_250m"))
    suit_a = ee.Image(aid("suit_present"))
    realized = ee.Image(aid("feat_realized"))
    frac_bands = [f"rl_{r}_frac" for r in
                  ("soybean", "sugarcane", "other_crops", "pasture", "native")]
    bands = zoning.ZONING_BANDS
    log("zoning: sample + PCA + k-sweep + gap + stability (seed=42) ...")
    sample = zoning.build_sample(z, raw, suit_a, AOI, bands, n=15000, seed=42,
                                 extra=realized.select(frac_bands))
    df = zoning.fc_to_df(sample)
    X = zoning.cluster_matrix(df, bands)
    pca = zoning.fit_pca(X, var_keep=0.90)
    S = pca.transform(X)
    sweep = zoning.kmeans_sweep(S, ks=range(2, 11), seed=42)
    gap = zoning.gap_statistic(S, ks=range(2, 11), B=10, seed=42)
    stab = zoning.stability_sweep(S, ks=range(2, 11), B=20, seed=42)
    swp = sweep.merge(gap, on="k").merge(stab, on="k")
    out = OUT / "zoning_kselect.csv"
    swp.to_csv(out, index=False)
    log(f"  wrote {out}\n" + swp.round(3).to_string(index=False))


# --- factor_variance.csv (mirrors run_ws_analysis.py D1) ----------------------
def gen_factor_variance():
    stack = ee.Image(aid("feature_stack_250m"))
    lc = ee.Image(aid("feat_landcover"))
    lonlat = ee.Image.pixelLonLat()
    extras = {"sit_": ee.Image(aid("feat_siting")),
              "rl_": ee.Image(aid("feat_realized")),
              "cv_": ee.Image(aid("feat_conservation"))}

    def sample_df(image, n=CAP, seed=5, scale=250):
        feats = (image.addBands(lonlat)
                 .sample(region=AOI, scale=scale, numPixels=n, seed=seed,
                         dropNulls=True, tileScale=TS)
                 .getInfo()["features"])
        return pd.DataFrame([f["properties"] for f in feats])

    log("variance: per-segment factor-variance decomposition ...")
    rows = []
    for name in SEGS:
        seg = SEG["segments"][name]
        mem = membership.segment_membership_image(stack, lc, seg, SEG, extras)
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
        log(f"  {name:12s} top drivers: " + ", ".join(f"{b} {s:.2f}" for b, s in top))
    out = OUT / "factor_variance.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    log(f"  wrote {out}")


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    OUT.mkdir(parents=True, exist_ok=True)
    log(f"=== diagnostic CSVs (project={P}) -> {OUT} ===")
    if what in ("zoning", "all"):
        gen_zoning_kselect()
    if what in ("variance", "all"):
        gen_factor_variance()
    log("=== done ===")


if __name__ == "__main__":
    main()
