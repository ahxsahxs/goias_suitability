"""Shared helpers: EE init, config loading, the 250 m grid, and asset/export utilities.

Nothing here performs a server call at import time, so the module is import-safe
(syntax-checkable) without Earth Engine authentication.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import yaml

try:
    import ee
except ImportError:  # allow docs/lint without ee installed
    ee = None  # type: ignore

# --- paths -------------------------------------------------------------------
PKG_ROOT = Path(__file__).resolve().parent.parent          # goias_agromarket/
CONFIG_DIR = PKG_ROOT / "config"
EE_CRED = Path("~/.config/earthengine/credentials").expanduser()


@lru_cache(maxsize=None)
def cfg(name: str = "datasets") -> dict:
    """Load and cache a YAML config file from config/."""
    with open(CONFIG_DIR / f"{name}.yaml") as fh:
        return yaml.safe_load(fh)


# --- Earth Engine init -------------------------------------------------------
def credentials_project() -> str | None:
    """Read the cloud project stored in the EE credentials file, if any."""
    if EE_CRED.exists():
        try:
            return json.load(open(EE_CRED)).get("project")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def init(project: str | None = None):
    """Initialize Earth Engine. Project resolves from arg -> $EE_PROJECT ->
    credentials file. Returns the project id used."""
    project = project or os.environ.get("EE_PROJECT") or credentials_project()
    if project is None:
        raise RuntimeError(
            "No EE project found. Re-auth with `earthengine authenticate` and/or "
            "set $EE_PROJECT."
        )
    ee.Initialize(project=project)
    return project


# --- the analysis grid -------------------------------------------------------
def scale_m() -> int:
    return int(cfg()["grid"]["scale_m"])


def crs() -> str:
    return cfg()["grid"]["crs"]


def grid_projection():
    """The 250 m target projection (EPSG:4326 at 250 m)."""
    return ee.Projection(crs()).atScale(scale_m())


# --- raster harmonization to the grid ---------------------------------------
def to_grid_bilinear(img):
    """Resample a *coarse* continuous image onto the 250 m grid (bilinear)."""
    return img.resample("bilinear").reproject(grid_projection())


def to_grid_mean(img, max_pixels: int = 1024):
    """Coarsen a *fine* image (e.g. 30 m terrain) to the 250 m grid by averaging."""
    return img.reduceResolution(ee.Reducer.mean(), maxPixels=max_pixels).reproject(
        grid_projection()
    )


# --- assets & exports --------------------------------------------------------
def asset_root(project: str) -> str:
    return f"projects/{project}/assets/{cfg()['asset']['subfolder']}"


def asset_id(project: str, name: str) -> str:
    return f"{asset_root(project)}/{name}"


def ensure_folder(project: str):
    """Create projects/<project>/assets/goias as an EE FOLDER if absent."""
    root = asset_root(project)
    try:
        ee.data.getAsset(root)
    except ee.EEException:
        ee.data.createAsset({"type": "FOLDER"}, root)
    return root


def export_image(img, project: str, name: str, region, scale: int | None = None,
                 start: bool = True, overwrite: bool = False):
    """Submit an image -> EE asset export at the 250 m grid. Returns the task."""
    aid = asset_id(project, name)
    if overwrite:
        try:
            ee.data.deleteAsset(aid)
        except ee.EEException:
            pass
    task = ee.batch.Export.image.toAsset(
        image=img,
        description=name,
        assetId=aid,
        region=region,
        scale=scale or scale_m(),
        crs=crs(),
        maxPixels=int(1e13),
    )
    if start:
        task.start()
    return task


def export_table(fc, project: str, name: str, start: bool = True):
    """Submit a FeatureCollection -> EE table asset export."""
    aid = asset_id(project, name)
    task = ee.batch.Export.table.toAsset(collection=fc, description=name, assetId=aid)
    if start:
        task.start()
    return task


def load_aoi(project: str):
    """Return the AOI geometry from the cached asset, or build it from the
    local IBGE malha municipal mesh (see src/ibge_mesh.py)."""
    import features  # local import to avoid an import cycle

    aid = asset_id(project, "aoi")
    try:
        ee.data.getAsset(aid)
        return ee.FeatureCollection(aid).geometry()
    except ee.EEException:
        return features.aoi_geometry()


# --- calibration / validation spatial holdout --------------------------------
# The 50/50 split lives in ONE place: the exported `calib_val_split` asset
# (tools/make_calib_val_split.py), a Byte band `split` with 0 = calibration,
# 1 = validation, over a 6x6 grid of ~130 km blocks sized from the measured
# residual autocorrelation range. Every consumer reads that asset
# rather than recomputing the block grid, because zoning.build_strat_band bins
# ee.Geometry(AOI).bounds(): if `aoi` were re-exported the bounds would shift and
# each tool would silently see a different split. Pinning to the asset keeps the
# two halves bit-identical across every stage of the cascade.
SPLIT_ASSET = "calib_val_split"
SPLIT_HALVES = ("calib", "val", "full")


def split_half(default: str = "full") -> str:
    """Resolve $SPLIT_HALF to one of 'calib' | 'val' | 'full' (house env pattern).

    'all' is accepted by the tools that loop over every domain; it is NOT a valid
    mask selector, so it is returned verbatim for the caller to handle explicitly
    rather than being silently collapsed to one half.
    """
    h = (os.environ.get("SPLIT_HALF") or default).strip().lower()
    if h not in SPLIT_HALVES + ("all",):
        raise SystemExit(
            f"SPLIT_HALF must be one of {list(SPLIT_HALVES) + ['all']}, got {h!r}")
    return h


def split_image(project: str):
    """The `split` band of the holdout asset (0 = calibration, 1 = validation)."""
    return ee.Image(asset_id(project, SPLIT_ASSET)).select("split")


def split_mask(project: str, half: str | None = None):
    """Mask for one half of the holdout, or ``None`` for the full domain.

    Returns ``None`` -- not ``ee.Image(1)`` -- for 'full'. Every call site already
    branches on ``if mask is not None``, so None threads through without new code
    AND leaves the full-domain graph bit-identical to the pre-holdout one. That
    bit-identity is what makes the 'full' row of a domain comparison a valid
    baseline instead of a recomputation, so do not "simplify" it to a constant
    image.

    Restrict by MASK, never by ``geometry=``: the reduction extent and tiling then
    stay identical across domains (so the halves are directly comparable), and the
    guardrail that every exported product covers the whole AOI is untouched.
    """
    half = (half or split_half()).strip().lower()
    if half == "full":
        return None
    if half == "calib":
        return split_image(project).eq(0)
    if half == "val":
        return split_image(project).eq(1)
    raise SystemExit(f"split_mask: half must be 'calib' | 'val' | 'full', got {half!r}")


def and_split(mask, project: str, half: str | None = None):
    """Intersect an existing mask with a half of the holdout.

    ``mask`` may be None (meaning "no restriction yet"), which is why this is a
    helper rather than an inline ``.And()`` at each site.
    """
    sm = split_mask(project, half)
    if sm is None:
        return mask
    return sm if mask is None else ee.Image(mask).And(sm)


def range_report(img, region, scale: int = 1000):
    """DataFrame of per-band min/mean/max over the region — the DoD sanity check."""
    import pandas as pd

    red = (
        ee.Reducer.minMax()
        .combine(ee.Reducer.mean(), sharedInputs=True)
    )
    stats = img.reduceRegion(
        reducer=red, geometry=region, scale=scale, maxPixels=int(1e12),
        bestEffort=True, tileScale=16,
    ).getInfo()
    rows = []
    for b in img.bandNames().getInfo():
        rows.append(
            (b, stats.get(f"{b}_min"), stats.get(f"{b}_mean"), stats.get(f"{b}_max"))
        )
    return pd.DataFrame(rows, columns=["band", "min", "mean", "max"])


def task_summary(tasks) -> str:
    """One-line status per task (call .status() server-side)."""
    lines = []
    for t in tasks:
        s = t.status()
        lines.append(f"  {s.get('description'):28s} {s.get('state'):10s} {s.get('id','')}")
    return "\n".join(lines)
