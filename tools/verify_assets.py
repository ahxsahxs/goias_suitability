"""Verify the geographic footprint / projection / scale of the built EE assets.

Reads each asset's stored metadata only (band crs + crs_transform + dimensions),
so it works even in EE 'restricted mode' (no compute). For every image asset it
reconstructs the pixel-grid bounding box and compares it to the expected
Goiás + DF envelope, flagging displacement or wrong scale.

Run:  EE_PROJECT=probformer ../.venv/bin/python tools/verify_assets.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ee  # noqa: E402
import utils  # noqa: E402

# Expected GO+DF envelope (WGS84) and target grid scale.
EXP = dict(west=-53.25, east=-45.90, south=-19.50, north=-12.39)
TOL = 0.5                      # deg slack on each edge
EXP_SCALE_DEG = 250 / 111320.0  # ~0.002246 deg ~ 250 m at the equator

ASSETS = [
    "aoi",
    "feat_climate", "feat_terrain", "feat_soil", "feat_water",
    "feat_phenology", "feat_access", "feat_landcover", "feat_siting",
    "feat_conservation",
    "feature_stack_250m", "feature_stack_250m_z",
    "suit_present", "suit_present_comp", "suit_present_sens", "zones_present",
    # Phase B (Parts 12–14)
    "feat_realized", "realized_vs_potential",
]
# Part 11 — CMIP6 outputs (MISSING until the export tasks complete, then verified).
for _ssp in ("ssp245", "ssp585"):
    for _win in ("2031_2050", "2051_2070"):
        ASSETS += [f"suit_future_{_ssp}_{_win}", f"delta_{_ssp}_{_win}",
                   f"agreement_{_ssp}_{_win}"]


def bbox_from_transform(t, w, h):
    """[xS,_,xT,_,yS,yT] + dims -> (west, south, east, north) in CRS units."""
    xs, _, xt, _, ys, yt = t
    xa, xb = xt, xt + xs * w
    ya, yb = yt, yt + ys * h
    return min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)


def fmt(v):
    return f"{v:8.3f}" if isinstance(v, (int, float)) else f"{v:>8}"


def main():
    p = utils.init(os.environ.get("EE_PROJECT", "probformer"))
    print(f"project = {p}")
    print(f"expected envelope: lon[{EXP['west']}, {EXP['east']}]  "
          f"lat[{EXP['south']}, {EXP['north']}]   scale~{EXP_SCALE_DEG:.6f} deg\n")

    hdr = f"{'asset':22s} {'type':7s} {'crs':10s} {'scale_deg':>10s}  {'footprint W/S/E/N':>40s}  flags"
    print(hdr)
    print("-" * len(hdr))

    for name in ASSETS:
        aid = utils.asset_id(p, name)
        try:
            info = ee.data.getAsset(aid)
        except Exception as e:  # noqa: BLE001
            print(f"{name:22s} MISSING  ({type(e).__name__})")
            continue

        atype = info.get("type", "?")
        if atype != "IMAGE":
            # table (aoi): report stored geometry bounds via a cheap vector op
            try:
                b = ee.FeatureCollection(aid).geometry().bounds(1000).coordinates().getInfo()[0]
                xs = [c[0] for c in b]; ys = [c[1] for c in b]
                w, s, e, n = min(xs), min(ys), max(xs), max(ys)
                flags = check_bounds(w, s, e, n)
                print(f"{name:22s} {atype:7s} {'-':10s} {'-':>10s}  "
                      f"{w:8.3f}{s:8.3f}{e:8.3f}{n:8.3f}  {flags}")
            except Exception as e:  # noqa: BLE001
                print(f"{name:22s} {atype:7s}  (bounds read failed: {e})")
            continue

        band = info["bands"][0]
        gp = band.get("grid", {})
        crs = gp.get("crsCode") or gp.get("crsWkt", "?")[:10]
        aff = gp.get("affineTransform", {})
        t = [aff.get("scaleX"), aff.get("shearX", 0.0), aff.get("translateX"),
             aff.get("shearY", 0.0), aff.get("scaleY"), aff.get("translateY")]
        dims = gp.get("dimensions", {})
        w_px, h_px = dims.get("width"), dims.get("height")
        if None in t or w_px is None:
            print(f"{name:22s} {atype:7s} {crs:10s}  (no grid metadata)")
            continue
        w, s, e, n = bbox_from_transform(t, w_px, h_px)
        scale = abs(t[0])
        flags = check_bounds(w, s, e, n) + check_scale(scale)
        nb = len(info["bands"])
        print(f"{name:22s} {atype:7s} {crs:10s} {scale:10.6f}  "
              f"{w:8.3f}{s:8.3f}{e:8.3f}{n:8.3f}  [{nb}b] {flags}")


def check_bounds(w, s, e, n):
    f = []
    if not (EXP["west"] - TOL <= w <= EXP["west"] + TOL):
        f.append("WEST_OFF")
    if not (EXP["east"] - TOL <= e <= EXP["east"] + TOL):
        f.append("EAST_OFF")
    if not (EXP["south"] - TOL <= s <= EXP["south"] + TOL):
        f.append("SOUTH_OFF")
    if not (EXP["north"] - TOL <= n <= EXP["north"] + TOL):
        f.append("NORTH_OFF")
    return ("DISPLACED:" + ",".join(f)) if f else "ok"


def check_scale(scale):
    if abs(scale - EXP_SCALE_DEG) / EXP_SCALE_DEG > 0.05:
        return f" WRONG_SCALE({scale:.6f})"
    return ""


if __name__ == "__main__":
    main()
