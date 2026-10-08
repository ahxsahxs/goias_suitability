"""Present-side + realized-use table numbers for thesis Ch.4 (recalibrated surfaces).

Computes, on the recalibrated assets, the numbers behind Tables 4.1/4.2 (via
zone_profiles.csv, already written), zone area shares, present S1+S2 shares (4.4
present col), realized-crop mean suitability, under-utilization gaps (4.10), the
sugarcane/other_crops presence metrics that complete Table 4.11, and the municipal
summary + rankings (4.13). Per-block try/except; cached assets; tileScale.

Run:  EE_PROJECT=probformer ../.venv/bin/python tools/extract_present.py
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

P = utils.init()
AOI = utils.load_aoi(P)
SEG = utils.cfg("segments")
SEGS = list(SEG["segments"])
TS, CAP = 8, 4500

# House pattern (see tools/anchor_breakpoints.py): CSVs land in thesis/Chapters/
# so make_figures._read_diag finds them; $SCRATCHPAD overrides for scratch runs.
REPO = Path(__file__).resolve().parent.parent
CHAPTERS = REPO / "thesis" / "Chapters"
OUT = Path(os.environ.get("SCRATCHPAD", str(CHAPTERS)))
OUT.mkdir(parents=True, exist_ok=True)


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
    """Zone area shares via pixelArea(), written to zone_area.csv.

    CLAUDE.md §7: areas come from ee.Image.pixelArea(), never from a pixel count.
    A frequencyHistogram counts pixels, which is neither equal-area under
    EPSG:4326 nor stable across reduction scales. zone_profiles.csv's `n` is a
    *sample* count and is not an area share either (it differs by ~6 points on
    the largest zone) -- this CSV is the only correct source for the area row of
    the four zone-indexed thesis tables.
    """
    grouped = (ee.Image.pixelArea().divide(1e6).addBands(zones.toInt())
               .reduceRegion(
                   reducer=ee.Reducer.sum().group(groupField=1, groupName="zone"),
                   geometry=AOI, scale=250, maxPixels=1e10, tileScale=TS)
               .get("groups").getInfo())
    tot = sum(g["sum"] for g in grouped)
    rows = []
    for g in sorted(grouped, key=lambda x: int(x["zone"])):
        z = int(g["zone"]) + 1               # raster is 0-based, reporting is 1-based
        rows.append({"zone": z, "area_km2": g["sum"], "share_pct": 100 * g["sum"] / tot})
        print(f"  zone {z}: {100*g['sum']/tot:5.1f}%  ({g['sum']:,.0f} km2)")
    print(f"  total classified: {tot:,.1f} km2")
    path = OUT / "zone_area.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  wrote {path}")


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


# E. REMOVED 2026-10-03 — presence metrics moved to tools/run_validation.py.
# This block computed sugarcane + other_crops AUC/Boyce from a UNIFORM
# .sample(numPixels=4500, seed=11), while soybean's row of the same thesis table
# came from run_validation.py's GRID-stratified n~16k draw. Three rows of one
# table, three different estimators -- which is how the thesis came to print
# AUC 0.871 for soybean against a validation_metrics.csv that said 0.846.
# run_validation.presence_metrics() now draws all three crops once, stratified,
# at CAP_PRESENCE=60000, and reports each on both halves of the spatial holdout.
# Do not reintroduce a second presence-metric path here.


# F. municipal summary + rankings (Table 4.13) -----------------------------------
def municipal():
    # IBGE malha municipal, built client-side (src/ibge_mesh.py) on every run —
    # NOT the stale `municipal_godf` export, which still reflects GAUL until an
    # explicitly-approved Part 12 asset rebuild (CLAUDE.md §4/§10).
    muni = external.municipal_fc()
    # add per-municipality underused shares for the opportunity score
    uu = ee.Image(aid("realized_vs_potential")).select(
        ["underused_soybean", "underused_sugarcane"]).unmask(0)
    delta = ee.Image(aid("delta_ssp585_2051_2070"))
    agg = (suit.select(["suit_soybean", "suit_sugarcane"])
           .addBands(zones)
           .addBands(delta.select("delta_other_crops"))
           .addBands(uu))
    uu_m = external.municipal_means(muni, agg, scale=250)
    props = ["NM_MUN", "zone", "suit_soybean", "suit_sugarcane",
             "delta_other_crops", "underused_soybean", "underused_sugarcane"]
    feats = uu_m.select(props, None, False).getInfo()["features"]
    df = pd.DataFrame([f["properties"] for f in feats]).dropna(subset=["suit_soybean"])
    df["opportunity"] = df["suit_soybean"] * df["underused_soybean"]
    print(f"  municipalities n={len(df)}")
    print(f"  soybean suit: median={df.suit_soybean.median():.3f} "
          f"min={df.suit_soybean.min():.3f} max={df.suit_soybean.max():.3f}")
    print(f"  S1-level (>=0.75): {(df.suit_soybean >= 0.75).sum()}   "
          f"S2+ (>=0.50): {(df.suit_soybean >= 0.50).sum()}")
    # municipal_godf aggregates the 0-based raster, so shift to 1-based reporting
    df["zone"] = df.zone.round().astype(int) + 1
    zc = df.zone.value_counts().sort_index()
    print(f"  municipalities by majority zone: {zc.to_dict()}")
    vuln = df[df.delta_other_crops < -0.05]
    print(f"  vulnerable (delta_other_crops < -0.05): {len(vuln)}  "
          f"mean={vuln.delta_other_crops.mean():.3f} worst={df.delta_other_crops.min():.3f}")
    print(f"  opportunity > 0.4: {(df.opportunity > 0.4).sum()}")
    print("  TOP-5 OPPORTUNITY (suit_soybean x underused_soybean):")
    for _, r in df.nlargest(5, "opportunity").iterrows():
        print(f"    {r.NM_MUN:28s} opp={r.opportunity:.3f} "
              f"suit={r.suit_soybean:.3f} unused={r.underused_soybean:.3f}")
    print("  TOP-5 VULNERABILITY (most negative delta_other_crops):")
    for _, r in df.nsmallest(5, "delta_other_crops").iterrows():
        print(f"    {r.NM_MUN:28s} dS={r.delta_other_crops:.3f} zone={int(r.zone)}")
    out_path = CHAPTERS / "Figures" / "municipal_ranking.csv"   # not CWD-relative
    df.to_csv(out_path, index=False,
              columns=["NM_MUN", "delta_other_crops", "suit_soybean", "suit_sugarcane",
                       "underused_soybean", "underused_sugarcane", "zone", "opportunity"])
    print(f"  wrote {out_path}")


def main():
    log(f"=== present-side extraction (recalibrated, project={P}) ===")
    block("A. zone area shares", zone_shares)
    block("B. present S1+S2 shares", present_s2)
    block("C. realized-crop mean suitability", realized_crop_suit)
    block("D. under-utilization gaps (Table 4.10)", under_util)
    block("F. municipal summary + rankings (Table 4.13)", municipal)
    log("=== extraction complete ===")


if __name__ == "__main__":
    main()
