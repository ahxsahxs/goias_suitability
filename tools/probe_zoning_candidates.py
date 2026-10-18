"""Probe: should any `feat_siting` / `feat_conservation` band be a ZONING axis?

Read-only. Submits no export, writes nothing to config/, touches no asset.

WHY THIS EXISTS
---------------
`feat_siting` (`sit_`) and `feat_conservation` (`cv_`) feed the suitability arm
only (Part 9, via membership's prefix routing) and never the zoning arm
(Part 10). The thesis justified that structurally rather than methodologically
("ficam fora do conjunto de 29 bandas utilizadas para agrupamento"), which is
both a non-argument and imprecise: only 13 of the 29 stacked bands are
clustered, so 16 stacked bands are *also* absent from zoning. "In the stack"
was never the same thing as "in the zoning arm".

This tool replaces that non-argument with evidence, by asking the only question
that matters -- is each of the five side bands a legitimate zoning axis? -- under
four gates, pre-committed in this order:

  G-a  admissibility (QUALITATIVE, decided before any number is seen): does the
       band encode land-surface biophysics, or realized state / governance?
       Runs first BY DESIGN so no statistic can overturn a published guardrail.
  G-b  redundancy, with the threshold CALIBRATED ON THE PROJECT'S OWN DISCARDS
       (the pairs 04_methodology.tex:324-326 says were dropped as "quase
       duplicadas"), never on an invented 0.8 cutoff.
  G-c  new information: does PCA(var_keep=0.90) retain another component?
  G-d  partition impact: the full k=2..20 panel in both spaces, on the SAME ROWS.

WHY THE IN-MEMORY Z-SCORES ARE EXACT, NOT APPROXIMATE
-----------------------------------------------------
`features.assemble_stack` reduces mean/stdDev per band (a single-input reducer
over a multi-band image repeats per band, each band over its own pixels), so
computing those same statistics on the 5-band side image ALONE yields
bit-identical mu/sigma. The z-stack built here therefore IS what a merged export
would produce -- this is not a proxy for the merge, it is the merge's clustering
input. `Z_STAT_SCALE` / `Z_STAT_KW` below must stay in step with
`features.assemble_stack`.

ONE SAMPLE, SHARED BY BOTH ARMS
-------------------------------
Every column is drawn in a SINGLE `build_sample` call and subset afterwards.
`build_sample` passes `dropNulls=True`, so a larger band set can drop rows:
comparing an augmented sweep against the production 13-band panel sampled
separately would confound an admission effect with a sample-composition effect.

Run:
    EE_PROJECT=probformer uv run python tools/probe_zoning_candidates.py
    EE_PROJECT=probformer uv run python tools/probe_zoning_candidates.py --no-gd
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ee  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import utils  # noqa: E402
import zoning  # noqa: E402

P = utils.init()
AOI = utils.load_aoi(P)
SEG = utils.cfg("segments")
SEGS = list(SEG["segments"])
OUT = utils.out_dir()

# Kept in step with features.assemble_stack (src/features.py:565-574). If those
# reducer parameters ever change, the claim that this probe's z-scores equal a
# merged export's z-scores stops holding.
Z_STAT_SCALE = utils.scale_m() * 4
Z_STAT_KW = dict(geometry=AOI, scale=Z_STAT_SCALE, maxPixels=int(1e13),
                 bestEffort=True, tileScale=16)

SIDE_ASSETS = {
    "feat_siting": ["sit_clearness", "sit_water_dist_seas"],
    "feat_conservation": ["cv_pa_dist", "cv_ruggedness", "cv_carbon"],
}
CANDIDATES = [b for bands in SIDE_ASSETS.values() for b in bands]

# G-a. Pre-committed, qualitative, and NOT derived from any statistic below.
# `theme` is the block a band would join if admitted -- needed because
# zoning._theme_of splits the band name on the first "_", which would give
# `sit_clearness` a 1-band block at weight 1/sqrt(1)=1.0 against terrain's
# 1/sqrt(3)=0.577. There is no additive way to add a zoning band: mapping one
# into `climate` moves EVERY climate band from 1/sqrt(4) to 1/sqrt(5).
GATE_A = {
    "sit_clearness": (
        "pass", "climate",
        "Kt = Rs/Ra: atmospheric transmissivity, a land-surface/climate "
        "variable; clim_srad is absent from the curated 13, so the radiation "
        "axis is currently unrepresented in the zoning space."),
    "sit_water_dist_seas": (
        "pass", "water",
        "Euclidean distance to seasonal surface water: biophysical, same kind "
        "of band as the incumbent water_dist."),
    "cv_ruggedness": (
        "pass", "terrain",
        "Local stdDev of SRTM elevation: biophysical terrain texture, same "
        "kind of band as the incumbent terr_slope."),
    "cv_carbon": (
        "reject", None,
        "Vegetation STATE (aboveground biomass is high exactly where native "
        "cover survives) -- the argument that removed NDVI phenology. The mild "
        "circularity segments.yaml concedes is tolerable at weight 0.1706 "
        "inside a compensatory arithmetic mean; it is not tolerable at weight "
        "1/sqrt(n) inside a Euclidean distance, where zoning has no sigma(mu) "
        "demotion mechanism."),
    "cv_pa_dist": (
        "reject", None,
        "Governance layer, not land surface (07_annex.tex:171-175 already "
        "argues this). Zones are agro-ENVIRONMENTAL: a zone boundary following "
        "a decree boundary is not biophysical. Also circular within the "
        "conservation arm -- zone defined by PA proximity, then scored for "
        "conservation value."),
}

# G-b. The pairs 04_methodology.tex:324-326 names as near-duplicates ("mantendo
# a aridez em vez do par precipitacao/evapotranspiracao, um indice termico, e a
# argila em vez do par areia/densidade aparente"). Their |r| on THIS sample
# calibrates the rejection threshold, so the criterion is the project's own and
# is citable to that passage.
#
# THE THRESHOLD IS THE MINIMUM, NOT THE MAXIMUM, and this is load-bearing. These
# six discards span |r| = 0.679..0.997, so there is no single cutoff the project
# "used"; what the set reveals is the weakest redundancy at which it demonstrably
# dropped a band (soil_bdod vs soil_clay, 0.679). Any candidate at or above that
# would have been dropped by the same hand. Taking the max instead (0.997, gdd vs
# twarm_q) makes the gate vacuous -- nothing in this territory clears it.
#
# `water_seasonality` is deliberately NOT in this list. It was dropped from the
# curated subset too, but it sits at |r| = 0.14 against water_dist, so it was not
# dropped for redundancy with it: it falls under the SEPARATE "alem das bandas
# quase constantes" clause of the same sentence. Including it would calibrate a
# redundancy threshold on a discard that was not about redundancy.
REFERENCE_PAIRS = [
    ("clim_pr_annual", "clim_aridity"),
    ("clim_pet_annual", "clim_aridity"),
    ("clim_tcold_q", "clim_twarm_q"),
    ("clim_gdd", "clim_twarm_q"),
    ("soil_sand", "soil_clay"),
    ("soil_bdod", "soil_clay"),
]
REFERENCE_BANDS = sorted({a for a, _ in REFERENCE_PAIRS})

KS = range(2, 21)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def aid(n):
    return utils.asset_id(P, n)


def theme_weights(band_names, override=None):
    """zoning.theme_weight_vector with an explicit band->theme override.

    Mirrors zoning.theme_weight_vector (1/sqrt(bands-in-theme)) but lets a
    candidate join an existing block instead of forming its own. Local to this
    probe: production code is not touched until an admission is decided.
    """
    override = override or {}

    def theme_of(b):
        return override.get(b) or b.split("_", 1)[0]

    counts = Counter(theme_of(b) for b in band_names)
    return np.asarray([1.0 / math.sqrt(counts[theme_of(b)]) for b in band_names])


def design(df, band_names, override=None):
    """Theme-weighted z design matrix, columns in `band_names` order."""
    X = df[zoning.zbands(band_names)].to_numpy()
    return X * theme_weights(band_names, override)


def side_z_image():
    """The 5 side bands, z-scored exactly as assemble_stack would z-score them."""
    imgs = [ee.Image(aid(a)).select(b) for a, b in SIDE_ASSETS.items()]
    raw = ee.Image.cat(imgs).clip(AOI)
    bn = raw.bandNames()
    means = raw.reduceRegion(reducer=ee.Reducer.mean(), **Z_STAT_KW)
    stds = raw.reduceRegion(reducer=ee.Reducer.stdDev(), **Z_STAT_KW)
    mean_img = ee.Image.constant(means.values(bn)).rename(bn)
    std_img = ee.Image.constant(stds.values(bn)).rename(bn)
    return raw, raw.subtract(mean_img).divide(std_img).clip(AOI)


def vif(df, target, predictors):
    """Variance inflation factor of `target` regressed on `predictors` (z cols)."""
    y = df[zoning.Z_PREFIX + target].to_numpy()
    A = df[zoning.zbands(predictors)].to_numpy()
    A = np.column_stack([np.ones(len(A)), A])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ coef
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float((resid ** 2).sum()) / ss_tot if ss_tot > 0 else float("nan")
    return (float("inf") if r2 >= 1.0 else 1.0 / (1.0 - r2)), r2


def panel(S, split, label):
    """The production k-selection panel (zoning.kselect_panel)."""
    out = zoning.kselect_panel(S, split, ks=KS)
    out.insert(0, "space", label)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-gd", action="store_true",
                    help="skip G-d (the two k=2..20 panels), the only slow gate")
    ap.add_argument("-n", type=int, default=40000, help="target sample size")
    ap.add_argument("--cache", default=str(Path(os.environ.get("SCRATCHPAD") or "/tmp")
                                          / "probe_zoning_sample.csv"),
                    help="reuse/store the drawn sample here (the only EE-quota cost)")
    ap.add_argument("--resample", action="store_true",
                    help="ignore an existing cache and draw from EE again")
    args = ap.parse_args()

    incumbents = list(zoning.ZONING_BANDS)
    bands = incumbents + CANDIDATES + REFERENCE_BANDS

    # The sample is the ONLY part of this probe that spends EE compute; the gates
    # are offline. Cache it so a re-run (a changed threshold rule, another gate)
    # costs nothing -- which matters while the project sits in restricted mode.
    cache = Path(args.cache)
    if cache.exists() and not args.resample:
        df = pd.read_csv(cache)
        log(f"reusing cached sample {cache} (n={len(df)}) -- no EE compute")
    else:
        z = ee.Image(aid("feature_stack_250m_z"))
        raw = ee.Image(aid("feature_stack_250m"))
        suit = ee.Image(aid("suit_present"))
        side_raw, side_z = side_z_image()
        log(f"sampling {len(bands)} bands = {len(incumbents)} incumbent + "
            f"{len(CANDIDATES)} candidate + {len(REFERENCE_BANDS)} threshold-reference")
        split_img = utils.split_image(P).rename("split")
        sample = zoning.build_sample(
            z.addBands(side_z), raw.addBands(side_raw), suit, AOI, bands,
            segments=SEGS, seed=42, n=args.n, extra=split_img)
        df = zoning.fc_to_df(sample)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache, index=False)
        log(f"cached sample -> {cache}")
    split = (df["split"].to_numpy() == 1).astype(int)   # 0 = calib, 1 = val
    log(f"  n={len(df)}  calib={int((split == 0).sum())}  val={int(split.sum())}")

    # --- G-b: threshold calibrated on the project's own discards -------------
    zc = df[zoning.zbands(bands)].corr()
    ref_rows = [{"discarded": a, "retained": b,
                 "abs_r": abs(float(zc.loc[zoning.Z_PREFIX + a,
                                           zoning.Z_PREFIX + b]))}
                for a, b in REFERENCE_PAIRS]
    ref = pd.DataFrame(ref_rows).sort_values("abs_r", ascending=False)
    thresh = float(ref["abs_r"].min())          # the MINIMUM -- see REFERENCE_PAIRS
    weakest = ref.iloc[-1]
    log("G-b threshold calibrated on the thesis's own discarded near-duplicates:\n"
        + ref.round(4).to_string(index=False))
    log(f"  => rejection threshold |r| >= {thresh:.4f} = the weakest redundancy at "
        f"which the project itself dropped a band ({weakest['discarded']} vs "
        f"{weakest['retained']})")

    # --- G-c baseline --------------------------------------------------------
    calib = split == 0
    X13 = design(df, incumbents)
    pca13 = zoning.fit_pca(X13[calib], var_keep=0.90)
    n_pc13 = int(pca13.n_components_)
    log(f"G-c baseline: PCA(0.90) on {len(incumbents)} incumbents -> {n_pc13} PCs")

    rows, survivors = [], []
    for band in CANDIDATES:
        verdict_a, theme, reason_a = GATE_A[band]
        r_vs = {inc: abs(float(zc.loc[zoning.Z_PREFIX + band,
                                      zoning.Z_PREFIX + inc]))
                for inc in incumbents}
        nearest = max(r_vs, key=r_vs.get)
        max_r = r_vs[nearest]
        v, r2 = vif(df, band, incumbents)
        gate_b = "pass" if max_r < thresh else "reject"

        aug = incumbents + [band]
        override = {band: theme} if theme else None
        n_pc = int(zoning.fit_pca(design(df, aug, override)[calib],
                                  var_keep=0.90).n_components_)
        gate_c = "pass" if n_pc > n_pc13 else "reject"

        if verdict_a == "reject":
            decision, by = "reject", "G-a (admissibility)"
        elif gate_b == "reject":
            decision, by = "reject", "G-b (redundancy)"
        elif gate_c == "reject":
            decision, by = "reject", "G-c (no new dimension)"
        else:
            decision, by = "candidate", "G-d (partition impact) pending"
            survivors.append((band, theme))

        rows.append({
            "band": band, "theme_if_admitted": theme or "", "gate_a": verdict_a,
            "max_abs_r": round(max_r, 4), "nearest_incumbent": nearest,
            "threshold_abs_r": round(thresh, 4), "gate_b": gate_b,
            "vif_vs_incumbents": (round(v, 2) if math.isfinite(v) else ""),
            "r2_vs_incumbents": round(r2, 4),
            "n_pc_90_baseline": n_pc13, "n_pc_90_augmented": n_pc,
            "gate_c": gate_c, "decision": decision, "decided_by": by,
            "reason_a": reason_a,
        })
        log(f"  {band:22s} A={verdict_a:6s} |r|max={max_r:.3f} vs {nearest:20s} "
            f"VIF={v:8.2f} n_pc={n_pc} -> {decision} [{by}]")

    res = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    ref.round(6).to_csv(OUT / "zoning_candidates_threshold.csv", index=False)
    res.to_csv(OUT / "zoning_candidates.csv", index=False)
    log(f"wrote {OUT / 'zoning_candidates_threshold.csv'}")
    log(f"wrote {OUT / 'zoning_candidates.csv'}")

    # --- G-d: only if something cleared G-a..G-c -----------------------------
    if not survivors:
        log("G-d skipped: no candidate cleared G-a..G-c. "
            "ZONING_BANDS stands at 13 by measurement, not by taste.")
        return
    if args.no_gd:
        log(f"G-d suppressed (--no-gd); survivors = {[b for b, _ in survivors]}")
        return

    aug = incumbents + [b for b, _ in survivors]
    override = {b: t for b, t in survivors if t}
    log(f"G-d: two k=2..20 panels (13 vs {len(aug)} bands), same rows ...")
    S13 = pca13.transform(X13)
    Xa = design(df, aug, override)
    pca_a = zoning.fit_pca(Xa[calib], var_keep=0.90)
    Sa = pca_a.transform(Xa)
    panels = pd.concat([panel(S13, split, "incumbent_13"),
                        panel(Sa, split, f"augmented_{len(aug)}")],
                       ignore_index=True)
    panels.to_csv(OUT / "zoning_candidates_kselect.csv", index=False)
    log(f"wrote {OUT / 'zoning_candidates_kselect.csv'}\n"
        + panels.round(3).to_string(index=False))

    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score
    for k in (4, int(panels[panels.space == f"augmented_{len(aug)}"]
                     .set_index("k")["ari_holdout"].idxmax())):
        l13 = KMeans(n_clusters=k, random_state=42, n_init=10).fit(S13[calib]).predict(S13)
        la = KMeans(n_clusters=k, random_state=42, n_init=10).fit(Sa[calib]).predict(Sa)
        log(f"  k={k}: ARI(incumbent vs augmented partition, same rows) = "
            f"{adjusted_rand_score(l13, la):.4f}")


if __name__ == "__main__":
    main()
