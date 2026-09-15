"""Present-side + realized-use table numbers for thesis Ch.4 (recalibrated surfaces).

Computes, on the recalibrated assets, the numbers behind Tables 4.1/4.2 (via
zone_profiles.csv, already written), zone area shares, present S1+S2 shares (4.4
present col), realized-crop mean suitability, under-utilization gaps (4.10), the
sugarcane/other_crops presence metrics that complete Table 4.11, and the municipal
summary + rankings (4.13). Per-block try/except; cached assets; tileScale.

Run:  EE_PROJECT=probformer ../.venv/bin/python tools/extract_present.py
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

P = utils.init()
AOI = utils.load_aoi(P)
SEG = utils.cfg("segments")
SEGS = list(SEG["segments"])
TS, CAP = 8, 4500


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def aid(n):
    return utils.asset_id(P, n)


suit = ee.Image(aid("suit_present"))
realized = ee.Image(aid("feat_realized"))
zones = ee.Image(aid("zones_present")).rename("zone")


def block(name, fn):
    log(f"--- {name} ---")
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        log(f"  !! {name} FAILED: {type(e).__name__}: {e}")


# A. zone area shares (% of AOI) --------------------------------------------------
def zone_shares():
    hist = zones.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(), geometry=AOI, scale=250,
        maxPixels=1e10, tileScale=TS).get("zone").getInfo()
    tot = sum(hist.values())
    for k in sorted(hist, key=lambda x: int(x)):
        print(f"  zone {k}: {100*hist[k]/tot:5.1f}%  ({int(hist[k])} px)")


# B. present S1+S2 share per segment (mean of class>=2 over evaluated land) --------
def present_s2():
    exprs = [suit.select(f"class_{s}").gte(2).rename(s) for s in SEGS]
    stats = ee.Image.cat(exprs).reduceRegion(
        reducer=ee.Reducer.mean(), geometry=AOI, scale=250,
        maxPixels=1e10, tileScale=TS).getInfo()
    for s in SEGS:
        print(f"  {s:14s} S2+ = {100*stats[s]:5.1f}%")


# C. realized-crop mean suitability vs available-land mean ------------------------
def realized_crop_suit():
    avail = realized.select("mask_available")
    for crop in ["soybean", "sugarcane", "other_crops"]:
        m = realized.select("rl_role").eq(external.ROLE_CODES[crop])
        s = suit.select(f"suit_{crop}")
        at_crop = s.updateMask(m).reduceRegion(
            ee.Reducer.mean(), AOI, 250, maxPixels=1e10, tileScale=TS).getInfo()
        at_avail = s.updateMask(avail).reduceRegion(
            ee.Reducer.mean(), AOI, 250, maxPixels=1e10, tileScale=TS).getInfo()
        print(f"  {crop:12s} at realized={list(at_crop.values())[0]:.3f}  "
              f"over available={list(at_avail.values())[0]:.3f}")


# D. under-utilization gaps (Table 4.10) -----------------------------------------
def under_util():
    uu = ee.Image(aid("realized_vs_potential"))
    aoi_area = ee.Image.pixelArea().clip(AOI).reduceRegion(
        ee.Reducer.sum(), AOI, 250, maxPixels=1e10, tileScale=TS).getInfo()["area"]
    for b in uu.bandNames().getInfo():
        a = uu.select(b).unmask(0).multiply(ee.Image.pixelArea()).reduceRegion(
            ee.Reducer.sum(), AOI, 250, maxPixels=1e10, tileScale=TS).getInfo()[b]
        print(f"  {b:22s} = {100*a/aoi_area:5.1f}% of territory")


# E. complete Table 4.11 — sugarcane + other_crops AUC / Boyce -------------------
def presence_metrics():
    for crop in ["sugarcane", "other_crops"]:
        smp = (suit.select(f"suit_{crop}").addBands(realized.select("rl_role"))
               .sample(region=AOI, scale=250, numPixels=CAP, seed=11,
                       dropNulls=True, tileScale=TS).getInfo()["features"])
        sdf = pd.DataFrame([f["properties"] for f in smp])
        pres = sdf[sdf.rl_role == external.ROLE_CODES[crop]][f"suit_{crop}"]
        sdf["is_c"] = (sdf.rl_role == external.ROLE_CODES[crop]).astype(int)
        b = metrics.continuous_boyce(pres, sdf[f"suit_{crop}"])["boyce"]
        a = metrics.auc(sdf["is_c"], sdf[f"suit_{crop}"])["auc"]
        print(f"  {crop:12s} presence={len(pres)}/{len(sdf)}  AUC={a:.3f}  Boyce={b:.3f}")


# F. municipal summary + rankings (Table 4.13) -----------------------------------
def municipal():
    muni = ee.FeatureCollection(aid("municipal_godf"))
    # add per-municipality underused shares for the opportunity score
    uu = ee.Image(aid("realized_vs_potential")).select(
        ["underused_soybean", "underused_sugarcane"]).unmask(0)
    uu_m = external.municipal_means(muni, uu, scale=250)
    props = ["ADM2_NAME", "zone", "suit_soybean", "suit_sugarcane",
             "delta_other_crops", "underused_soybean", "underused_sugarcane"]
    feats = uu_m.select(props, None, False).getInfo()["features"]
    df = pd.DataFrame([f["properties"] for f in feats]).dropna(subset=["suit_soybean"])
    df["opportunity"] = df["suit_soybean"] * df["underused_soybean"]
    print(f"  municipalities n={len(df)}")
    print(f"  soybean suit: median={df.suit_soybean.median():.3f} "
          f"min={df.suit_soybean.min():.3f} max={df.suit_soybean.max():.3f}")
    print(f"  S1-level (>=0.75): {(df.suit_soybean >= 0.75).sum()}   "
          f"S2+ (>=0.50): {(df.suit_soybean >= 0.50).sum()}")
    zc = df.zone.round().astype(int).value_counts().sort_index()
    print(f"  municipalities by majority zone: {zc.to_dict()}")
    vuln = df[df.delta_other_crops < -0.05]
    print(f"  vulnerable (delta_other_crops < -0.05): {len(vuln)}  "
          f"mean={vuln.delta_other_crops.mean():.3f} worst={df.delta_other_crops.min():.3f}")
    print(f"  opportunity > 0.4: {(df.opportunity > 0.4).sum()}")
    print("  TOP-5 OPPORTUNITY (suit_soybean x underused_soybean):")
    for _, r in df.nlargest(5, "opportunity").iterrows():
        print(f"    {r.ADM2_NAME:28s} opp={r.opportunity:.3f} "
              f"suit={r.suit_soybean:.3f} unused={r.underused_soybean:.3f}")
    print("  TOP-5 VULNERABILITY (most negative delta_other_crops):")
    for _, r in df.nsmallest(5, "delta_other_crops").iterrows():
        print(f"    {r.ADM2_NAME:28s} dS={r.delta_other_crops:.3f} zone={int(round(r.zone))}")
    df.to_csv("docs/thesis/figures/municipal_ranking.csv", index=False,
              columns=["ADM2_NAME", "delta_other_crops", "suit_soybean", "suit_sugarcane",
                       "underused_soybean", "underused_sugarcane", "zone", "opportunity"])
    print("  wrote docs/thesis/figures/municipal_ranking.csv")


def main():
    log(f"=== present-side extraction (recalibrated, project={P}) ===")
    block("A. zone area shares", zone_shares)
    block("B. present S1+S2 shares", present_s2)
    block("C. realized-crop mean suitability", realized_crop_suit)
    block("D. under-utilization gaps (Table 4.10)", under_util)
    block("E. sugarcane/other_crops AUC/Boyce (Table 4.11)", presence_metrics)
    block("F. municipal summary + rankings (Table 4.13)", municipal)
    log("=== extraction complete ===")


if __name__ == "__main__":
    main()
