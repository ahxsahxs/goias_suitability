"""Shared helpers: config, EE init, the analysis grid, assets/exports, output paths.

No server call happens at import time, so every module stays import-safe without
Earth Engine authentication.
"""
from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path

import yaml

try:
    import ee
except ImportError:  # allow docs/lint without ee installed
    ee = None  # type: ignore

# --- paths -------------------------------------------------------------------
PKG_ROOT = Path(__file__).resolve().parent.parent          # repo root
REPO = PKG_ROOT
CONFIG_DIR = PKG_ROOT / "config"
CHAPTERS = PKG_ROOT / "thesis" / "Chapters"
EE_CRED = Path("~/.config/earthengine/credentials").expanduser()

# IBGE malha municipal schema (fixed across UFs and editions).
MESH_COLS = dict(code_col="CD_MUN", name_col="NM_MUN", uf_col="SIGLA_UF",
                 state_name_col="NM_UF")


@lru_cache(maxsize=None)
def _load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / f"{name}.yaml") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=None)
def territory() -> dict:
    """The territory config: $TERRITORY (path to a YAML file) or config/territory.yaml.

    Everything that changes when the AOI changes lives there.
    """
    path = os.environ.get("TERRITORY") or CONFIG_DIR / "territory.yaml"
    with open(path) as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=None)
def cfg(name: str = "datasets") -> dict:
    """Load and cache a YAML config file from config/.

    ``cfg()`` (datasets) also carries the territory as the ``asset`` and
    ``municipal_mesh`` blocks, so every consumer reads one dict.
    """
    data = dict(_load_yaml(name))
    if name == "datasets":
        t = territory()
        data["asset"] = {"subfolder": t["asset_subfolder"]}
        data["municipal_mesh"] = {
            "path": t["mesh_path"], "layer": "malha_municipal", **MESH_COLS,
            "uf_values": list(t["ufs"]), "join_key": t["join_key"],
            "simplify_tolerance_deg": t["simplify_tolerance_deg"],
        }
    return data


def out_dir() -> Path:
    """Where tools write their CSVs: $SCRATCHPAD if set, else territory `output_dir`."""
    d = os.environ.get("SCRATCHPAD") or str(PKG_ROOT / territory()["output_dir"])
    return Path(d)


def out_path(name: str) -> Path:
    return out_dir() / name


def scratch_path(name: str) -> Path:
    """Intermediate, non-committed files: $SCRATCHPAD if set, else data/scratch/."""
    return Path(os.environ.get("SCRATCHPAD") or PKG_ROOT / "data" / "scratch") / name


def aoi_bounds() -> tuple[float, float, float, float]:
    """(west, south, east, north) of the territory mesh -- offline, no EE call."""
    import geopandas as gpd

    m = cfg()["municipal_mesh"]
    gdf = gpd.read_file(PKG_ROOT / m["path"], layer=m["layer"])
    gdf = gdf[gdf[m["uf_col"]].isin(m["uf_values"])]
    w, s, e, n = gdf.to_crs(4326).total_bounds
    return float(w), float(s), float(e), float(n)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


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
    """The analysis projection (EPSG:4326 at 250 m)."""
    return ee.Projection(crs()).atScale(scale_m())


def to_grid_bilinear(img):
    """Resample a *coarse* continuous image onto the grid (bilinear)."""
    return img.resample("bilinear").reproject(grid_projection())


def to_grid_mean(img, max_pixels: int = 1024):
    """Coarsen a *fine* image (e.g. 30 m terrain) to the grid by averaging."""
    return img.reduceResolution(ee.Reducer.mean(), maxPixels=max_pixels).reproject(
        grid_projection()
    )


# --- assets & exports --------------------------------------------------------
def asset_root(project: str) -> str:
    return f"projects/{project}/assets/{cfg()['asset']['subfolder']}"


def asset_id(project: str, name: str) -> str:
    return f"{asset_root(project)}/{name}"


def asset_exists(project: str, name: str) -> bool:
    try:
        ee.data.getAsset(asset_id(project, name))
        return True
    except ee.EEException:
        return False


def ensure_folder(project: str):
    """Create the territory asset folder if absent."""
    root = asset_root(project)
    try:
        ee.data.getAsset(root)
    except ee.EEException:
        ee.data.createAsset({"type": "FOLDER"}, root)
    return root


def _delete_if_exists(aid: str) -> None:
    try:
        ee.data.deleteAsset(aid)
    except ee.EEException:
        pass


def export_image(img, project: str, name: str, region, scale: int | None = None,
                 start: bool = True, overwrite: bool = False):
    """Submit an image -> EE asset export on the analysis grid. Returns the task.

    ``overwrite`` DELETES the old asset before submitting, so a failed task leaves
    no asset at all -- back up first (tools/backup_assets.py).
    """
    aid = asset_id(project, name)
    if overwrite:
        _delete_if_exists(aid)
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


def export_table(fc, project: str, name: str, start: bool = True,
                 overwrite: bool = False):
    """Submit a FeatureCollection -> EE table asset export.

    EE refuses to overwrite a table asset, so ``overwrite`` deletes it first.
    """
    aid = asset_id(project, name)
    if overwrite:
        _delete_if_exists(aid)
    task = ee.batch.Export.table.toAsset(collection=fc, description=name, assetId=aid)
    if start:
        task.start()
    return task


def wait_for(project: str, names, tasks=(), timeout: int = 28800, poll: int = 45):
    """Block until every named asset exists; raise if a task fails or on timeout."""
    names = [names] if isinstance(names, str) else list(names)
    t0 = time.time()
    while True:
        have = [n for n in names if asset_exists(project, n)]
        if len(have) == len(names):
            log(f"  ready: {', '.join(names)}")
            return
        for t in tasks:
            st = t.status()
            if st["state"] in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"task {st.get('description')} {st['state']}: "
                                   f"{st.get('error_message', '')}")
        if time.time() - t0 > timeout:
            raise TimeoutError(f"timeout waiting for {set(names) - set(have)}")
        time.sleep(poll)


def load_aoi(project: str):
    """AOI geometry from the cached `aoi` asset, else built from the local mesh."""
    import features  # local import to avoid an import cycle

    aid = asset_id(project, "aoi")
    try:
        ee.data.getAsset(aid)
        return ee.FeatureCollection(aid).geometry()
    except ee.EEException:
        return features.aoi_geometry()


# --- calibration / validation spatial holdout --------------------------------
# The 50/50 split lives in ONE place: the `calib_val_split` asset (Byte band
# `split`: 0 = calibration, 1 = validation), built by tools/make_calib_val_split.py.
# Always read the asset; never recompute the block grid, which bins the AOI bounds
# and would silently shift if `aoi` were re-exported.
SPLIT_ASSET = "calib_val_split"
SPLIT_HALVES = ("calib", "val", "full")


def split_half(default: str = "full") -> str:
    """Resolve $SPLIT_HALF to 'calib' | 'val' | 'full' (or 'all', returned verbatim
    for tools that loop over every domain)."""
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

    ``None`` (not ``ee.Image(1)``) keeps the full-domain graph bit-identical to the
    unrestricted one; every call site branches on ``if mask is not None``. Restrict
    by MASK, never by ``geometry=``, so extent and tiling match across domains.
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
    """Intersect an existing mask (or None) with a half of the holdout."""
    sm = split_mask(project, half)
    if sm is None:
        return mask
    return sm if mask is None else ee.Image(mask).And(sm)


def range_report(img, region, scale: int = 1000):
    """DataFrame of per-band min/mean/max over the region (sanity check)."""
    import pandas as pd

    red = ee.Reducer.minMax().combine(ee.Reducer.mean(), sharedInputs=True)
    stats = img.reduceRegion(
        reducer=red, geometry=region, scale=scale, maxPixels=int(1e12),
        bestEffort=True, tileScale=16,
    ).getInfo()
    rows = [(b, stats.get(f"{b}_min"), stats.get(f"{b}_mean"), stats.get(f"{b}_max"))
            for b in img.bandNames().getInfo()]
    return pd.DataFrame(rows, columns=["band", "min", "mean", "max"])


def task_summary(tasks) -> str:
    """One-line status per task (calls .status() server-side)."""
    lines = []
    for t in tasks:
        s = t.status()
        lines.append(f"  {s.get('description'):28s} {s.get('state'):10s} {s.get('id','')}")
    return "\n".join(lines)
