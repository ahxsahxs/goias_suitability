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
    """Return the AOI geometry from the cached asset, or build it from GAUL."""
    import features  # local import to avoid an import cycle

    aid = asset_id(project, "aoi")
    try:
        ee.data.getAsset(aid)
        return ee.FeatureCollection(aid).geometry()
    except ee.EEException:
        return features.aoi_geometry()


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
