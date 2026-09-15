"""Quick correctness/meaningfulness check for the `zones_present` asset.

Two parts:
  1. METADATA (always works, even under restricted compute quota): asset type,
     band(s), CRS, 250 m scale, and GO+DF footprint — same checks as
     tools/verify_assets.py but for zones_present.
  2. COMPUTE (needs quota): per-zone area share over the AOI via a grouped
     pixelArea sum, plus distinct-value sanity (no single-cluster collapse).

Run:  EE_PROJECT=probformer ../.venv/bin/python tools/check_zones.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ee  # noqa: E402
import utils  # noqa: E402

EXP = dict(west=-53.25, east=-45.90, south=-19.50, north=-12.39)
TOL = 0.5
EXP_SCALE_DEG = 250 / 111320.0
# what the notebook fit (K=3, silhouette pick); sample shares for cross-check
SAMPLE_SHARES = {0: 5518, 1: 8415, 2: 1005}


def bbox_from_transform(t, w, h):
    xs, _, xt, _, ys, yt = t
    xa, xb = xt, xt + xs * w
    ya, yb = yt, yt + ys * h
    return min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)


def main():
    p = utils.init(os.environ.get("EE_PROJECT", "probformer"))
    aid = utils.asset_id(p, "zones_present")
    print(f"project = {p}")
    print(f"asset   = {aid}\n")

    # --- 1. metadata -------------------------------------------------------
    try:
        info = ee.data.getAsset(aid)
    except Exception as e:  # noqa: BLE001
        print(f"MISSING: {type(e).__name__}: {e}")
        return

    atype = info.get("type", "?")
    bands = info.get("bands", [])
    bnames = [b["id"] for b in bands]
    print(f"type        : {atype}")
    print(f"bands       : {bnames}")

    band = bands[0]
    dtype = band.get("dataType", {})
    gp = band.get("grid", {})
    crs = gp.get("crsCode") or gp.get("crsWkt", "?")[:12]
    aff = gp.get("affineTransform", {})
    t = [aff.get("scaleX"), aff.get("shearX", 0.0), aff.get("translateX"),
         aff.get("shearY", 0.0), aff.get("scaleY"), aff.get("translateY")]
    dims = gp.get("dimensions", {})
    w_px, h_px = dims.get("width"), dims.get("height")
    w, s, e, n = bbox_from_transform(t, w_px, h_px)
    scale = abs(t[0])

    print(f"data type   : {dtype.get('precision')} "
          f"[{dtype.get('min')}, {dtype.get('max')}]")
    print(f"crs         : {crs}")
    print(f"scale (deg) : {scale:.6f}   (expect ~{EXP_SCALE_DEG:.6f})")
    print(f"dims (px)   : {w_px} x {h_px}")
    print(f"footprint   : W{w:.3f} S{s:.3f} E{e:.3f} N{n:.3f}")

    flags = []
    if abs(scale - EXP_SCALE_DEG) / EXP_SCALE_DEG > 0.05:
        flags.append("WRONG_SCALE")
    for lbl, val, exp in (("W", w, EXP["west"]), ("E", e, EXP["east"]),
                          ("S", s, EXP["south"]), ("N", n, EXP["north"])):
        if not (exp - TOL <= val <= exp + TOL):
            flags.append(f"{lbl}_OFF")
    if bnames != ["zone"]:
        flags.append("BAND_NAME")
    print(f"metadata    : {'OK' if not flags else 'FLAGS=' + ','.join(flags)}\n")

    # --- 2. spatial zone distribution -------------------------------------
    zones = ee.Image(aid)
    aoi = utils.load_aoi(p)
    print("per-zone area share over AOI (grouped pixelArea sum)...")
    try:
        grouped = ee.Image.pixelArea().addBands(zones).reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="zone"),
            geometry=aoi, scale=1000, maxPixels=int(1e12),
            bestEffort=True, tileScale=16,
        ).getInfo()
        groups = sorted(grouped.get("groups", []), key=lambda g: g["zone"])
        total = sum(g["sum"] for g in groups) or 1.0
        smp_tot = sum(SAMPLE_SHARES.values())
        print(f"  {'zone':>4} {'area_km2':>12} {'share':>7}   {'sample%':>8}")
        for g in groups:
            z = int(g["zone"])
            km2 = g["sum"] / 1e6
            share = 100 * g["sum"] / total
            smp = 100 * SAMPLE_SHARES.get(z, 0) / smp_tot
            print(f"  {z:>4} {km2:>12,.0f} {share:>6.1f}%   {smp:>7.1f}%")
        nz = len(groups)
        print(f"\n  distinct zones present : {nz}")
        if nz <= 1:
            print("  *** COLLAPSE: only one cluster present — not meaningful ***")
        else:
            print("  OK: multiple zones present, no single-cluster collapse.")
    except Exception as e:  # noqa: BLE001
        print(f"  compute step failed ({type(e).__name__}: {e})")
        print("  (likely restricted-quota; metadata check above still holds)")


if __name__ == "__main__":
    main()
