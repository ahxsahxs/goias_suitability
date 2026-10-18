"""Build static data assets for docs/dashboard/public/data/ (docs/dashboard_ux_plan.md §2).

v2 scope (2026-09-20): the pipeline rebuild that was in flight when v1 was built has
completed and is footprint-verified (tools/verify_assets.py). This script now pulls
the full asset set: feat_*, feature_stack_250m(_z), suit_present (7 suit_* + 7
class_* bands), suit_present_sens (7 sens_* bands), zones_present, the IBGE municipal
mesh (Part 12), suit_future_*/delta_* (Part 11, CMIP6), and
realized_vs_potential/feat_realized (Parts 12-13). The extended municipal ranking
below carries all 7 suit_*, zone, all 7 delta_* (off delta_ssp585_2051_2070 only —
not all 4 SSP/window combos), and every underused_<crop> band that actually exists
on realized_vs_potential (currently 4: soybean/sugarcane/other_crops/pisciculture —
cattle/conservation/solar have none by construction, see external.ROLE_CODES). This
is a separate file from thesis/Chapters/Figures/municipal_ranking.csv (produced by
tools/extract_present.py::municipal()) — this script never touches that file.

Delta raster coverage follows config: every segment in SEGMENTS x every
`cmip6.scenarios` x `cmip6.windows` in config/datasets.yaml. The dashboard learns
which layers exist from manifest.json (`delta_layers`, a scan of pmtiles/), never
from a list of its own. The dashboard no longer ships
agreement_* (GCM ensemble agreement) rasters — the territory-mean agreement is ~0.999
and near-uniform everywhere regardless of scenario/segment (see
thesis/Chapters/04_methodology.tex's concordância paragraph and fig:ensemble-agreement),
so the maps were non-informative and were dropped from the dashboard.

Zones: the count is read from zone_profiles.csv at run time, never hardcoded. The
zones_present raster is 0-based; every file this script writes is 1-based, like
zone_profiles.csv, the thesis and its figures (CLAUDE.md §11). The +1 is applied
exactly once, where a raster value is read (municipal ranking, PCA sample).

Words vs numbers: every NUMBER the dashboard shows comes from a file written here;
every human-readable LABEL comes from config/dashboard.yaml via manifest.json.
`--only offline` runs every stage that needs no Earth Engine compute.

Run:
  EE_PROJECT=<your-project> uv run python tools/build_dashboard_assets.py [--only <stage>]
  (see --help for the full --only stage list)
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
import features  # noqa: E402
import ibge_mesh  # noqa: E402
import utils  # noqa: E402
from palettes import (  # noqa: E402
    DELTA_DOMAIN,
    FAO_ORDER,
    PAL_DIV,
    PAL_FAO,
    PAL_ROLE,
    PAL_SUIT,
    PAL_UNDERUSED,
    SEGMENTS,
    ZONE_PAIR_MARGIN,
    zone_palette,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "docs" / "dashboard" / "public" / "data"
SCRATCH_DIR = REPO_ROOT / "docs" / "dashboard" / ".build-scratch"
CONFIG_DIR = REPO_ROOT / "config"

TS = 8  # tileScale — see CLAUDE.md §11 "validation is compute-heavy" gotcha
THESIS_DIR = utils.out_dir()   # where the pipeline wrote its CSVs

# The one SSP/window the municipal click-panel and the Home chip summarize (the
# thesis' worst case, §sec:shift / tab:municipal-rank). Exported in manifest.json so
# the dashboard never has to restate it.
MUNICIPAL_DELTA = ("ssp585", "2051_2070")


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
    delta = ee.Image(aid("delta_{}_{}".format(*MUNICIPAL_DELTA)))
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
    key = utils.cfg()["municipal_mesh"]["join_key"]
    props = [
        *([key] if key == "NM_MUN" else [key, "NM_MUN"]), "SIGLA_UF", "zone",
        *[f"suit_{s}" for s in SEGMENTS],
        *[f"delta_{s}" for s in SEGMENTS],
        *uu_bands,
    ]
    feats = means.select(props, None, False).getInfo()["features"]

    df = pd.DataFrame([f["properties"] for f in feats]).dropna(subset=[f"suit_{SEGMENTS[0]}"])
    # zones_present is 0-based; shift once to the 1-based ids every other file uses
    # (same rule as tools/extract_present.municipal, which the thesis counts come from).
    df["zone"] = df["zone"].round().astype(int) + 1

    out_csv = DATA_DIR / "csv" / "municipal_ranking.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(out_csv, index=False)
    log(f"wrote {out_csv} ({len(df)} municipalities)")

    m = utils.cfg()["municipal_mesh"]
    gdf = ibge_mesh._load_gdf()
    gdf = gdf.assign(geometry=gdf.geometry.simplify(m["simplify_tolerance_deg"], preserve_topology=True))
    merged = gdf.merge(df, on=key, how="inner", validate="one_to_one", suffixes=("", "_dup"))
    merged = merged.drop(columns=[c for c in merged.columns if c.endswith("_dup")])
    out_geojson = DATA_DIR / "geojson" / "municipal_ranking.geojson"
    merged.to_file(out_geojson, driver="GeoJSON")
    log(f"wrote {out_geojson} ({len(merged)} municipalities)")


# =============================================================================
# 4. Diagnostic CSV passthrough (already produced by tools/gen_diag_csvs.py / src/zoning.py)
# =============================================================================
DIAG_CSVS = {
    "zone_profiles.csv": THESIS_DIR / "zone_profiles.csv",
    "zoning_kselect.csv": THESIS_DIR / "zoning_kselect.csv",
    "factor_variance.csv": THESIS_DIR / "factor_variance.csv",
    # Part 9 weight derivation (tools/derive_weights.py): w_lit | d | w_final
    "ahp_weights.csv": THESIS_DIR / "ahp_weights.csv",
    "lambda_sweep.csv": THESIS_DIR / "lambda_sweep.csv",
    "factor_discrimination.csv": THESIS_DIR / "factor_discrimination.csv",
    # Zone AREA shares via pixelArea() (tools/extract_present.zone_shares). The ONLY
    # source for "how big is zone N": zone_profiles.csv's `n` is a stratified-sample
    # count, not an area share (CLAUDE.md §9).
    "zone_area.csv": THESIS_DIR / "zone_area.csv",
    # Part 9 discrimination / λ sensitivity (tools/anchor_breakpoints.py, derive_weights.py)
    "lambda_auc.csv": THESIS_DIR / "lambda_auc.csv",
    "factor_variance_theme.csv": THESIS_DIR / "factor_variance_theme.csv",
    # Part 11 summary tables (tools/extract_cmip6.py) -- tab:shift-mean, tab:shift-share,
    # tab:downgrade-share, tab:transition-othercrops, tab:zone-shift
    "cmip6_shift_mean.csv": THESIS_DIR / "cmip6_shift_mean.csv",
    "cmip6_shift_share.csv": THESIS_DIR / "cmip6_shift_share.csv",
    "cmip6_downgrade.csv": THESIS_DIR / "cmip6_downgrade.csv",
    "cmip6_transition_othercrops.csv": THESIS_DIR / "cmip6_transition_othercrops.csv",
    "cmip6_zone_shift.csv": THESIS_DIR / "cmip6_zone_shift.csv",
    # Parts 12-13 (tools/extract_present.py) -- tab:realized-composition, tab:pot-real-gap
    "realized_composition.csv": THESIS_DIR / "realized_composition.csv",
    "realized_gap.csv": THESIS_DIR / "realized_gap.csv",
}


def build_diagnostics() -> None:
    out = DATA_DIR / "csv"
    out.mkdir(parents=True, exist_ok=True)
    # A missing source used to be logged and skipped, which left the PREVIOUS copy in
    # public/data -- a stale table shipped with exit code 0 (CLAUDE.md §11). Refuse.
    missing = [str(src) for src in DIAG_CSVS.values() if not src.exists()]
    if missing:
        raise SystemExit("missing diagnostic sources:\n  " + "\n  ".join(missing))
    for name, src in DIAG_CSVS.items():
        shutil.copyfile(src, out / name)
        log(f"copied {src} -> {out / name}")


def zone_count() -> int:
    """Ground truth for how many zones actually exist — never hardcode this."""
    df = pd.read_csv(DIAG_CSVS["zone_profiles.csv"])
    return len(df)


def build_home_stats() -> None:
    """Small aggregate for the Home route's stat-chip strip — computed once here
    from files this script already writes (municipal_ranking.csv, zone_profiles.csv,
    validation_scorecard.json) plus thesis/Chapters/cmip6_shift_mean.csv, never
    recomputed client-side. No EE call. Run `--only validation_scorecard` and
    `--only municipal` before this stage (the full run already orders them)."""
    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)

    muni = pd.read_csv(DATA_DIR / "csv" / "municipal_ranking.csv")
    zones = pd.read_csv(DIAG_CSVS["zone_profiles.csv"])
    # The biggest zone and its share come from zone_area.csv (a pixelArea() group
    # reduce), NOT from zone_profiles.csv's `n`. `n` counts rows of a STRATIFIED
    # sample: using it reported zone 1 at 37.9% of the territory when its real area
    # share is 46.4% -- the exact error CLAUDE.md §9 flags, on the Home route of a
    # dashboard the thesis links to.
    area = pd.read_csv(DIAG_CSVS["zone_area.csv"])
    top_zone = area.loc[area["share_pct"].idxmax()]

    scorecard_path = out / "validation_scorecard.json"
    if not scorecard_path.exists():
        raise SystemExit("run --only validation_scorecard first")
    scorecard = json.loads(scorecard_path.read_text())

    # Worst projected change = most negative territory-mean ΔS over every segment x
    # scenario, read from the thesis' own table (tab:shift-mean) rather than a fresh,
    # bestEffort EE reduction that could disagree with it in the 3rd decimal.
    shift = pd.read_csv(THESIS_DIR / "cmip6_shift_mean.csv")
    worst = shift.loc[shift["delta_s"].idxmin()]

    stats = {
        "n_zones": len(zones),
        "n_segments": len(SEGMENTS),
        "n_municipalities": len(muni),
        "mean_suit_soybean": round(float(muni["suit_soybean"].mean()), 3),
        "top_zone": int(top_zone["zone"]),
        "top_zone_share_pct": round(float(top_zone["share_pct"]), 1),
        "kappa_soybean": scorecard.get("rf_kappa", {}).get("soybean"),
        "auc_soybean": scorecard.get("presence_auc_boyce", {}).get("soybean", {}).get("auc"),
        "boyce_soybean": scorecard.get("presence_auc_boyce", {}).get("soybean", {}).get("boyce"),
        "underused_soybean_pct": scorecard.get("underuse_pct", {}).get("soybean"),
        "worst_delta": {
            "segment": str(worst["segment"]), "ssp": str(worst["ssp"]),
            "window": str(worst["window"]), "delta_s": round(float(worst["delta_s"]), 4),
        },
    }
    dest = out / "home_stats.json"
    dest.write_text(json.dumps(stats, indent=2))
    log(f"wrote {dest}")


# =============================================================================
# 5. Sensitivity percentiles (reduceRegion, NOT a raster — used for a histogram)
# =============================================================================
def build_sensitivity_json() -> None:
    """P5..P95 of each `sens_<segment>` band -> json/sensitivity_<segment>.json, read by
    SuitabilityView. This stage was defined but missing from STAGE_CHOICES/`stages` until
    2026-10-07, so the shipped JSONs sat at their 2026-09-19 values through two
    recalibrations with nothing to flag it. Keep it wired."""
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
    already provably bounded there (suit_*, underused_*). For a band that is
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
# 6b. CMIP6 shift rasters: delta_<ssp>_<window>_<segment> (diverging)
# =============================================================================
def cmip6_scenarios() -> list[str]:
    return list(utils.cfg()["cmip6"]["scenarios"])


def cmip6_windows() -> list[str]:
    return list(utils.cfg()["cmip6"]["windows"])


def build_future_rasters(only_band: str | None = None) -> None:
    project = utils.init()
    aid = lambda n: utils.asset_id(project, n)  # noqa: E731
    region = ee.FeatureCollection(aid("aoi")).geometry()

    jobs = []
    for ssp in cmip6_scenarios():
        for win in cmip6_windows():
            delta_img = ee.Image(aid(f"delta_{ssp}_{win}"))
            for seg in SEGMENTS:
                jobs.append({
                    "image": delta_img, "band": f"delta_{seg}", "palette": PAL_DIV,
                    "out_name": f"delta_{ssp}_{win}_{seg}", "categorical": False,
                    "domain": DELTA_DOMAIN,
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
#     bands in this pass — deferred.
# =============================================================================
HERO_BANDS = {
    "climate": "clim_aridity",
    "terrain": "terr_slope",
    "soil": "soil_clay",
    "water": "water_dist",
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
    span = lambda a, b: f"{a}–{b}"  # noqa: E731  (en dash, as in the thesis)
    clim_start = ds["climate"]["terraclimate"]["period"][0][:4]
    clim_end = int(ds["climate"]["terraclimate"]["period"][1][:4]) - 1  # exclusive end
    wins = list(ds["cmip6"]["windows"].values())
    mb_years = ds["mapbiomas"]["years"]
    prod = ds["productivity"]["period"]

    rows = [
        {"theme": "Malha municipal", "source": "IBGE Malha Municipal Digital 2025",
         "id": ds["municipal_mesh"]["path"], "native_res": "vetorial",
         "period": str(utils.territory()["ibge_year"])},
        {"theme": "Clima", "source": "TerraClimate",
         "id": ds["climate"]["terraclimate"]["id"], "native_res": "~4,6 km",
         "period": f"normal climatológica {span(clim_start, clim_end)}"},
        {"theme": "Relevo", "source": "SRTM GL1",
         "id": ds["terrain"]["srtm"], "native_res": "30 m", "period": "estático"},
        {"theme": "Solo", "source": "OpenLandMap",
         "id": ds["soil"]["layers"]["clay"]["id"], "native_res": "250 m", "period": "estático"},
        {"theme": "Água", "source": "JRC Global Surface Water",
         "id": ds["water"]["gsw"], "native_res": "30 m", "period": "1984-2021"},
        # Part 7b. The mask comes from MapBiomas since T10 (2026-09), NOT from ESA
        # WorldCover: `features.landcover_features_mapbiomas` reads cfg()["mapbiomas"],
        # and the ESA builder survives only as a documented fallback. This row announced
        # the retired source until 2026-10-12. Two MapBiomas rows is correct, not a
        # duplicate -- the mask is built from ONE year, the realized-use analysis from
        # the series; the periods are what tell them apart.
        {"theme": "Máscara de cobertura da terra", "source": "MapBiomas coleção 10",
         "id": ds["mapbiomas"]["asset"], "native_res": "30 m",
         "period": str(ds["mapbiomas"]["current_year"])},
        {"theme": "Conservação (UCs)", "source": "Áreas protegidas WDPA",
         "id": ds["conservation"]["wdpa"], "native_res": "vetorial", "period": "atual"},
        {"theme": "Conservação (carbono)", "source": "Carbono de biomassa, Spawn et al. 2020",
         "id": ds["conservation"]["biomass"]["id"], "native_res": "300 m", "period": "2010"},
        {"theme": "Projeção climática CMIP6", "source": "NASA NEX-GDDP-CMIP6",
         "id": ds["cmip6"]["id"], "native_res": "~25 km",
         "period": (f"{span(wins[0][0], wins[-1][1])} ({len(ds['cmip6']['scenarios'])} SSP × "
                    f"{len(wins)} janelas; {len(ds['cmip6']['models'])} GCMs)")},
        {"theme": "Uso atual da terra", "source": "MapBiomas coleção 10",
         "id": ds["mapbiomas"]["asset"], "native_res": "30 m",
         "period": span(mb_years[0], mb_years[-1])},
        {"theme": "Contexto de produtividade", "source": "MODIS MOD17 NPP/GPP",
         "id": ds["productivity"]["npp"]["id"], "native_res": "500 m",
         "period": span(prod[0], prod[1])},
    ]
    dest = out / "datasets_catalog.json"
    dest.write_text(json.dumps(rows, indent=2))
    log(f"wrote {dest} ({len(rows)} rows)")


# Band-name prefix -> theme key (the same prefix rule as zoning._theme_of).
PREFIX_THEME = {"clim": "climate", "terr": "terrain", "soil": "soil", "water": "water"}


def build_stack_composition() -> None:
    """Per-theme band counts of the EXPORTED feature_stack_250m, read from its band
    names (metadata only -- works under restricted EE quota). Until 2026-10 this was a
    literal {14, 6, 6, 3}, i.e. a number that would not follow a theme change."""
    import zoning

    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)
    project = utils.init()
    bands = ee.Image(utils.asset_id(project, "feature_stack_250m")).bandNames().getInfo()
    composition = {t: 0 for t in features.STACK_THEMES}
    for b in bands:
        theme = PREFIX_THEME.get(b.split("_", 1)[0])
        if theme not in composition:
            raise SystemExit(f"stack band {b!r} has no theme in STACK_THEMES {features.STACK_THEMES}")
        composition[theme] += 1
    missing = sorted(set(zoning.ZONING_BANDS) - set(bands))
    if missing:
        raise SystemExit(f"ZONING_BANDS not in the exported stack: {missing}")
    dest = out / "stack_composition.json"
    dest.write_text(json.dumps({
        "themes": composition,
        "total_bands": len(bands),
        "bands": bands,
        "zoning_bands": list(zoning.ZONING_BANDS),
        "excluded": ["landcover"],
        "note": ("A cobertura da terra é deliberadamente excluída do conjunto: serve apenas "
                 "de máscara e contexto, nunca de entrada da aptidão ou do agrupamento."),
    }, indent=2, ensure_ascii=False))
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
# 6f. Validation scorecard — DERIVED from tools/run_validation.py's output, on the
# HELD-OUT half (`half == "val"`), which is the column the thesis quotes.
#
# This used to be a hand-transcribed literal dict, on the argument that re-deriving
# it "would reproduce the same values". That stopped being true the moment the
# weights were re-derived, and because no tool wrote to it, nothing detected the
# drift: it shipped 2026-09 numbers (soybean AUC 0,871) through the 2026-10 rebuild
# while build_home_stats() read them for the Home route's stat chips. It now reads
# the CSVs, so it cannot silently go stale again, and it refuses rather than
# falling back when they predate the spatial holdout (CLAUDE.md §11).
# =============================================================================
SCORECARD_HALF = "val"


def _scorecard_metrics() -> "pd.DataFrame":
    src = THESIS_DIR / "validation_metrics.csv"
    if not src.exists():
        raise SystemExit(f"missing {src}\nRe-run: EE_PROJECT=<your-project> uv run "
                         f"python tools/run_validation.py")
    df = pd.read_csv(src)
    if "half" not in df.columns:
        raise SystemExit(
            f"{src} has no `half` column, so it predates the spatial holdout and every "
            f"value in it is in-sample.\nRe-run: EE_PROJECT=<your-project> uv run python "
            f"tools/run_validation.py")
    return df


def _underuse_pct() -> dict:
    """{segment: share_pct} from thesis/Chapters/realized_gap.csv, rounded as the
    dashboard displays it. Refuses rather than falling back, so a missing CSV is a
    loud failure instead of a silently stale scorecard."""
    src = THESIS_DIR / "realized_gap.csv"
    if not src.exists():
        raise SystemExit(
            f"{src} is missing, so the under-utilization shares have no source.\n"
            f"Re-run: EE_PROJECT=<your-project> uv run python tools/extract_present.py")
    df = pd.read_csv(src)
    return {r.segment: round(float(r.share_pct), 1) for r in df.itertuples()}


def build_validation_scorecard() -> None:
    out = DATA_DIR / "json"
    out.mkdir(parents=True, exist_ok=True)

    df = _scorecard_metrics()
    v = df[df.half == SCORECARD_HALF]
    if v.empty:
        raise SystemExit(f"no rows with half={SCORECARD_HALF!r} in validation_metrics.csv")

    def pick(metric: str) -> dict:
        s = v[v.metric == metric]
        return {r.segment: float(r.value) for r in s.itertuples()}

    def n_of(metric: str, segment: str) -> int:
        s = v[(v.metric == metric) & (v.segment == segment)]
        return int(s.n.iloc[0]) if len(s) else 0

    auc, boyce = pick("auc"), pick("boyce")
    rho_npp, gpp = pick("spearman_mod17"), pick("within_crop_gpp_rho")
    kappa = pick("cohen_kappa_rf")

    anova_src = THESIS_DIR / "validation_zone_anova.csv"
    an = pd.read_csv(anova_src)
    if "half" not in an.columns:
        raise SystemExit(f"{anova_src} has no `half` column; re-run tools/run_validation.py")
    an = an[an.half == SCORECARD_HALF]

    p_npp = {r.segment: float(r.p) for r in v[v.metric == "spearman_mod17"].itertuples()}
    notes = {seg: f"n.s., p={p:.2f}".replace(".", ",")
             for seg, p in p_npp.items() if p >= 0.05}

    def presences(segment: str) -> int | None:
        s = v[(v.metric == "auc") & (v.segment == segment)]
        extra = str(s.extra.iloc[0]) if len(s) else ""
        return int(extra.split("=", 1)[1]) if extra.startswith("presences=") else None

    scorecard = {
        "half": SCORECARD_HALF,
        "presence_auc_boyce": {
            seg: {"auc": round(auc[seg], 4), "boyce": round(boyce[seg], 4),
                  "n": n_of("auc", seg), "presences": presences(seg)}
            for seg in auc
        },
        "spearman_npp": {seg: round(r, 4) for seg, r in rho_npp.items()},
        "spearman_npp_p": {seg: p for seg, p in p_npp.items()},
        "spearman_npp_n_municipalities": n_of("spearman_mod17", "soybean"),
        "spearman_npp_notes": notes,
        "within_crop_gpp_gradient": {
            seg: {"rho": round(r, 4), "n": n_of("within_crop_gpp_rho", seg)}
            for seg, r in gpp.items()
        },
        "zone_anova": {
            "f": round(float(an.F.iloc[0]), 1),
            "p_approx": float(an.p.iloc[0]),
            "zone_mean_range": [round(float(an.mean_npp.min()), 3),
                                round(float(an.mean_npp.max()), 3)],
            # zone ids are 1-based in validation_zone_anova.csv (extract tools shift once)
            # full precision: the dashboard rounds once for display (rounding here to 4
            # places and again to 3 gave 0,836 where the thesis prints 0,835)
            "zones": [{"zone": int(r.zone), "mean_npp": float(r.mean_npp), "n": int(r.n)}
                      for r in an.sort_values("zone").itertuples()],
        },
        "rf_kappa": {
            "soybean": round(kappa.get("soybean", float("nan")), 4),
            "n": n_of("cohen_kappa_rf", "soybean"),
            "knowledge_area_pct": round(100 * pick("kb_s2plus_share")["soybean"], 1),
            "rf_area_pct": round(100 * pick("rf_highprob_share")["soybean"], 1),
            "note": "concordância razoável, e não forte, na escala de Landis e Koch",
        },
        # From realized_gap.csv (extract_present.under_util), which that block started
        # writing on 2026-10-07. Until then it only printed, so these four numbers were
        # hand-transcribed here and shipped 2026-09 values through two recalibrations.
        "underuse_pct": _underuse_pct(),
        "source": (f"thesis/Chapters/validation_metrics.csv + validation_zone_anova.csv "
                   f"+ realized_gap.csv (half={SCORECARD_HALF})"),
    }
    dest = out / "validation_scorecard.json"
    dest.write_text(json.dumps(scorecard, indent=2, ensure_ascii=False))
    log(f"wrote {dest}  (half={SCORECARD_HALF})")


# =============================================================================
# 6g. Feature Stack PCA comparison — naive full z-stack vs the curated,
# theme-weighted 13-band ZONING_BANDS space that Part 10 actually clusters on
# (src/zoning.py). Same stratified sample + seed as the Part-10 zoning, so the 13-band
# PCA is the zoning's own decorrelated space (fit_pca's var_keep only truncates it).
# =============================================================================
PCA_N_POINTS = 3000         # scatter subsample shipped to the browser
PCA_COLOR_BANDS = ["terr_elev", "clim_aridity", "soil_clay"]


def _build_rgb_raster(image: "ee.Image", bands: list[str], domains: list[tuple[float, float]],
                      region, out_name: str) -> None:
    """RGB PMTiles from 3 continuous bands (R, G, B), each stretched to its own domain.

    Bands are downloaded one at a time — a single 3-band uint8 GeoTIFF of GO+DF at 250 m
    exceeds getDownloadURL's 48 MiB cap (see the NODATA_SENTINEL comment)."""
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = DATA_DIR / "pmtiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{out_name}.pmtiles"

    channels, mask, profile = [], None, None
    for band, (vmin, vmax) in zip(bands, domains):
        raw = SCRATCH_DIR / f"{out_name}_{band}_raw.tif"
        log(f"  downloading {band} (domain {vmin:.3f}..{vmax:.3f}) ...")
        _download_band(_prep_band(image, band, False, vmin, vmax), region, raw)
        with rasterio.open(raw) as src:
            arr = src.read(1)
            profile = src.profile
        band_mask = arr == NODATA_SENTINEL
        mask = band_mask if mask is None else (mask | band_mask)
        channels.append(np.clip(arr.astype("float64") / CONTINUOUS_STEPS * 255, 0, 255).astype("uint8"))

    rgba = SCRATCH_DIR / f"{out_name}_rgba.tif"
    merc = SCRATCH_DIR / f"{out_name}_merc.tif"
    alpha = np.where(mask, 0, 255).astype("uint8")
    profile.update(count=4, dtype="uint8", nodata=None, compress="deflate")
    with rasterio.open(rgba, "w", **profile) as dst:
        for i, ch in enumerate([*channels, alpha]):
            dst.write(ch, i + 1)
    _reproject_webmercator(rgba, merc)
    if out_path.exists():
        out_path.unlink()
    _to_pmtiles(merc, out_path)
    log(f"  wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")


def build_pca_compare(only_band: str | None = None) -> None:
    from types import SimpleNamespace

    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score

    import zoning

    project = utils.init()
    aid = lambda n: utils.asset_id(project, n)  # noqa: E731
    region = ee.FeatureCollection(aid("aoi")).geometry()
    z = ee.Image(aid("feature_stack_250m_z"))
    stack = ee.Image(aid("feature_stack_250m"))
    suit = ee.Image(aid("suit_present"))
    zones = ee.Image(aid("zones_present")).select([0]).rename("zone")
    bands_full = z.bandNames().getInfo()
    bands_curated = list(zoning.ZONING_BANDS)
    log(f"  sampling {len(bands_full)}-band z-stack (stratified, seed=42) ...")

    extra = zones.addBands(ee.Image.pixelLonLat())
    sample = zoning.build_sample(z, stack, suit, region, bands_full, segments=SEGMENTS,
                                 seed=42, tile_scale=TS, extra=extra)
    df = zoning.fc_to_df(sample).dropna().reset_index(drop=True)
    log(f"  sample: {len(df)} points")

    # Keys are SEMANTIC ("full"/"curated"), never band counts: they name the raster
    # files and the JSON contract the dashboard reads. The old "34"/"15" keys drifted
    # the moment the stack went 34 -> 29 and ZONING_BANDS 15 -> 13, which blanks the
    # page instead of failing loudly. The counts live only in each variant's `bands`.
    variants = {
        "full": (bands_full, [1.0] * len(bands_full),
                 zoning.cluster_matrix(df, bands_full, theme_weighted=False)),
        "curated": (bands_curated, zoning.theme_weight_vector(bands_curated),
                    zoning.cluster_matrix(df, bands_curated)),
    }
    payload: dict = {"variants": {}, "n_sample": int(len(df))}
    scores: dict[str, np.ndarray] = {}
    for key, (bands, weights, X) in variants.items():
        pca = PCA(svd_solver="full", random_state=42).fit(X)
        S = pca.transform(X)[:, :3]
        scores[key] = S
        evr = pca.explained_variance_ratio_
        n90 = int(np.searchsorted(np.cumsum(evr), pca_var_keep()) + 1)
        domain = [(float(np.percentile(S[:, j], 2)), float(np.percentile(S[:, j], 98))) for j in range(3)]
        log(f"  PCA-{key}: PC1-3 = {evr[:3].round(3).tolist()}; {n90} PCs reach 90%")
        payload["variants"][key] = {
            "bands": bands,
            "themes": [zoning._theme_of(b) for b in bands],
            "weights": [round(float(w), 4) for w in weights],
            "explained_variance_ratio": [round(float(v), 5) for v in evr],
            "n_pc_90": n90,
            "loadings": [[round(float(pca.components_[j, i]), 4) for j in range(3)] for i in range(len(bands))],
            "pc_domain": [[round(lo, 4), round(hi, 4)] for lo, hi in domain],
        }

        out_name = f"pca_rgb_{key}"
        if only_band and only_band != out_name:
            continue
        pca3 = SimpleNamespace(components_=pca.components_[:3], mean_=pca.mean_)
        pc_img = zoning.pca_project_image(z, bands, weights, pca3)
        _build_rgb_raster(pc_img, zoning.pc_names(pca3), domain, region, out_name)

    rng = np.random.default_rng(42)
    idx = np.sort(rng.choice(len(df), size=min(PCA_N_POINTS, len(df)), replace=False))
    r3 = lambda a: [round(float(v), 3) for v in a]  # noqa: E731
    payload["points"] = {
        "pc_full": [r3(scores["full"][i]) for i in idx],
        "pc_curated": [r3(scores["curated"][i]) for i in idx],
        # zones_present is 0-based; 1-based here like zone_profiles.csv (module docstring)
        "zone": [int(df["zone"].iloc[i]) + 1 for i in idx],
        "lon": r3(df["longitude"].iloc[idx]),
        "lat": r3(df["latitude"].iloc[idx]),
        **{b: r3(df[b].iloc[idx]) for b in PCA_COLOR_BANDS},
    }
    # How well the actual zones_present labels separate in each space's first 3 PCs
    # (the dimensions the page plots), on the same shipped subsample.
    for key in variants:
        sil = silhouette_score(scores[key][idx], df["zone"].iloc[idx].to_numpy())
        payload["variants"][key]["zone_silhouette_pc3"] = round(float(sil), 3)
        log(f"  PCA-{key}: zone silhouette on PC1-3 = {sil:.3f}")

    dest = DATA_DIR / "json" / "pca_compare.json"
    dest.write_text(json.dumps(payload, separators=(",", ":")))
    log(f"wrote {dest} ({dest.stat().st_size / 1024:.0f} KB)")
    shutil.rmtree(SCRATCH_DIR, ignore_errors=True)


# =============================================================================
# 7. manifest.json — every count, list, domain and label the dashboard would
# otherwise have to hardcode. Offline (no EE). Refuses to write when the words in
# config/dashboard.yaml drift from the thesis or from the data they label.
# =============================================================================
AOI_EQUAL_AREA_CRS = "+proj=aea +lat_0=-32 +lon_0=-60 +lat_1=-5 +lat_2=-42 +datum=WGS84 +units=m"  # Albers, South America


def pca_var_keep() -> float:
    """The variance share the zoning PCA retains -- zoning.fit_pca's own default, so
    the dashboard's "n PCs for X%" can never quote a threshold the zoning does not use."""
    import inspect

    import zoning
    return float(inspect.signature(zoning.fit_pca).parameters["var_keep"].default)


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _labels() -> dict:
    with open(CONFIG_DIR / "dashboard.yaml") as fh:
        lab = yaml.safe_load(fh)
    # Segment names must be the thesis' own (tools/gen_thesis_tables.SEG_PT/SEG_SHORT).
    import gen_thesis_tables as gtt
    if list(lab["segments"]) != list(SEGMENTS):
        raise SystemExit(f"config/dashboard.yaml segments {list(lab['segments'])} != {SEGMENTS}")
    for k, v in lab["segments"].items():
        if v["label"] != gtt.SEG_PT[k] or v["short"] != gtt.SEG_SHORT[k]:
            raise SystemExit(f"config/dashboard.yaml segment {k!r} != gen_thesis_tables "
                             f"({gtt.SEG_PT[k]!r}/{gtt.SEG_SHORT[k]!r})")
    codes = {0, *external.ROLE_CODES.values()}
    if set(lab["roles"]) != codes:
        raise SystemExit(f"config/dashboard.yaml roles {sorted(lab['roles'])} != ROLE_CODES {sorted(codes)}")
    return lab


def _zones(lab: dict) -> list[dict]:
    prof = pd.read_csv(DIAG_CSVS["zone_profiles.csv"]).sort_values("zone")
    area = pd.read_csv(DIAG_CSVS["zone_area.csv"]).set_index("zone")
    k = len(prof)
    names = {int(z): n for z, n in lab["zones"].items()}
    if sorted(names) != list(range(1, k + 1)) or sorted(prof["zone"]) != list(range(1, k + 1)):
        raise SystemExit(
            f"config/dashboard.yaml has zone descriptors {sorted(names)} but zone_profiles.csv "
            f"has K={k} (zones {sorted(prof['zone'])}). The zoning moved: re-read the zone "
            f"means (tab:zone-means) and rewrite the descriptors before publishing.")
    out = []
    for r in prof.itertuples():
        z = int(r.zone)
        out.append({
            "zone": z,
            "name": names[z],
            "comparative_segment": r.comparative_segment,
            "comparative_segment_2": r.comparative_segment_2,
            "comparative_margin": round(float(r.comparative_margin), 3),
            "paired": bool(r.comparative_margin < ZONE_PAIR_MARGIN),
            "area_km2": round(float(area.loc[z, "area_km2"]), 0),
            "share_pct": round(float(area.loc[z, "share_pct"]), 1),
            "mean_elev_m": round(float(r.terr_elev), 0),
        })
    elev = [z["mean_elev_m"] for z in out]
    if elev != sorted(elev, reverse=True):
        raise SystemExit(f"zone_profiles.csv is not in canonical order (descending terr_elev): {elev}")
    return out


def _delta_layers() -> dict:
    """{ssp: {window: [segments with a shipped delta PMTiles]}} -- scanned, not assumed,
    so a layer that failed to export is absent from the selector instead of a blank map."""
    pm = DATA_DIR / "pmtiles"
    return {
        ssp: {win: [seg for seg in SEGMENTS if (pm / f"delta_{ssp}_{win}_{seg}.pmtiles").exists()]
              for win in cmip6_windows()}
        for ssp in cmip6_scenarios()
    }


def build_manifest() -> None:
    import zoning

    lab = _labels()
    ds = utils.cfg()
    seg_cfg = yaml.safe_load((CONFIG_DIR / "segments.yaml").read_text())

    stack_path = DATA_DIR / "json" / "stack_composition.json"
    if not stack_path.exists():
        raise SystemExit("run --only stack_composition first (needs EE metadata only)")
    stack = json.loads(stack_path.read_text())

    # Every band/factor the dashboard can name must have a label.
    factors = {f for s in seg_cfg["segments"].values() for f in s["factors"]}
    unlabeled = sorted((set(stack["bands"]) | factors) - set(lab["bands"]))
    if unlabeled:
        raise SystemExit(f"config/dashboard.yaml `bands` lacks labels for {unlabeled}")

    gdf = ibge_mesh._load_gdf()
    aoi_km2 = float(gdf.to_crs(AOI_EQUAL_AREA_CRS).union_all().area / 1e6)
    uf_col = ds["municipal_mesh"]["uf_col"]
    by_uf = gdf[uf_col].value_counts().to_dict() if uf_col in gdf.columns else {}

    clim = ds["climate"]["terraclimate"]["period"]
    manifest = {
        "generated_at": time.strftime("%Y-%m-%d"),
        "git_sha": _git_sha(),
        "segments": [{"key": k, **v} for k, v in lab["segments"].items()],
        "zones": _zones(lab),
        "zone_pair_margin": ZONE_PAIR_MARGIN,
        "roles": {int(k): v for k, v in lab["roles"].items()},
        "realized_bands": lab["realized_bands"],
        "fao_classes": [
            {"code": c, "label": lab["fao_classes"][c]} for c in FAO_ORDER
        ],
        "fao_breaks": seg_cfg["fao_classes"]["breaks"],
        "ssps": [{"key": k, "label": lab["ssps"][k]} for k in cmip6_scenarios()],
        "windows": [{"key": k, "start": int(v[0]), "end": int(v[1])}
                    for k, v in ds["cmip6"]["windows"].items()],
        "gcms": list(ds["cmip6"]["models"]),
        "baseline": {"start": int(clim[0][:4]), "end": int(clim[1][:4]) - 1},
        "municipal_delta": {"ssp": MUNICIPAL_DELTA[0], "window": MUNICIPAL_DELTA[1]},
        "delta_layers": _delta_layers(),
        "delta_domain": list(DELTA_DOMAIN),
        "aoi": {"area_km2": round(aoi_km2, 0), "n_municipalities": int(len(gdf)),
                "municipalities_by_uf": by_uf},
        "grid_m": int(utils.scale_m()),
        "stack": {"total_bands": stack["total_bands"], "themes": stack["themes"],
                  "n_zoning_bands": len(zoning.ZONING_BANDS), "pca_var_keep": pca_var_keep()},
        # one representative band per theme (feat_<band>.pmtiles); `stacked` = the
        # theme is in features.STACK_THEMES (siting/conservation are side images)
        "hero_bands": [{"theme": t, "band": b, "stacked": t in features.STACK_THEMES}
                       for t, b in HERO_BANDS.items()],
        "themes": lab["themes"],
        "anchor_rules": lab["anchor_rules"],
        "membership_types": lab["membership_types"],
        "bands": lab["bands"],
    }
    dest = DATA_DIR / "json" / "manifest.json"
    dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    log(f"wrote {dest}")


# Stages that need no Earth Engine COMPUTE (stack_composition reads band names only,
# which still works when the project is in restricted-quota mode).
OFFLINE_STAGES = ["config", "diagnostics", "datasets_catalog", "stack_composition",
                  "validation_scorecard", "home_stats", "manifest"]

STAGE_CHOICES = [
    "vectors", "config", "municipal", "diagnostics", "sensitivity", "rasters",
    "future_rasters", "realized_rasters", "datasets_catalog", "stack_composition",
    "band_percentiles", "theme_rasters", "validation_scorecard", "home_stats",
    "pca_compare", "manifest", "offline",
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
            "with --only rasters/future_rasters/realized_rasters/theme_rasters/pca_compare, "
            "build a single named layer (e.g. suit_soybean, delta_ssp585_2051_2070_soybean)"
        ),
    )
    args = parser.parse_args()

    stages = {
        "vectors": build_vectors,
        "config": build_config_json,
        "municipal": build_municipal_ranking,
        "diagnostics": build_diagnostics,
        "sensitivity": build_sensitivity_json,
        "rasters": lambda: build_rasters(args.raster),
        "future_rasters": lambda: build_future_rasters(args.raster),
        "realized_rasters": lambda: build_realized_rasters(args.raster),
        "datasets_catalog": build_datasets_catalog,
        "stack_composition": build_stack_composition,
        "band_percentiles": build_band_percentiles,
        "theme_rasters": lambda: build_theme_rasters(args.raster),
        "validation_scorecard": build_validation_scorecard,
        "home_stats": build_home_stats,
        "pca_compare": lambda: build_pca_compare(args.raster),
        "manifest": build_manifest,  # last: scans the pmtiles the raster stages wrote
    }

    if args.only == "offline":
        for name in OFFLINE_STAGES:
            log(f"=== {name} ===")
            stages[name]()
        return
    if args.only:
        stages[args.only]()
        return

    for name, fn in stages.items():
        log(f"=== {name} ===")
        fn()
    log("=== done ===")


if __name__ == "__main__":
    main()
