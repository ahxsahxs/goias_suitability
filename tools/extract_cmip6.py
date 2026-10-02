"""CMIP6 table numbers for thesis §4.3 (recalibrated surfaces).

Tables 4.3 (ΔS territory means), 4.4 (S1+S2 shares present→future), 4.5 (per-zone
ΔS for crops), 4.6 (FAO-downgrade shares), 4.7 (other_crops transition matrix).

Baseline rule (CLAUDE.md §11): the present used for shares/transitions is the
**rederived** present = suit_future − delta (self-consistent per combo), NOT the
suit_present asset — so the export-reprojection offset cancels. ΔS means come
straight from the delta_* assets. Per-block try/except; tileScale; one reduceRegion
per combo where possible.

Run:  EE_PROJECT=probformer ../.venv/bin/python tools/extract_cmip6.py
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

P = utils.init()
AOI = utils.load_aoi(P)
SEGS = list(utils.cfg("segments")["segments"])
CROPS = ["soybean", "sugarcane", "other_crops"]
COMBOS = [("ssp245", "2031_2050"), ("ssp245", "2051_2070"),
          ("ssp585", "2031_2050"), ("ssp585", "2051_2070")]
TS = 8
RR = dict(geometry=AOI, scale=250, maxPixels=1e10, tileScale=TS)

# House pattern: CSVs land in thesis/Chapters/; $SCRATCHPAD overrides.
REPO = Path(__file__).resolve().parent.parent
CHAPTERS = REPO / "thesis" / "Chapters"
OUT = Path(os.environ.get("SCRATCHPAD", str(CHAPTERS)))
OUT.mkdir(parents=True, exist_ok=True)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def aid(n):
    return utils.asset_id(P, n)


def fut(ssp, win):
    return ee.Image(aid(f"suit_future_{ssp}_{win}"))


def dlt(ssp, win):
    return ee.Image(aid(f"delta_{ssp}_{win}"))


def fao(suit):  # continuous -> 0/1/2/3 (breaks 0.25/0.50/0.75)
    return suit.gte(0.25).add(suit.gte(0.50)).add(suit.gte(0.75))


zones = ee.Image(aid("zones_present")).rename("zone")


def block(name, fn):
    log(f"--- {name} ---")
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        log(f"  !! {name} FAILED: {type(e).__name__}: {e}")


# 4.3 — territory-mean ΔS per segment × combo ------------------------------------
def t43():
    rows = {s: {} for s in SEGS}
    for ssp, win in COMBOS:
        m = dlt(ssp, win).reduceRegion(ee.Reducer.mean(), **RR).getInfo()
        for s in SEGS:
            rows[s][f"{ssp}_{win}"] = m[f"delta_{s}"]
    print(f"  {'segment':14s} " + "  ".join(f"{ssp}_{win}" for ssp, win in COMBOS))
    for s in SEGS:
        print(f"  {s:14s} " + "  ".join(f"{rows[s][f'{ssp}_{win}']:+.4f}" for ssp, win in COMBOS))
    path = OUT / "cmip6_shift_mean.csv"
    pd.DataFrame([{"segment": s, "ssp": ssp, "window": win,
                   "delta_s": rows[s][f"{ssp}_{win}"]}
                  for s in SEGS for ssp, win in COMBOS]).to_csv(path, index=False)
    print(f"  wrote {path}")


# 4.4 — S1+S2 share present→future -----------------------------------------------
def t44():
    # present (rederived) is combo-independent; take it from the first combo
    ssp0, win0 = COMBOS[0]
    pres_img = ee.Image.cat([(fut(ssp0, win0).select(f"suit_{s}")
                              .subtract(dlt(ssp0, win0).select(f"delta_{s}"))
                              .gte(0.50).rename(s)) for s in SEGS])
    pres = pres_img.reduceRegion(ee.Reducer.mean(), **RR).getInfo()
    print(f"  {'segment':14s} present  " + "  ".join(f"{ssp}_{win}" for ssp, win in COMBOS))
    futdata = {}
    for ssp, win in COMBOS:
        fimg = ee.Image.cat([fut(ssp, win).select(f"suit_{s}").gte(0.50).rename(s) for s in SEGS])
        futdata[(ssp, win)] = fimg.reduceRegion(ee.Reducer.mean(), **RR).getInfo()
    for s in SEGS:
        cells = "  ".join(f"{100*futdata[c][s]:5.1f}%" for c in COMBOS)
        print(f"  {s:14s} {100*pres[s]:5.1f}%   {cells}")
    path = OUT / "cmip6_shift_share.csv"
    pd.DataFrame([{"segment": s, "ssp": ssp, "window": win,
                   "present_share": pres[s], "future_share": futdata[(ssp, win)][s]}
                  for s in SEGS for ssp, win in COMBOS]).to_csv(path, index=False)
    print(f"  wrote {path}")


# 4.6 — share downgraded ≥1 FAO class --------------------------------------------
def t46():
    print(f"  {'segment':14s} " + "  ".join(f"{ssp}_{win}" for ssp, win in COMBOS))
    data = {s: {} for s in SEGS}
    for ssp, win in COMBOS:
        f_img, d_img = fut(ssp, win), dlt(ssp, win)
        bands = []
        for s in SEGS:
            pres = f_img.select(f"suit_{s}").subtract(d_img.select(f"delta_{s}"))
            down = fao(f_img.select(f"suit_{s}")).lt(fao(pres)).rename(s)
            bands.append(down)
        m = ee.Image.cat(bands).reduceRegion(ee.Reducer.mean(), **RR).getInfo()
        for s in SEGS:
            data[s][(ssp, win)] = m[s]
    for s in SEGS:
        print(f"  {s:14s} " + "  ".join(f"{100*data[s][c]:5.1f}%" for c in COMBOS))
    path = OUT / "cmip6_downgrade.csv"
    pd.DataFrame([{"segment": s, "ssp": ssp, "window": win,
                   "downgrade_share": data[s][(ssp, win)]}
                  for s in SEGS for ssp, win in COMBOS]).to_csv(path, index=False)
    print(f"  wrote {path}")


# 4.5 — per-zone ΔS for crops (all four combos) ----------------------------------
def t45():
    """Per-zone mean ΔS per crop, written to cmip6_zone_shift.csv.

    All four SSP x window combos (it used to print only the mildest and the
    harshest); tab:zone-shift in the annex is generated from this CSV, so the
    full grid has to be on disk rather than only in stdout.
    """
    rows = []
    for ssp, win in COMBOS:
        d = dlt(ssp, win)
        print(f"  [{ssp} {win}]")
        for c in CROPS:
            fc = (d.select(f"delta_{c}").addBands(zones).reduceRegion(
                reducer=ee.Reducer.mean().group(groupField=1, groupName="zone"),
                **RR).get("groups").getInfo())
            # raster is 0-based, reporting is 1-based
            byz = {int(g["zone"]) + 1: g["mean"] for g in fc}
            cells = "  ".join(f"z{z}:{byz.get(z, float('nan')):+.4f}" for z in sorted(byz))
            print(f"    {c:12s} {cells}")
            for z, v in sorted(byz.items()):
                rows.append({"ssp": ssp, "window": win, "segment": c,
                             "zone": z, "delta_s": v})
    path = OUT / "cmip6_zone_shift.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  wrote {path}")


# 4.7 — other_crops present→future FAO transition matrix (harshest) --------------
def t47():
    ssp, win = "ssp585", "2051_2070"
    f_img, d_img = fut(ssp, win), dlt(ssp, win)
    pres = f_img.select("suit_other_crops").subtract(d_img.select("delta_other_crops"))
    pc, fc = fao(pres), fao(f_img.select("suit_other_crops"))
    key = pc.multiply(4).add(fc).rename("t")  # present*4 + future
    hist = key.reduceRegion(ee.Reducer.frequencyHistogram(), **RR).get("t").getInfo()
    tot = sum(hist.values())
    print(f"  other_crops transition ({ssp} {win}), % of evaluated land:")
    print("       fut:  N     S3    S2    S1   | present total")
    names = ["N", "S3", "S2", "S1"]
    rows = []
    for pi in range(4):
        cells, rowtot = [], 0.0
        for fi in range(4):
            v = 100 * hist.get(str(pi * 4 + fi), 0) / tot
            cells.append(f"{v:5.1f}")
            rowtot += v
            rows.append({"present": names[pi], "future": names[fi], "share_pct": v})
        print(f"  {names[pi]:>4s} {'  '.join(cells)} | {rowtot:5.1f}")
    path = OUT / "cmip6_transition_othercrops.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  wrote {path}")


def main():
    log(f"=== CMIP6 extraction (recalibrated, project={P}) ===")
    block("Table 4.3 — ΔS territory means", t43)
    block("Table 4.4 — S1+S2 shares present→future", t44)
    block("Table 4.6 — FAO downgrade shares", t46)
    block("Table 4.5 — per-zone ΔS for crops", t45)
    block("Table 4.7 — other_crops transition matrix", t47)
    log("=== CMIP6 extraction complete ===")


if __name__ == "__main__":
    main()
