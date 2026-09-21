"""Build static data assets for docs/dashboard/public/data/ (docs/dashboard_ux_plan.md §2.3).

v2 scope (2026-09-20): the pipeline rebuild that was in flight when v1 was built has
completed and is footprint-verified (tools/verify_assets.py). This script now pulls
the full asset set: feat_*, feature_stack_250m(_z), suit_present (7 suit_* + 7
class_* bands), suit_present_sens (7 sens_* bands), zones_present, the IBGE municipal
mesh (Part 12), suit_future_*/delta_*/agreement_* (Part 11, CMIP6), and
realized_vs_potential/feat_realized (Parts 12-13). The extended municipal ranking
below carries all 7 suit_*, zone, all 7 delta_* (off delta_ssp585_2051_2070 only —
not all 4 SSP/window combos), and every underused_<crop> band that actually exists
on realized_vs_potential (currently 4: soybean/sugarcane/other_crops/pisciculture —
cattle/conservation/solar have none by construction, see external.ROLE_CODES). This
is a separate file from thesis/Chapters/Figures/municipal_ranking.csv (produced by
tools/extract_present.py::municipal()) — this script never touches that file.

Delta/agreement raster coverage is deliberately curated, not exhaustive: delta_* PMTiles
cover 5 segments (soybean/sugarcane/other_crops/conservation/solar) x 4 SSP/window
combos = 20 files (docs/dashboard_ux_plan.md §5's manifest); agreement_* is cut down to
just 2 representative combos (other_crops x {ssp585/2051_2070, ssp245/2031_2050}) since
the territory-mean agreement is ~0.999 and near-uniform everywhere regardless of
scenario/segment (see thesis/Chapters/03_methodology.tex's concordância paragraph and
fig:ensemble-agreement) — shipping the full ~20-file combinatorial matrix would mostly
duplicate near-identical maps.

Note: the zone count is read from zone_profiles.csv at run time, NOT hardcoded — the
zoning asset currently has 10 zones (0-9), not the 7 that CLAUDE.md's Part-10 row used
to describe.

Run:
  EE_PROJECT=probformer uv run python tools/build_dashboard_assets.py [--only <stage>]
  (see --help for the full --only stage list)
"""
from __future__ import annotations

import argparse
import json
import math
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
import features  # noqa: E402
import ibge_mesh  # noqa: E402
import utils  # noqa: E402
from palettes import (  # noqa: E402
    FAO_ORDER,
    PAL_AGREEMENT,
    PAL_DIV,
    PAL_FAO,
    PAL_ROLE,
    PAL_SUIT,
    PAL_UNDERUSED,
    SEGMENTS,
    zone_palette,
)

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
# 3. Extended municipal ranking: all 7 suit_*, zone, all 7 delta_* (single combo:
#    ssp585/2051-2070, mirroring tools/extract_present.py::municipal()'s pattern —
#    NOT all 4 SSP/window combos, this is a click-panel snapshot not a scenario
#    switcher), and every underused_<crop> band that actually exists.
# =============================================================================
def build_municipal_ranking() -> None:
    project = utils.init()
    aid = lambda n: utils.asset_id(project, n)  # noqa: E731

    suit = ee.Image(aid("suit_present"))
    zones = ee.Image(aid("zones_present")).rename("zone")
    delta = ee.Image(aid("delta_ssp585_2051_2070"))
    uu = ee.Image(aid("realized_vs_potential"))
    uu_bands = uu.bandNames().getInfo()  # discovered, not assumed — see module docstring
    muni = external.municipal_fc()

    agg = (
        suit.select([f"suit_{s}" for s in SEGMENTS])
        .addBands(zones)
        .addBands(delta.select([f"delta_{s}" for s in SEGMENTS]))
        .addBands(uu.select(uu_bands))
    )
    means = external.municipal_means(muni, agg, scale=250)
    props = [
        "NM_MUN", "SIGLA_UF", "zone",
        *[f"suit_{s}" for s in SEGMENTS],
        *[f"delta_{s}" for s in SEGMENTS],
        *uu_bands,
    ]
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
    from files this script already writes (municipal_ranking.csv, zone_profiles.csv,
    validation_scorecard.json), never recomputed client-side. Run `--only
    validation_scorecard` and `--only municipal` before this stage (the full run,
    with no --only, already orders them correctly)."""
    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)

    muni = pd.read_csv(DATA_DIR / "csv" / "municipal_ranking.csv")
    zones = pd.read_csv(DIAG_CSVS["zone_profiles.csv"])
    top_zone = zones.loc[zones["n"].idxmax()]

    scorecard_path = out / "validation_scorecard.json"
    scorecard = json.loads(scorecard_path.read_text()) if scorecard_path.exists() else {}

    project = utils.init()
    aoi = utils.load_aoi(project)
    delta = ee.Image(utils.asset_id(project, "delta_ssp585_2051_2070"))
    mean_delta = delta.select("delta_other_crops").reduceRegion(
        reducer=ee.Reducer.mean(), geometry=aoi, scale=1000, bestEffort=True,
        tileScale=TS, maxPixels=int(1e9),
    ).getInfo().get("delta_other_crops")

    stats = {
        "n_zones": len(zones),
        "n_segments": len(SEGMENTS),
        "n_municipalities": len(muni),
        "mean_suit_soybean": round(float(muni["suit_soybean"].mean()), 3),
        "top_zone": int(top_zone["zone"]),
        "top_zone_share_pct": round(100 * float(top_zone["n"]) / float(zones["n"].sum()), 1),
        "kappa_soybean": scorecard.get("rf_kappa", {}).get("soybean"),
        "auc_soybean": scorecard.get("presence_auc_boyce", {}).get("soybean", {}).get("auc"),
        "boyce_soybean": scorecard.get("presence_auc_boyce", {}).get("soybean", {}).get("boyce"),
        "underused_soybean_pct": scorecard.get("underuse_pct", {}).get("soybean"),
        "mean_delta_other_crops_ssp585_2051_2070": round(float(mean_delta), 4) if mean_delta is not None else None,
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


def _prep_band(
    image: "ee.Image", band: str, categorical: bool, vmin: float = 0.0, vmax: float = 1.0,
) -> "ee.Image":
    """Scale a band to uint8 0..254 for the 48 MiB download-cap workaround (see comment
    above). `vmin`/`vmax` is the physical domain mapped to that range — [0, 1] for bands
    already provably bounded there (suit_*, agreement_*, underused_*). For a band that is
    NOT provably bounded (e.g. delta_*, which make_figures.py visualizes on a *clipped*
    [-0.15, 0.15] window, not a hard bound), an out-of-window pixel MUST be `.clamp()`ed
    before scaling — otherwise it can compute to exactly 255, the reserved
    NODATA_SENTINEL, and get silently rendered transparent by `_colorize`'s nodata mask."""
    b = image.select(band)
    if categorical:
        scaled = b.toUint8()
    else:
        clamped = b.clamp(vmin, vmax)
        scaled = clamped.subtract(vmin).divide(vmax - vmin).multiply(CONTINUOUS_STEPS).round().toUint8()
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
                       categorical: bool = False, domain: tuple[float, float] = (0.0, 1.0)) -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    raw = SCRATCH_DIR / f"{out_name}_raw.tif"
    rgba = SCRATCH_DIR / f"{out_name}_rgba.tif"
    merc = SCRATCH_DIR / f"{out_name}_merc.tif"
    out_dir = DATA_DIR / "pmtiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{out_name}.pmtiles"

    log(f"  downloading {band} (domain {domain}) ...")
    prepped = _prep_band(image, band, categorical, domain[0], domain[1])
    _download_band(prepped, region, raw)
    _colorize(raw, rgba, palette, categorical=categorical)
    _reproject_webmercator(rgba, merc)
    if out_path.exists():
        out_path.unlink()
    _to_pmtiles(merc, out_path)
    size_kb = out_path.stat().st_size / 1024
    log(f"  wrote {out_path} ({size_kb:.0f} KB)")


def _run_raster_jobs(jobs: list[dict], region, only_band: str | None) -> None:
    if only_band:
        jobs = [j for j in jobs if j["out_name"] == only_band]
        if not jobs:
            raise SystemExit(f"no raster job named {only_band!r}")
    for j in jobs:
        _build_one_raster(
            j["image"], j["band"], region, j["palette"], j["out_name"],
            categorical=j.get("categorical", False), domain=j.get("domain", (0.0, 1.0)),
        )
    shutil.rmtree(SCRATCH_DIR, ignore_errors=True)


def build_rasters(only_band: str | None = None) -> None:
    project = utils.init()
    region = ee.FeatureCollection(utils.asset_id(project, "aoi")).geometry()
    suit = ee.Image(utils.asset_id(project, "suit_present"))
    zones = ee.Image(utils.asset_id(project, "zones_present"))
    nzones = zone_count()

    jobs = []
    for seg in SEGMENTS:
        jobs.append({"image": suit, "band": f"suit_{seg}", "palette": PAL_SUIT,
                     "out_name": f"suit_{seg}", "categorical": False})
        jobs.append({"image": suit, "band": f"class_{seg}", "palette": PAL_FAO,
                     "out_name": f"class_{seg}", "categorical": True})
    jobs.append({"image": zones, "band": "zone", "palette": zone_palette(nzones),
                 "out_name": "zones_present", "categorical": True})

    _run_raster_jobs(jobs, region, only_band)


# =============================================================================
# 6b. CMIP6 shift rasters: delta_<ssp>_<window>_<segment> (diverging) +
#     agreement_<ssp>_<window>_other_crops (2 representative combos only — see
#     module docstring for why the full ~20-file matrix isn't shipped)
# =============================================================================
CMIP6_SCENARIOS = ["ssp245", "ssp585"]
CMIP6_WINDOWS = ["2031_2050", "2051_2070"]
CMIP6_DELTA_SEGMENTS = ["soybean", "sugarcane", "other_crops", "conservation", "solar"]
CMIP6_AGREEMENT_COMBOS = [("ssp585", "2051_2070"), ("ssp245", "2031_2050")]
DELTA_DOMAIN = (-0.15, 0.15)  # matches make_figures.py's fig_4_4 vis params


def _agreement_domain(image: "ee.Image", band: str, region) -> tuple[float, float]:
    """Same approach as make_figures.py's fig_4_5: agreement is ~1.0 almost everywhere,
    so pull the lower bound to the data's 2nd percentile to reveal contrast, falling
    back to 0.5 if the reduceRegion call fails."""
    try:
        stat = image.select(band).reduceRegion(
            reducer=ee.Reducer.percentile([2]), geometry=region, scale=1000,
            bestEffort=True, tileScale=TS, maxPixels=int(1e9),
        ).getInfo()
        p2 = stat.get(f"{band}_p2")
        if p2 is not None:
            return (min(math.floor(p2 * 100) / 100, 0.99), 1.0)
    except Exception as e:
        log(f"  !! agreement domain lookup failed ({e}), using 0.5 fallback")
    return (0.5, 1.0)


def build_future_rasters(only_band: str | None = None) -> None:
    project = utils.init()
    aid = lambda n: utils.asset_id(project, n)  # noqa: E731
    region = ee.FeatureCollection(aid("aoi")).geometry()

    jobs = []
    for ssp in CMIP6_SCENARIOS:
        for win in CMIP6_WINDOWS:
            delta_img = ee.Image(aid(f"delta_{ssp}_{win}"))
            for seg in CMIP6_DELTA_SEGMENTS:
                jobs.append({
                    "image": delta_img, "band": f"delta_{seg}", "palette": PAL_DIV,
                    "out_name": f"delta_{ssp}_{win}_{seg}", "categorical": False,
                    "domain": DELTA_DOMAIN,
                })

    for ssp, win in CMIP6_AGREEMENT_COMBOS:
        agree_img = ee.Image(aid(f"agreement_{ssp}_{win}"))
        band = "agreement_other_crops"
        domain = _agreement_domain(agree_img, band, region)
        jobs.append({
            "image": agree_img, "band": band, "palette": PAL_AGREEMENT,
            "out_name": f"agreement_{ssp}_{win}_other_crops", "categorical": False,
            "domain": domain,
        })

    _run_raster_jobs(jobs, region, only_band)


# =============================================================================
# 6c. Realized-use rasters: feat_realized's rl_role (categorical) + every
#     underused_<crop> band that actually exists on realized_vs_potential
# =============================================================================
def build_realized_rasters(only_band: str | None = None) -> None:
    project = utils.init()
    aid = lambda n: utils.asset_id(project, n)  # noqa: E731
    region = ee.FeatureCollection(aid("aoi")).geometry()
    realized = ee.Image(aid("feat_realized"))
    uu = ee.Image(aid("realized_vs_potential"))
    uu_bands = uu.bandNames().getInfo()  # discovered, not assumed (see module docstring)

    jobs = [{
        "image": realized, "band": "rl_role", "palette": PAL_ROLE,
        "out_name": "rl_role", "categorical": True,
    }]
    for band in uu_bands:
        jobs.append({
            "image": uu, "band": band, "palette": PAL_UNDERUSED,
            "out_name": band, "categorical": False,
        })

    _run_raster_jobs(jobs, region, only_band)


# =============================================================================
# 6d. Feature-theme hero rasters (v2 Feature Themes route): one representative
#     band per theme, domain from band_percentiles.json's P5/P95 (run
#     `--only band_percentiles` first). No PNG gallery for the remaining ~30
#     bands in this pass — deferred, see docs/dashboard_ux_plan.md §9 build log.
# =============================================================================
HERO_BANDS = {
    "climate": "clim_aridity",
    "terrain": "terr_slope",
    "soil": "soil_clay",
    "water": "water_dist",
    "phenology": "phen_amplitude",
    "access": "access_logtt",
    "siting": "sit_clearness",
    "conservation": "cv_pa_dist",
}


def build_theme_rasters(only_band: str | None = None) -> None:
    project = utils.init()
    region = ee.FeatureCollection(utils.asset_id(project, "aoi")).geometry()
    perc_path = DATA_DIR / "json" / "band_percentiles.json"
    if not perc_path.exists():
        raise SystemExit("run --only band_percentiles first (theme raster domains come from it)")
    percentiles = json.loads(perc_path.read_text())

    jobs = []
    for theme, band in HERO_BANDS.items():
        asset_name = features.THEME_ASSETS[theme]
        img = ee.Image(utils.asset_id(project, asset_name))
        p = percentiles.get(band, {})
        vmin, vmax = p.get("p5"), p.get("p95")
        if vmin is None or vmax is None or vmin >= vmax:
            log(f"  !! skipping {band}: bad percentile domain ({vmin}, {vmax})")
            continue
        jobs.append({
            "image": img, "band": band, "palette": PAL_SUIT,
            "out_name": f"feat_{band}", "categorical": False, "domain": (vmin, vmax),
        })

    _run_raster_jobs(jobs, region, only_band)


# =============================================================================
# 6e. Study Area & Feature Stack config-derived JSON (no GEE call)
# =============================================================================
def build_datasets_catalog() -> None:
    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)
    ds = utils.cfg()  # config/datasets.yaml

    rows = [
        {"theme": "Malha municipal", "source": "IBGE Malha Municipal Digital 2025",
         "id": ds["municipal_mesh"]["path"], "native_res": "vetorial", "period": "2025"},
        {"theme": "Clima", "source": "TerraClimate",
         "id": ds["climate"]["terraclimate"]["id"], "native_res": "~4,6 km",
         "period": "normal 1991-2020"},
        {"theme": "Relevo", "source": "SRTM GL1",
         "id": ds["terrain"]["srtm"], "native_res": "30 m", "period": "estático"},
        {"theme": "Solo", "source": "OpenLandMap",
         "id": ds["soil"]["layers"]["clay"]["id"], "native_res": "250 m", "period": "estático"},
        {"theme": "Água", "source": "JRC Global Surface Water",
         "id": ds["water"]["gsw"], "native_res": "30 m", "period": "1984-2021"},
        {"theme": "Fenologia", "source": "MODIS MOD13Q1 NDVI",
         "id": ds["phenology"]["modis"], "native_res": "250 m", "period": "2001-2020"},
        {"theme": "Acesso a mercados", "source": "Oxford MAP accessibility",
         "id": ds["access"]["oxford"], "native_res": "~1 km", "period": "2015"},
        {"theme": "Máscara de cobertura da terra", "source": "ESA WorldCover",
         "id": ds["landcover"]["worldcover"], "native_res": "10 m", "period": "2021"},
        {"theme": "Conservação (UCs)", "source": "Áreas protegidas WDPA",
         "id": ds["conservation"]["wdpa"], "native_res": "vetorial", "period": "atual"},
        {"theme": "Conservação (carbono)", "source": "Carbono de biomassa, Spawn et al. 2020",
         "id": ds["conservation"]["biomass"]["id"], "native_res": "300 m", "period": "2010"},
        {"theme": "Projeção climática CMIP6", "source": "NASA NEX-GDDP-CMIP6",
         "id": ds["cmip6"]["id"], "native_res": "~25 km",
         "period": "2031-2070 (2 SSP x 2 janelas)"},
        {"theme": "Uso realizado da terra", "source": "MapBiomas Coleção 10",
         "id": ds["mapbiomas"]["asset"], "native_res": "30 m", "period": "1985-2024"},
        {"theme": "Validação de produtividade", "source": "MODIS MOD17 NPP/GPP",
         "id": ds["productivity"]["npp"]["id"], "native_res": "500 m", "period": "2001-2020"},
    ]
    dest = out / "datasets_catalog.json"
    dest.write_text(json.dumps(rows, indent=2))
    log(f"wrote {dest} ({len(rows)} rows)")


def build_stack_composition() -> None:
    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)
    # Static — matches STACK_THEMES in src/features.py / CLAUDE.md's own 34-band breakdown.
    composition = {"climate": 14, "terrain": 6, "soil": 6, "water": 3, "phenology": 4, "access": 1}
    dest = out / "stack_composition.json"
    dest.write_text(json.dumps({
        "themes": composition,
        "total_bands": sum(composition.values()),
        "excluded": ["landcover"],
        "note": ("A cobertura da terra é deliberadamente excluída da pilha — apenas "
                 "máscara/contexto, nunca uma entrada de aptidão ou de agrupamento."),
    }, indent=2))
    log(f"wrote {dest}")


def build_band_percentiles() -> None:
    project = utils.init()
    aoi = utils.load_aoi(project)
    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)

    percentiles = [5, 25, 50, 75, 95]
    reducer = ee.Reducer.percentile(percentiles)
    payload = {}
    for theme, band in HERO_BANDS.items():
        asset_name = features.THEME_ASSETS[theme]
        img = ee.Image(utils.asset_id(project, asset_name)).select(band)
        stats = img.reduceRegion(
            reducer=reducer, geometry=aoi, scale=250, maxPixels=int(1e10),
            tileScale=TS, bestEffort=True,
        ).getInfo()
        payload[band] = {f"p{p}": stats.get(f"{band}_p{p}") for p in percentiles}

    dest = out / "band_percentiles.json"
    dest.write_text(json.dumps(payload, indent=2))
    log(f"wrote {dest} ({len(payload)} bands)")


# =============================================================================
# 6f. Validation scorecard — hand-transcribed from the thesis's already-published
# numbers (04_results.tex tab:presence-auc / tab:pot-real-gap / within-crop GPP /
# ANOVA / kappa paragraphs, 06_annex.tex tab:spearman-npp). Re-deriving via
# tools/run_validation.py would reproduce the same values (they already match) at
# the cost of a 10+ minute RF/stratified-sample rerun — not worth it here.
# =============================================================================
def build_validation_scorecard() -> None:
    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)

    scorecard = {
        "presence_auc_boyce": {
            "soybean": {"auc": 0.871, "boyce": 0.964},
            "sugarcane": {"auc": 0.821, "boyce": 0.769},
            "other_crops": {"auc": 0.698, "boyce": 0.792},
        },
        "spearman_npp": {
            "cattle": 0.52, "conservation": 0.46, "sugarcane": 0.45, "solar": 0.40,
            "soybean": 0.31, "other_crops": 0.11, "pisciculture": -0.32,
        },
        "spearman_npp_n_municipalities": 247,
        "spearman_npp_notes": {"other_crops": "n.s., p=0,09"},
        "within_crop_gpp_gradient": {
            "soybean": {"rho": 0.417, "n": 14646},
            "other_crops": {"rho": 0.370, "n": 12117},
            "sugarcane": {"rho": -0.085, "n": 6678},
        },
        "zone_anova": {"f": 2191.0, "p_approx": 0, "zone_mean_range": [0.47, 0.89]},
        "rf_kappa": {
            "soybean": 0.269,
            "n": 16160,
            "knowledge_area_pct": 52.8,
            "rf_area_pct": 21.6,
            "note": "Landis & Koch: concordância razoável, mas não forte",
        },
        "underuse_pct": {
            "other_crops": 57.3, "sugarcane": 51.6, "soybean": 41.8, "pisciculture": 9.4,
        },
        "source": "thesis/Chapters/04_results.tex + 06_annex.tex, referente ao rebuild de 2026-09",
    }
    dest = out / "validation_scorecard.json"
    dest.write_text(json.dumps(scorecard, indent=2))
    log(f"wrote {dest}")


STAGE_CHOICES = [
    "vectors", "config", "municipal", "diagnostics", "rasters", "future_rasters",
    "realized_rasters", "datasets_catalog", "stack_composition", "band_percentiles",
    "theme_rasters", "validation_scorecard", "home_stats",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only", choices=STAGE_CHOICES,
        help="run a single stage instead of all of them",
    )
    parser.add_argument(
        "--raster",
        help=(
            "with --only rasters/future_rasters/realized_rasters/theme_rasters, "
            "build a single named layer (e.g. suit_soybean, delta_ssp585_2051_2070_soybean)"
        ),
    )
    args = parser.parse_args()

    stages = {
        "vectors": build_vectors,
        "config": build_config_json,
        "municipal": build_municipal_ranking,
        "diagnostics": build_diagnostics,
        "rasters": lambda: build_rasters(args.raster),
        "future_rasters": lambda: build_future_rasters(args.raster),
        "realized_rasters": lambda: build_realized_rasters(args.raster),
        "datasets_catalog": build_datasets_catalog,
        "stack_composition": build_stack_composition,
        "band_percentiles": build_band_percentiles,
        "theme_rasters": lambda: build_theme_rasters(args.raster),
        "validation_scorecard": build_validation_scorecard,
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
