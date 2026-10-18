"""Verify the footprint / projection / scale of the built EE assets.

Reads stored metadata only (band crs + affine transform + dimensions), so it works
even in EE restricted (no-compute) mode. Each asset's pixel-grid bounding box is
compared with the territory envelope (from the local mesh) and the grid scale.

Run:  EE_PROJECT=<your-project> uv run python pipeline.py verify
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import ee  # noqa: E402
import utils  # noqa: E402

TOL = 0.5  # deg slack on each edge


def expected():
    w, s, e, n = utils.aoi_bounds()
    scale_deg = utils.scale_m() / 111320.0   # EPSG:4326 grid step at the equator
    return dict(west=w, east=e, south=s, north=n), scale_deg


def asset_list():
    names = [
        "aoi",
        "feat_climate", "feat_terrain", "feat_soil", "feat_water",
        "feat_landcover", "feat_siting", "feat_conservation",
        "feature_stack_250m", "feature_stack_250m_z",
        "feat_realized", utils.SPLIT_ASSET,
        "suit_present", "suit_present_comp", "suit_present_sens", "zones_present",
        "realized_vs_potential",
    ]
    cc = utils.cfg()["cmip6"]
    for ssp in cc["scenarios"]:
        for win in cc["windows"]:
            names += [f"suit_future_{ssp}_{win}", f"delta_{ssp}_{win}",
                      f"agreement_{ssp}_{win}"]
    names.append("clim_future_ssp585_2051_2070")   # horizon cache (export_horizon_climate)
    return names


EXP, EXP_SCALE_DEG = None, None


def bbox_from_transform(t, w, h):
    """[xS,_,xT,_,yS,yT] + dims -> (west, south, east, north) in CRS units."""
    xs, _, xt, _, ys, yt = t
    xa, xb = xt, xt + xs * w
    ya, yb = yt, yt + ys * h
    return min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)


def fmt(v):
    return f"{v:8.3f}" if isinstance(v, (int, float)) else f"{v:>8}"


def main():
    global EXP, EXP_SCALE_DEG
    EXP, EXP_SCALE_DEG = expected()
    p = utils.init()
    print(f"project = {p}   territory = {utils.territory()['name']}")
    print(f"expected envelope: lon[{EXP['west']}, {EXP['east']}]  "
          f"lat[{EXP['south']}, {EXP['north']}]   scale~{EXP_SCALE_DEG:.6f} deg\n")

    hdr = f"{'asset':22s} {'type':7s} {'crs':10s} {'scale_deg':>10s}  {'footprint W/S/E/N':>40s}  flags"
    print(hdr)
    print("-" * len(hdr))

    for name in asset_list():
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
