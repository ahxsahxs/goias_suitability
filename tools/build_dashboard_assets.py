"""Build static data assets for docs/dashboard/public/data/ (docs/dashboard_ux_plan.md §2.3).

v1-safe scope: pulls only the already-built, STABLE parts of the pipeline — feat_*,
feature_stack_250m(_z), suit_present (7 suit_* + 7 class_* bands), suit_present_sens
(7 sens_* bands), zones_present, and the IBGE municipal mesh (Part 12). Deliberately
does NOT touch suit_future*, delta_*, agreement_*, realized_vs_potential, or
feat_realized — those parts of the pipeline are being recomputed as of 2026-09-19
(confirmed with the user) and are off-limits until that settles. The extended
municipal ranking below is therefore a NEW, v1-safe file (7 suit_* + zone only) —
it does not touch or overwrite thesis/Chapters/Figures/municipal_ranking.csv, whose
delta_other_crops/underused_* columns depend on exactly those off-limits assets.

Note: the zone count is read from zone_profiles.csv at run time, NOT hardcoded — the
zoning asset currently has 10 zones (0-9), not the 7 that CLAUDE.md's Part-10 row
still describes (that row is stale; a rezone appears to have run since it was written).

Run:
  EE_PROJECT=probformer uv run python tools/build_dashboard_assets.py [--only vectors|config|municipal|diagnostics|rasters]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ee  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import requests  # noqa: E402
import yaml  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, ListedColormap  # noqa: E402

import external  # noqa: E402
import ibge_mesh  # noqa: E402
import utils  # noqa: E402
from palettes import FAO_ORDER, PAL_FAO, PAL_SUIT, SEGMENTS, zone_palette  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "docs" / "dashboard" / "public" / "data"
SCRATCH_DIR = REPO_ROOT / "docs" / "dashboard" / ".build-scratch"
CONFIG_DIR = REPO_ROOT / "config"

TS = 8  # tileScale — see CLAUDE.md §11 "validation is compute-heavy" gotcha


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# =============================================================================
# 1. Vector assets — pure geopandas, no EE call needed
# =============================================================================
def build_vectors() -> None:
    out = DATA_DIR / "geojson"
    out.mkdir(parents=True, exist_ok=True)

    m = utils.cfg()["municipal_mesh"]
    gdf_full = ibge_mesh._load_gdf()

    # Dissolve from full-precision geometry first (cancels shared borders before any
    # simplification — far fewer vertices than simplifying-then-dissolving; mirrors
    # ibge_mesh.aoi_ee_geometry()), then simplify the single dissolved result.
    aoi_geom = gdf_full.union_all().simplify(m["simplify_tolerance_deg"], preserve_topology=True)
    aoi_path = out / "aoi.geojson"
    aoi_path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": aoi_geom.__geo_interface__}))
    log(f"wrote {aoi_path}")

    gdf = gdf_full.assign(geometry=gdf_full.geometry.simplify(m["simplify_tolerance_deg"], preserve_topology=True))
    muni_path = out / "municipios.geojson"
    gdf.to_file(muni_path, driver="GeoJSON")
    log(f"wrote {muni_path} ({len(gdf)} municipalities)")


# =============================================================================
# 2. Config YAML -> JSON
# =============================================================================
def build_config_json() -> None:
    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)

    for name in ("segments", "ahp_matrices"):
        with open(CONFIG_DIR / f"{name}.yaml") as fh:
            payload = yaml.safe_load(fh)
        dest = out / f"{name}.json"
        dest.write_text(json.dumps(payload, indent=2))
        log(f"wrote {dest}")


# =============================================================================
# 3. v1-safe extended municipal ranking (all 7 suit_* + zone; no delta/underused)
# =============================================================================
def build_municipal_ranking() -> None:
    project = utils.init()
    aid = lambda n: utils.asset_id(project, n)  # noqa: E731

    suit = ee.Image(aid("suit_present"))
    zones = ee.Image(aid("zones_present")).rename("zone")
    muni = external.municipal_fc()

    agg = suit.select([f"suit_{s}" for s in SEGMENTS]).addBands(zones)
    means = external.municipal_means(muni, agg, scale=250)
    props = ["NM_MUN", "SIGLA_UF", "zone", *[f"suit_{s}" for s in SEGMENTS]]
    feats = means.select(props, None, False).getInfo()["features"]

    df = pd.DataFrame([f["properties"] for f in feats]).dropna(subset=[f"suit_{SEGMENTS[0]}"])
    df["zone"] = df["zone"].round().astype(int)

    out_csv = DATA_DIR / "csv" / "municipal_ranking.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(out_csv, index=False)
    log(f"wrote {out_csv} ({len(df)} municipalities)")

    m = utils.cfg()["municipal_mesh"]
    gdf = ibge_mesh._load_gdf()
    gdf = gdf.assign(geometry=gdf.geometry.simplify(m["simplify_tolerance_deg"], preserve_topology=True))
    merged = gdf.merge(df, on="NM_MUN", how="inner", validate="one_to_one", suffixes=("", "_dup"))
    merged = merged.drop(columns=[c for c in merged.columns if c.endswith("_dup")])
    out_geojson = DATA_DIR / "geojson" / "municipal_ranking.geojson"
    merged.to_file(out_geojson, driver="GeoJSON")
    log(f"wrote {out_geojson} ({len(merged)} municipalities)")


# =============================================================================
# 4. Diagnostic CSV passthrough (already produced by tools/gen_diag_csvs.py / src/zoning.py)
# =============================================================================
DIAG_CSVS = {
    "zone_profiles.csv": REPO_ROOT / "zone_profiles.csv",
    "zoning_kselect.csv": REPO_ROOT / "thesis" / "Chapters" / "zoning_kselect.csv",
    "factor_variance.csv": REPO_ROOT / "thesis" / "Chapters" / "factor_variance.csv",
    "theme_roughness.csv": REPO_ROOT / "thesis" / "Chapters" / "theme_roughness.csv",
    "theme_roughness_points.csv": REPO_ROOT / "thesis" / "Chapters" / "theme_roughness_points.csv",
}


def build_diagnostics() -> None:
    out = DATA_DIR / "csv"
    out.mkdir(parents=True, exist_ok=True)
    for name, src in DIAG_CSVS.items():
        if not src.exists():
            log(f"  !! missing {src}, skipped")
            continue
        shutil.copyfile(src, out / name)
        log(f"copied {src} -> {out / name}")


def zone_count() -> int:
    """Ground truth for how many zones actually exist — never hardcode this."""
    df = pd.read_csv(DIAG_CSVS["zone_profiles.csv"])
    return len(df)


def build_home_stats() -> None:
    """Small aggregate for the Home route's stat-chip strip — computed once here
    from files this script already writes (municipal_ranking.csv, zone_profiles.csv),
    never recomputed client-side. Deliberately excludes any validation/CMIP6/realized-
    use number (kappa, AUC, underuse share): those depend on assets that are off-limits
    while the background pipeline recomputes them (see module docstring)."""
    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)

    muni = pd.read_csv(DATA_DIR / "csv" / "municipal_ranking.csv")
    zones = pd.read_csv(DIAG_CSVS["zone_profiles.csv"])
    top_zone = zones.loc[zones["n"].idxmax()]

    stats = {
        "n_zones": len(zones),
        "n_segments": len(SEGMENTS),
        "n_municipalities": len(muni),
        "mean_suit_soybean": round(float(muni["suit_soybean"].mean()), 3),
        "top_zone": int(top_zone["zone"]),
        "top_zone_share_pct": round(100 * float(top_zone["n"]) / float(zones["n"].sum()), 1),
    }
    dest = out / "home_stats.json"
    dest.write_text(json.dumps(stats, indent=2))
    log(f"wrote {dest}")


# =============================================================================
# 5. Sensitivity percentiles (reduceRegion, NOT a raster — used for a histogram)
# =============================================================================
def build_sensitivity_json() -> None:
    project = utils.init()
    aoi = utils.load_aoi(project)
    sens = ee.Image(utils.asset_id(project, "suit_present_sens"))

    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)

    percentiles = [5, 25, 50, 75, 95]
    reducer = ee.Reducer.percentile(percentiles)
    stats = sens.reduceRegion(
        reducer=reducer, geometry=aoi, scale=250, maxPixels=int(1e10),
        tileScale=TS, bestEffort=True,
    ).getInfo()

    for seg in SEGMENTS:
        band = f"sens_{seg}"
        payload = {f"p{p}": stats.get(f"{band}_p{p}") for p in percentiles}
        dest = out / f"sensitivity_{seg}.json"
        dest.write_text(json.dumps(payload, indent=2))
    log(f"wrote sensitivity_<segment>.json for {len(SEGMENTS)} segments")


# =============================================================================
# 6. Hero rasters: suit_present (14 bands) + zones_present (1 band) -> PMTiles
# =============================================================================
# getDownloadURL caps a single request at 48 MiB; a full-AOI float32 250 m band
# is ~93 MB. Cast to uint8 server-side first (continuous bands scaled 0..254,
# 255 reserved as a nodata sentinel so masked pixels survive the uint8 round
# trip without needing NaN) — ~23 MB, comfortably under the limit, and more
# than enough precision for a colorized visualization tile.
NODATA_SENTINEL = 255
CONTINUOUS_STEPS = 254


def _prep_band(image: "ee.Image", band: str, categorical: bool) -> "ee.Image":
    b = image.select(band)
    if categorical:
        scaled = b.toUint8()
    else:
        scaled = b.multiply(CONTINUOUS_STEPS).round().toUint8()
    return scaled.unmask(NODATA_SENTINEL)


def _download_band(image: "ee.Image", region, out_path: Path) -> None:
    url = image.getDownloadURL({
        "region": region,
        "scale": 250,
        "crs": "EPSG:4326",
        "format": "GEO_TIFF",
    })
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    out_path.write_bytes(r.content)


def _colorize(src_path: Path, dst_path: Path, palette: list[str], categorical: bool = False) -> None:
    with rasterio.open(src_path) as src:
        arr = src.read(1)
        profile = src.profile

    mask = arr == NODATA_SENTINEL

    if categorical:
        cmap = ListedColormap(palette)
        idx = np.clip(arr, 0, len(palette) - 1)
        rgba = (cmap(idx) * 255).astype("uint8")
    else:
        cmap = LinearSegmentedColormap.from_list("c", palette)
        norm = np.clip(arr.astype("float64") / CONTINUOUS_STEPS, 0, 1)
        rgba = (cmap(norm) * 255).astype("uint8")
    rgba[mask, 3] = 0

    profile.update(count=4, dtype="uint8", nodata=None, compress="deflate")
    with rasterio.open(dst_path, "w", **profile) as dst:
        for i in range(4):
            dst.write(rgba[:, :, i], i + 1)


def _reproject_webmercator(src_path: Path, dst_path: Path) -> None:
    subprocess.run(
        ["gdalwarp", "-t_srs", "EPSG:3857", "-r", "near", "-overwrite",
         str(src_path), str(dst_path)],
        check=True, capture_output=True,
    )


def _to_pmtiles(src_path: Path, dst_path: Path) -> None:
    rio_bin = Path(sys.executable).parent / "rio"
    subprocess.run(
        [str(rio_bin), "pmtiles", str(src_path), str(dst_path)],
        check=True, capture_output=True,
    )


def _build_one_raster(image: "ee.Image", band: str, region, palette: list[str], out_name: str,
                       categorical: bool = False) -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    raw = SCRATCH_DIR / f"{out_name}_raw.tif"
    rgba = SCRATCH_DIR / f"{out_name}_rgba.tif"
    merc = SCRATCH_DIR / f"{out_name}_merc.tif"
    out_dir = DATA_DIR / "pmtiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{out_name}.pmtiles"

    log(f"  downloading {band} ...")
    prepped = _prep_band(image, band, categorical)
    _download_band(prepped, region, raw)
    _colorize(raw, rgba, palette, categorical=categorical)
    _reproject_webmercator(rgba, merc)
    if out_path.exists():
        out_path.unlink()
    _to_pmtiles(merc, out_path)
    size_kb = out_path.stat().st_size / 1024
    log(f"  wrote {out_path} ({size_kb:.0f} KB)")


def build_rasters(only_band: str | None = None) -> None:
    project = utils.init()
    region = ee.FeatureCollection(utils.asset_id(project, "aoi")).geometry()
    suit = ee.Image(utils.asset_id(project, "suit_present"))
    zones = ee.Image(utils.asset_id(project, "zones_present"))
    nzones = zone_count()

    jobs = []
    for seg in SEGMENTS:
        jobs.append((suit, f"suit_{seg}", PAL_SUIT, f"suit_{seg}", False))
        jobs.append((suit, f"class_{seg}", PAL_FAO, f"class_{seg}", True))
    jobs.append((zones, "zone", zone_palette(nzones), "zones_present", True))

    if only_band:
        jobs = [j for j in jobs if j[3] == only_band]
        if not jobs:
            raise SystemExit(f"no raster job named {only_band!r}")

    for image, band, palette, out_name, categorical in jobs:
        _build_one_raster(image, band, region, palette, out_name, categorical=categorical)

    shutil.rmtree(SCRATCH_DIR, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only", choices=["vectors", "config", "municipal", "diagnostics", "rasters", "home_stats"],
        help="run a single stage instead of all of them",
    )
    parser.add_argument("--raster", help="with --only rasters, build a single named layer (e.g. suit_soybean)")
    args = parser.parse_args()

    stages = {
        "vectors": build_vectors,
        "config": build_config_json,
        "municipal": build_municipal_ranking,
        "diagnostics": build_diagnostics,
        "rasters": lambda: build_rasters(args.raster),
        "home_stats": build_home_stats,
    }

    if args.only:
        stages[args.only]()
        return

    for name, fn in stages.items():
        log(f"=== {name} ===")
        fn()
    log("=== done ===")


if __name__ == "__main__":
    main()
