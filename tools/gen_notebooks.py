"""Generate notebooks/01..08 (Phase-A Parts 1-8) from a single spec.

Run:  python tools/gen_notebooks.py
The notebooks are thin: they import src/ and call the feature builders, so the
analysis logic lives in src/features.py (one source of truth).
"""
import sys
from pathlib import Path

import nbformat as nbf

NB_DIR = Path(__file__).resolve().parent.parent / "notebooks"
NB_DIR.mkdir(exist_ok=True)

# Optional filter: `python tools/gen_notebooks.py 09_suitability_fuzzy_ahp.ipynb`
# regenerates only the named notebook(s); no args = regenerate all. Lets us add a
# new Part without clobbering the executed outputs saved in earlier notebooks.
ONLY = set(sys.argv[1:])

INIT = (
    "import sys, os\n"
    "sys.path.insert(0, os.path.abspath('../src'))\n"
    "import ee, geemap\n"
    "import utils, features\n"
    "project = utils.init()\n"
    "print('EE initialized; project =', project)"
)

LOAD_AOI = (
    "aoi = utils.load_aoi(project)\n"
    "print('AOI area (km^2):', round(aoi.area(1000).divide(1e6).getInfo(), 1))"
)


def md(text):
    return nbf.v4.new_markdown_cell(text)


def code(text):
    return nbf.v4.new_code_cell(text)


def write(name, cells):
    if ONLY and name not in ONLY:
        return
    nb = nbf.v4.new_notebook()
    nb.cells = cells
    nb.metadata = {
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
    }
    nbf.write(nb, NB_DIR / name)
    print("wrote", name)


# ---------------------------------------------------------------- Part 1
write(
    "01_setup_aoi.ipynb",
    [
        md(
            "# Part 1 — Project & AOI setup\n\n"
            "**Output:** `aoi` (table asset). **DoD:** AOI renders over Goiás+DF; "
            "`config/datasets.yaml` pinned and verified against the live catalog."
        ),
        code(INIT),
        md("### Build the AOI (IBGE malha municipal: Goiás + Distrito Federal)"),
        code(
            "aoi_fc = features.aoi_fc()\n"
            "print('states:', aoi_fc.aggregate_array('NM_UF').distinct().getInfo())\n"
            "aoi = features.aoi_geometry()\n"
            "print('AOI area (km^2):', round(aoi.area(1000).divide(1e6).getInfo(), 1))"
        ),
        code(
            "Map = geemap.Map()\n"
            "Map.centerObject(aoi, 7)\n"
            "Map.addLayer(aoi_fc, {'color': 'red'}, 'AOI (GO+DF)')\n"
            "Map"
        ),
        md(
            "### Verify-at-build — confirm every pinned dataset ID / band exists\n"
            "Print actual band names so `datasets.yaml` (esp. `VERIFY`-tagged soil scales) "
            "can be corrected before downstream parts run."
        ),
        code(
            "ds = utils.cfg()\n"
            "checks = {\n"
            "    'TerraClimate': ee.ImageCollection(ds['climate']['terraclimate']['id']).first(),\n"
            "    'SRTM': ee.Image(ds['terrain']['srtm']),\n"
            "    'HydroSHEDS_ACC': ee.Image(ds['terrain']['hydrosheds_acc']),\n"
            "    'GSW': ee.Image(ds['water']['gsw']),\n"
            "    'MODIS': ee.ImageCollection(ds['phenology']['modis']).first(),\n"
            "    'Oxford': ee.Image(ds['access']['oxford']),\n"
            "    'WorldCover': ee.ImageCollection(ds['landcover']['worldcover']).first(),\n"
            "}\n"
            "for k, v in checks.items():\n"
            "    print(f'{k:16s}', v.bandNames().getInfo())\n"
            "for key, spec in ds['soil']['layers'].items():\n"
            "    print(f'soil.{key:5s}', ee.Image(spec['id']).bandNames().getInfo())"
        ),
        md("### Export the AOI as an EE asset"),
        code(
            "utils.ensure_folder(project)\n"
            "task = utils.export_table(features.aoi_dissolved_fc(), project, 'aoi')\n"
            "print('export', task.status()['description'], '->', task.status()['state'])"
        ),
    ],
)

# ---------------------------------------------------------------- Parts 2-7b
FEATURE_SPECS = [
    dict(
        nb="02_features_climate.ipynb", part="2", title="Climate & water-balance features",
        builder="climate_features", asset="feat_climate",
        source="`IDAHO_EPSCOR/TERRACLIMATE` monthly climatology, 1991–2020",
        dod="band ranges sane (e.g. annual precip ~800–2000 mm; aridity 0–2).",
        viz="clim_pr_annual", vis="{'min': 800, 'max': 2000, 'palette': ['red','yellow','blue']}",
    ),
    dict(
        nb="03_features_terrain.ipynb", part="3", title="Terrain features",
        builder="terrain_features", asset="feat_terrain",
        source="`USGS/SRTMGL1_003` + `WWF/HydroSHEDS/15ACC`",
        dod="slope 0–~45°, no NaN holes.",
        viz="terr_slope", vis="{'min': 0, 'max': 20, 'palette': ['green','yellow','red']}",
    ),
    dict(
        nb="04_features_soil.ipynb", part="4", title="Soil features",
        builder="soil_features", asset="feat_soil",
        source="`OpenLandMap/SOL/...` 0–30 cm mean",
        dod="clay+sand plausible; pH ~4–7 typical Cerrado.",
        viz="soil_ph", vis="{'min': 4, 'max': 7, 'palette': ['red','white','blue']}",
    ),
    dict(
        nb="05_features_water.ipynb", part="5", title="Hydrology & water-access features",
        builder="water_features", asset="feat_water",
        source="`JRC/GSW1_4/GlobalSurfaceWater` + `WWF/HydroSHEDS/15ACC`",
        dod="distance raster continuous; reservoirs present.",
        viz="water_dist", vis="{'min': 0, 'max': 20000, 'palette': ['blue','white','brown']}",
    ),
    dict(
        nb="06_features_phenology.ipynb", part="6", title="Vegetation phenology features",
        builder="phenology_features", asset="feat_phenology",
        source="`MODIS/061/MOD13Q1` NDVI, harmonic fit 2001–2020",
        dod="amplitude high in croplands, low in dense native veg.",
        viz="phen_amplitude", vis="{'min': 0, 'max': 0.4, 'palette': ['white','green']}",
    ),
    dict(
        nb="07_features_access.ipynb", part="7", title="Market-access feature",
        builder="access_features", asset="feat_access",
        source="`Oxford/MAP/accessibility_to_cities_2015_v1_0`",
        dod="low near cities, high in remote NE Goiás.",
        viz="access_logtt", vis="{'min': 0, 'max': 7, 'palette': ['green','yellow','red']}",
    ),
    dict(
        nb="07b_landcover_mask.ipynb", part="7b", title="Generic land-cover mask (ESA WorldCover)",
        builder="landcover_features", asset="feat_landcover",
        source="`ESA/WorldCover/v200` (10 m, 2021), aggregated to 250 m",
        dod="built-up around Goiânia/Brasília and major reservoirs excluded.",
        viz="mask_excluded", vis="{'min': 0, 'max': 1, 'palette': ['white','black']}",
    ),
    dict(
        nb="07c_siting.ipynb", part="7c", title="Siting features (solar/pisci; NOT stacked)",
        builder="siting_features", asset="feat_siting",
        source="TerraClimate srad / FAO-56 extraterrestrial Ra (clearness) + `JRC/GSW1_4` seasonal water",
        dod="clearness ~0.45-0.55; seasonal-water distance far below permanent-water distance. "
            "Consumed by solar/pisci membership via `sit_` routing; deliberately NOT in the stack.",
        viz="sit_clearness", vis="{'min': 0.45, 'max': 0.52, 'palette': ['white','orange']}",
    ),
    dict(
        nb="07d_conservation.ipynb", part="7d", title="Conservation-value features (NOT stacked)",
        builder="conservation_features", asset="feat_conservation",
        source="`WCMC/WDPA` reserve distance + SRTM ruggedness + `NASA/ORNL/biomass_carbon_density`",
        dod="cv_pa_dist 0 inside reserves; cv_ruggedness ~m-scale; cv_carbon Mg C/ha. "
            "Consumed by conservation membership via `cv_` routing; deliberately NOT in the stack.",
        viz="cv_carbon", vis="{'min': 0, 'max': 60, 'palette': ['white','darkgreen']}",
    ),
]

for s in FEATURE_SPECS:
    write(
        s["nb"],
        [
            md(
                f"# Part {s['part']} — {s['title']}\n\n"
                f"**Source:** {s['source']}\n\n"
                f"**Output:** `{s['asset']}` (250 m). **DoD:** {s['dod']}"
            ),
            code(INIT),
            code(LOAD_AOI),
            md("### Build the feature image"),
            code(
                f"img = features.{s['builder']}(aoi)\n"
                "print('bands:', img.bandNames().getInfo())"
            ),
            md("### DoD sanity — per-band min/mean/max"),
            code("utils.range_report(img, aoi)"),
            md("### Quick look"),
            code(
                "Map = geemap.Map()\n"
                "Map.centerObject(aoi, 7)\n"
                f"Map.addLayer(img.select('{s['viz']}'), {s['vis']}, '{s['viz']}')\n"
                "Map.addLayer(aoi, {}, 'AOI', False)\n"
                "Map"
            ),
            md("### Export to EE asset"),
            code(
                "utils.ensure_folder(project)\n"
                f"task = utils.export_image(img, project, '{s['asset']}', aoi)\n"
                "print('export', task.status()['description'], '->', task.status()['state'])"
            ),
        ],
    )

# ---------------------------------------------------------------- Part 8
write(
    "08_feature_stack.ipynb",
    [
        md(
            "# Part 8 — Feature-stack assembly (250 m)\n\n"
            "Concatenate the continuous themes (climate, terrain, soil, water, phenology, "
            "access) into one multiband image; build a **raw** stack (for fuzzy suitability) "
            "and a **z-scored** stack (for clustering). Land cover is excluded — it is a "
            "mask/context layer, not a clustering feature.\n\n"
            "**Output:** `feature_stack_250m`, `feature_stack_250m_z`. "
            "**DoD:** single multiband asset, gap-free over AOI, documented band list."
        ),
        code(INIT),
        code(LOAD_AOI),
        md("### Load cached feat_* assets and assemble"),
        code(
            "imgs = features.load_stack_images(project)  # cached 250 m assets (cheap)\n"
            "raw, z = features.assemble_stack(imgs, aoi)\n"
            "bands = raw.bandNames().getInfo()\n"
            "print(f'{len(bands)} bands:'); print(bands)"
        ),
        md("### DoD sanity — raw-stack band ranges"),
        code("utils.range_report(raw, aoi)"),
        md("### Export both stacks"),
        code(
            "utils.ensure_folder(project)\n"
            "t1 = utils.export_image(raw, project, 'feature_stack_250m', aoi)\n"
            "t2 = utils.export_image(z, project, 'feature_stack_250m_z', aoi)\n"
            "print(utils.task_summary([t1, t2]))"
        ),
    ],
)

# ---------------------------------------------------------------- Part 9
write(
    "09_suitability_fuzzy_ahp.ipynb",
    [
        md(
            "# Part 9 — Knowledge-based suitability (7 segments)\n\n"
            "FAO land evaluation + AHP: fuzzy-standardize each factor of the **raw** "
            "`feature_stack_250m` to [0,1], combine per segment with a **weighted "
            "geometric mean** (limiting-factor behavior), mask with the Part-7b "
            "land-cover masks, and classify into FAO **S1/S2/S3/N**. Rules live in "
            "`config/segments.yaml`; the engine in `src/membership.py`.\n\n"
            "**Output:** `suit_present` (7 `suit_*` + 7 `class_*` bands). "
            "**DoD:** 7 maps render; built-up/water masked; soy high on flat/fertile "
            "land, conservation high on steep/native."
        ),
        code(INIT + "\nimport membership, external"),
        code(LOAD_AOI),
        md(
            "### Load the raw 250 m stack + land-cover masks, the segment rules, and the "
            "side-image factors\n"
            "`extras` routes the recalibrated side-image factors into the engine "
            "(`membership._source_image`): `sit_` → `feat_siting` (solar clearness / pisci "
            "seasonal-water distance), `rl_` → the realized-use image (conservation's demoted "
            "`rl_native_frac`), `cv_` → `feat_conservation` (conservation-value: WDPA distance / "
            "ruggedness / biomass carbon). These stay **out** of the 34-band stack (guardrail)."
        ),
        code(
            "stack = ee.Image(utils.asset_id(project, 'feature_stack_250m'))\n"
            "lc = ee.Image(utils.asset_id(project, 'feat_landcover'))\n"
            "seg_cfg = utils.cfg('segments')\n"
            "segs = list(seg_cfg['segments'])\n"
            "# side-image factors (cached feat_siting / feat_conservation once Parts 7c/7d exported)\n"
            "siting = ee.Image(utils.asset_id(project, 'feat_siting'))\n"
            "consv = ee.Image(utils.asset_id(project, 'feat_conservation'))\n"
            "realized = external.realized_features(aoi)\n"
            "extras = {'sit_': siting, 'rl_': realized, 'cv_': consv}\n"
            "print('segments:', segs)"
        ),
        md(
            "### AHP weight sanity — each segment's factor weights sum to 1\n"
            "(`membership.consistency_ratio(matrix)` is available to back these with a "
            "Saaty pairwise matrix when one is elicited.)"
        ),
        code(
            "import pandas as pd\n"
            "rows = [(s, len(d['factors']),\n"
            "         round(sum(f['weight'] for f in d['factors'].values()), 3), d['mask'])\n"
            "        for s, d in seg_cfg['segments'].items()]\n"
            "pd.DataFrame(rows, columns=['segment', 'n_factors', 'weight_sum', 'mask'])"
        ),
        md("### Build the 7-segment suitability + FAO class image"),
        code(
            "suit = membership.suit_present(stack, lc, seg_cfg, extras)\n"
            "bands = suit.bandNames().getInfo()\n"
            "print(f'{len(bands)} bands:'); print(bands)"
        ),
        md(
            "### Comparative best-use + siting-screen variance test (2026-07-14)\n"
            "`comparative_present` z-normalizes each segment's suitability over the AOI so the "
            "unequal-permissiveness segments compare on common footing (`best_use` argmax + "
            "`comp_*` bands). `segment_spatial_std` is the σ≲0.15 variance test — segments below it "
            "(expected: solar, pisciculture) are presented as feasibility screens, not graded surfaces."
        ),
        code(
            "comp = membership.comparative_present(suit, aoi, segs, scale=1000)\n"
            "sd = membership.segment_spatial_std(suit, aoi, segs, scale=1000).getInfo()\n"
            "import pandas as pd\n"
            "sdf = pd.Series({s: sd.get(f'suit_{s}') for s in segs}).round(3)\n"
            "print('spatial std per segment (screen if <= 0.15):'); print(sdf)"
        ),
        md("### DoD sanity — suitability bands must lie in [0,1]"),
        code("utils.range_report(suit.select([f'suit_{s}' for s in segs]), aoi)"),
        md("### Quick look — soybean (flat/fertile) vs conservation (steep/native)"),
        code(
            "Map = geemap.Map(); Map.centerObject(aoi, 7)\n"
            "vis = {'min': 0, 'max': 1, 'palette': ['red', 'yellow', 'green']}\n"
            "Map.addLayer(suit.select('suit_soybean'), vis, 'soybean')\n"
            "Map.addLayer(suit.select('suit_conservation'), vis, 'conservation', False)\n"
            "Map.addLayer(suit.select('suit_solar'), vis, 'solar', False)\n"
            "Map.addLayer(aoi, {}, 'AOI', False)\n"
            "Map"
        ),
        md("### Export `suit_present` (7 suitability + 7 FAO-class bands) + `suit_present_comp`"),
        code(
            "utils.ensure_folder(project)\n"
            "task = utils.export_image(suit, project, 'suit_present', aoi)\n"
            "# comparative best-use (comp_* + best_use argmax) for the atlas / zone profiling\n"
            "t_comp = utils.export_image(comp, project, 'suit_present_comp', aoi)\n"
            "print(utils.task_summary([task, t_comp]))"
        ),
        md(
            "### (Optional) Weight-sensitivity robustness — ±20% AHP sweep\n"
            "Heavier compute (re-evaluates each segment under perturbed weights). Submit "
            "only if quota allows; smaller band = more robust. Exports a separate asset so "
            "the main `suit_present` stays lean."
        ),
        code(
            "sens = membership.sensitivity_present(stack, lc, seg_cfg, extras)\n"
            "t2 = utils.export_image(sens, project, 'suit_present_sens', aoi)\n"
            "print('export', t2.status()['description'], '->', t2.status()['state'])"
        ),
    ],
)

# ---------------------------------------------------------------- Part 10
write(
    "10_zoning_kmeans.ipynb",
    [
        md(
            "# Part 10 — Unsupervised biophysical zoning + profiling (decorrelated)\n\n"
            "Cluster a **curated, decorrelated** subset of the z-scored stack into biophysical "
            "zones, then profile each zone. Engine: `src/zoning.py`.\n\n"
            "**Decorrelation (2026-07-14):** clustering the raw 34-band stack resolved only 3 "
            "low-expressiveness zones — GO is climatically near-uniform yet the 14 collinear climate "
            "bands each carried full Euclidean weight and swamped the soil/relief/hydrology structure. "
            "We now cluster on `zoning.ZONING_BANDS` (~15 bands) with **theme-block weighting** "
            "(÷√bands-in-theme) then **PCA** (≥90% variance), and **re-select k** by "
            "silhouette + Davies–Bouldin + the gap statistic (expect k=4–6).\n\n"
            "**Clustering is offline (scikit-learn)**, not EE weka. We fit KMeans in PC space, then "
            "classify the full image server-side by projecting bands onto the PCA loadings and taking "
            "the **nearest centroid** (linear band-math, label-identical to sklearn).\n\n"
            "**Guardrail:** only z-features feed the clusterer; the raw stack, `suit_*` and realized-use "
            "fractions ride along **for profiling only** — never as clustering inputs.\n\n"
            "**Output:** `zones_present` + `zone_profiles.csv`. **DoD:** k≥4 with defensible internal "
            "validity; zones biophysically distinct; profile cards carry a de-meaned suitability signature."
        ),
        code(INIT + "\nimport zoning, external"),
        code(LOAD_AOI),
        md(
            "### Load the z-stack (clustering) + raw stack, suitability, realized use (profiling)\n"
            "Clustering uses only `zoning.ZONING_BANDS` (the curated decorrelated subset); the realized "
            "role fractions ride along so profile cards report each zone's land-use composition."
        ),
        code(
            "z = ee.Image(utils.asset_id(project, 'feature_stack_250m_z'))\n"
            "raw = ee.Image(utils.asset_id(project, 'feature_stack_250m'))\n"
            "suit = ee.Image(utils.asset_id(project, 'suit_present'))\n"
            "realized = external.realized_features(aoi)\n"
            "band_names = zoning.ZONING_BANDS\n"
            "frac_bands = [f'rl_{r}_frac' for r in ('soybean','sugarcane','other_crops','pasture','native')]\n"
            "segs = list(utils.cfg('segments')['segments'])\n"
            "print(f'{len(band_names)} curated clustering bands; {len(segs)} segments')"
        ),
        md(
            "### Sample once (aligned): `z_*` curated features + raw + `suit_*` + realized fractions\n"
            "Pulled to a DataFrame for offline decorrelation + clustering. For very large `n`, swap the "
            "`fc_to_df` getInfo for an `Export.table` to Drive."
        ),
        code(
            "sample = zoning.build_sample(z, raw, suit, aoi, band_names, n=15000, seed=42,\n"
            "                             extra=realized.select(frac_bands))\n"
            "df = zoning.fc_to_df(sample)\n"
            "# theme-block-weighted design matrix, then PCA (>=90% variance) to decorrelate\n"
            "X = zoning.cluster_matrix(df, band_names)          # theme-weighted z-features\n"
            "pca = zoning.fit_pca(X, var_keep=0.90)\n"
            "S = pca.transform(X)\n"
            "print(f'design {X.shape} -> {pca.n_components_} PCs (>=90% var); PC space {S.shape}')"
        ),
        md(
            "### Re-select k on the decorrelated PC space — silhouette + Davies–Bouldin + gap\n"
            "Cluster in PC space. Lower Davies–Bouldin and higher silhouette are better; the gap "
            "statistic's first `gap(k) >= gap(k+1) - s_{k+1}` is the recommended k. Default picks the "
            "max-silhouette k; override `K` if the other criteria argue otherwise (expect 4–6)."
        ),
        code(
            "sweep = zoning.kmeans_sweep(S, ks=range(2, 11), seed=42)\n"
            "gap = zoning.gap_statistic(S, ks=range(2, 11), B=10, seed=42)\n"
            "swp = sweep.merge(gap, on='k')\n"
            "print(swp.round(3).to_string(index=False))\n"
            "import matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots(1, 3, figsize=(13, 3))\n"
            "ax[0].plot(swp.k, swp.silhouette, 'o-'); ax[0].set(title='silhouette (max)', xlabel='k')\n"
            "ax[1].plot(swp.k, swp.davies_bouldin, 'o-'); ax[1].set(title='Davies-Bouldin (min)', xlabel='k')\n"
            "ax[2].errorbar(swp.k, swp.gap, yerr=swp.s_k, fmt='o-'); ax[2].set(title='gap', xlabel='k')\n"
            "plt.tight_layout(); plt.show()\n"
            "K = int(swp.loc[swp.silhouette.idxmax(), 'k'])\n"
            "print('chosen K =', K, '(review DB + gap before committing)')"
        ),
        md("### Fit final KMeans in PC space, classify the full image (nearest-centroid in PC space)"),
        code(
            "km = zoning.fit_kmeans(S, K, seed=42)\n"
            "import numpy as np\n"
            "print('zone sizes (sample):', np.bincount(km.labels_))\n"
            "# project the z-image onto the PCA loadings server-side, then nearest-centroid\n"
            "theme_w = zoning.theme_weight_vector(band_names)\n"
            "pc_img = zoning.pca_project_image(z, band_names, theme_w, pca)\n"
            "zones = zoning.nearest_centroid_image(pc_img, zoning.pc_names(pca), km.cluster_centers_)\n"
            "print('zone band:', zones.bandNames().getInfo())"
        ),
        md(
            "### Profile each zone — feature means, comparative best-use, top features, composition\n"
            "`comparative_segment` (argmax of zone-mean z-normalized suitability) is the zone's headline "
            "label (replaces the ad-hoc distinctive-segment); `top_features` are its most distinctive "
            "z-bands; `rl_*_frac` give the realized land-use composition. Profiling uses the sample "
            "labels (offline, quota-light; labels match the exported `zones_present`)."
        ),
        code(
            "prof = zoning.profile_zones(df, km.labels_, band_names, segs, realized_fracs=frac_bands)\n"
            "prof.to_csv('zone_profiles.csv', index=False)\n"
            "cols = ['zone', 'n', 'comparative_segment', 'dominant_segment', 'top_features']\n"
            "prof[cols + [f'suit_{s}' for s in segs]].round(3)"
        ),
        md("### Quick look — zone map"),
        code(
            "Map = geemap.Map(); Map.centerObject(aoi, 7)\n"
            "pal = ['#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf']\n"
            "Map.addLayer(zones, {'min': 0, 'max': K - 1, 'palette': pal[:K]}, 'zones')\n"
            "Map.addLayer(aoi, {}, 'AOI', False)\n"
            "Map"
        ),
        md("### Export `zones_present`"),
        code(
            "utils.ensure_folder(project)\n"
            "task = utils.export_image(zones.toByte(), project, 'zones_present', aoi)\n"
            "print('export', task.status()['description'], '->', task.status()['state'])"
        ),
    ],
)

# ---------------------------------------------------------------- Part 11
write(
    "11_cmip6_shift.ipynb",
    [
        md(
            "# Part 11 — CMIP6 delta-change future suitability & shift\n\n"
            "Apply NEX-GDDP-CMIP6 monthly **change factors** (ratio for precip, "
            "additive Δ for tasmax/tasmin; ensemble of 5 GCMs) to the observed "
            "**TerraClimate 1991–2020** baseline, re-derive the climate bands with the "
            "*same* `features.derive_climate_bands`, and re-run the **Part-9 membership** "
            "on a future stack (terrain/soil/etc. static). Engine: `src/cmip6.py`.\n\n"
            "Because baseline and future share one derivation, `suit_future − suit_present` "
            "is a **pure climate signal** (identity factors reproduce `feat_climate`). PET "
            "uses a Hargreaves ratio (Ra cancels); srad & soil-moisture held at baseline "
            "(documented caveats). Ensemble factors → `suit_future`; per-GCM signs → "
            "`agreement`.\n\n"
            "**Output:** `suit_future_<ssp>_<window>`, `delta_<ssp>_<window>`, "
            "`agreement_<ssp>_<window>`. **DoD:** Δ + agreement render; hindcast bias bounded."
        ),
        code(INIT + "\nimport cmip6, membership, external"),
        code(LOAD_AOI),
        md(
            "### Load present suitability + masks + side-image factors; pin the GCM ensemble\n"
            "`extras` (the `sit_`/`rl_` side images) are **held at baseline** in the future exactly like "
            "srad/soil-moisture — clearness keys on baseline srad, seasonal-water distance is static, "
            "native cover is a present observation — so Δ isolates the climate-driven factors (incl. "
            "solar's new `clim_twarm_q` heat de-rating, which *does* move with the future stack). The "
            "same `extras` feed present-rederived and future so they cancel in Δ."
        ),
        code(
            "suit_present = ee.Image(utils.asset_id(project, 'suit_present'))\n"
            "lc = ee.Image(utils.asset_id(project, 'feat_landcover'))\n"
            "seg_cfg = utils.cfg('segments'); segs = list(seg_cfg['segments'])\n"
            "siting = ee.Image(utils.asset_id(project, 'feat_siting'))\n"
            "consv = ee.Image(utils.asset_id(project, 'feat_conservation'))\n"
            "extras = {'sit_': siting, 'rl_': external.realized_features(aoi), 'cv_': consv}\n"
            "cc = utils.cfg()['cmip6']\n"
            "models, scenarios, windows = cc['models'], cc['scenarios'], cc['windows']\n"
            "print(f'{len(models)} GCMs:', models)\n"
            "print('scenarios:', scenarios, '| windows:', list(windows))\n"
            "# observed TerraClimate monthly climatology — built once, reused for every (ssp, window)\n"
            "base = cmip6.baseline_monthly(aoi)\n"
            "# Δ reference: present recomputed on-the-fly so the baseline cancels exactly in Δ.\n"
            "# (Subtracting the *exported* suit_present asset injects an export-reproject offset;\n"
            "#  verified: identity factors give Δ≈0 vs this, but spurious ±0.05–0.3 vs the asset.)\n"
            "suit_present_re = cmip6.suit_present_rederived(project, aoi, lc, seg_cfg, extras=extras)"
        ),
        md(
            "### Hindcast sanity — CMIP6 historical vs observed baseline bias\n"
            "Delta-change *cancels* this bias, so it is a report (should be bounded/plausible, "
            "not zero), not part of the projection. Heavier reduction — skip under tight quota."
        ),
        code(
            "import pandas as pd\n"
            "hb = cmip6.hindcast_bias(models, aoi).getInfo()\n"
            "print('CMIP6 historical − observed baseline (annual precip mm, mean temp °C):')\n"
            "print(pd.Series(hb).round(2))"
        ),
        md(
            "### Future suitability + ΔSuitability — one scenario/window (detail)\n"
            "`suit_future` is one membership run on the ensemble-mean future climate."
        ),
        code(
            "ssp, win_name = 'ssp245', '2031_2050'  # windows[win_name] is the [start,end] list cmip6 needs\n"
            "sf = cmip6.suit_future(project, models, ssp, windows[win_name], aoi, lc, seg_cfg, base=base, extras=extras)\n"
            "dl = cmip6.delta(sf, suit_present_re, segs)\n"
            "print('suit_future bands:', sf.bandNames().getInfo())"
        ),
        md("### DoD sanity — ΔSuitability range per segment (expect small, signed values)"),
        code("utils.range_report(dl, aoi)"),
        md("### Quick look — ΔSuitability (soybean), diverging palette"),
        code(
            "Map = geemap.Map(); Map.centerObject(aoi, 7)\n"
            "dvis = {'min': -0.2, 'max': 0.2, 'palette': ['#b2182b','#f7f7f7','#2166ac']}\n"
            "Map.addLayer(dl.select('delta_soybean'), dvis, f'Δ soybean {ssp} {win}')\n"
            "Map.addLayer(dl.select('delta_cattle'), dvis, f'Δ cattle {ssp} {win}', False)\n"
            "Map.addLayer(aoi, {}, 'AOI', False)\n"
            "Map"
        ),
        md(
            "### Export `suit_future_*` + `delta_*` for every scenario × window\n"
            "Batch tasks (heavy: each rebuilds the CMIP6 monthly climatologies server-side). "
            "Monitor with `earthengine task list`."
        ),
        code(
            "utils.ensure_folder(project)\n"
            "tasks = []\n"
            "for ssp in scenarios:\n"
            "    for win_name, win in windows.items():  # win is [start,end]; win_name is the asset suffix\n"
            "        sf = cmip6.suit_future(project, models, ssp, win, aoi, lc, seg_cfg, base=base, extras=extras)\n"
            "        dl = cmip6.delta(sf, suit_present_re, segs)\n"
            "        tasks.append(utils.export_image(sf, project, f'suit_future_{ssp}_{win_name}', aoi))\n"
            "        tasks.append(utils.export_image(dl, project, f'delta_{ssp}_{win_name}', aoi))\n"
            "print(utils.task_summary(tasks))"
        ),
        md(
            "### (Optional) Ensemble-agreement maps — fraction of GCMs agreeing on sign of Δ\n"
            "Confidence layer; **heavier** (one membership run per GCM). Submit per "
            "scenario/window as quota allows; coarsen if a task times out."
        ),
        code(
            "ag_tasks = []\n"
            "for ssp in scenarios:\n"
            "    for win_name, win in windows.items():\n"
            "        ag = cmip6.agreement(project, models, ssp, win, aoi, suit_present_re, lc, seg_cfg, base=base, extras=extras)\n"
            "        ag_tasks.append(utils.export_image(ag, project, f'agreement_{ssp}_{win_name}', aoi))\n"
            "print(utils.task_summary(ag_tasks))"
        ),
    ],
)

# ---------------------------------------------------------------- Part 12
write(
    "12_municipal_gaul.ipynb",
    [
        md(
            "# Part 12 — Municipal units (IBGE malha municipal)\n\n"
            "Load the GO+DF municipalities from the local IBGE mesh (client-side, no upload) and "
            "aggregate present suitability, zones and the CMIP6 Δ per municipality with "
            "`reduceRegions` — the join table for offline rankings (Parts 14–15). "
            "Engine: `src/external.py` + `src/ibge_mesh.py`.\n\n"
            "**Output:** `municipal_godf` (table asset) + a per-municipality CSV. **DoD:** "
            "GO+DF municipalities load (DF present as Brasília); `reduceRegions` runs; "
            "`NM_MUN` is the join key."
        ),
        code(INIT + "\nimport external"),
        code(LOAD_AOI),
        md("### Load the municipal units (IBGE malha municipal, GO+DF)"),
        code(
            "muni = external.municipal_fc()\n"
            "print('municipalities:', muni.size().getInfo())\n"
            "print('states:', muni.aggregate_array('NM_UF').distinct().getInfo())"
        ),
        md("### Aggregate present suitability + zone + Δ per municipality"),
        code(
            "suit = ee.Image(utils.asset_id(project, 'suit_present'))\n"
            "zones = ee.Image(utils.asset_id(project, 'zones_present')).rename('zone')\n"
            "delta = ee.Image(utils.asset_id(project, 'delta_ssp585_2051_2070'))\n"
            "segs = list(utils.cfg('segments')['segments'])\n"
            "agg_img = suit.select([f'suit_{s}' for s in segs]).addBands(zones).addBands(delta)\n"
            "table = external.municipal_means(muni, agg_img)\n"
            "print('reduceRegions feature count:', table.size().getInfo())"
        ),
        md("### Peek — a few municipalities' mean suitability"),
        code(
            "import pandas as pd\n"
            "key = utils.cfg()['municipal_mesh']['join_key']\n"
            "props = [key, 'NM_UF'] + [f'suit_{s}' for s in segs]\n"
            "rows = table.select(props, None, False).limit(8).getInfo()['features']\n"
            "pd.DataFrame([f['properties'] for f in rows]).round(3)"
        ),
        md("### Export — `municipal_godf` table asset (with geometry) + municipal CSV to Drive"),
        code(
            "utils.ensure_folder(project)\n"
            "# asset export keeps geometry (Export.table.toAsset rejects null geometry);\n"
            "# the CSV drops it via property selectors for a light offline join.\n"
            "t1 = utils.export_table(table, project, 'municipal_godf')\n"
            "csv_cols = [key, 'NM_UF'] + [f'suit_{s}' for s in segs] + ['zone']\n"
            "t2 = ee.batch.Export.table.toDrive(collection=table.select(csv_cols, None, False),\n"
            "        description='municipal_suit_summary', fileFormat='CSV')\n"
            "t2.start()\n"
            "print(utils.task_summary([t1, t2]))"
        ),
    ],
)

# ---------------------------------------------------------------- Part 13
write(
    "13_mapbiomas.ipynb",
    [
        md(
            "# Part 13 — MapBiomas realized use + potential-vs-realized (RQ2)\n\n"
            "Aggregate the GEE-hosted MapBiomas collection to a 250 m realized-use image "
            "(majority class + segment role + per-role area fractions + Brazil-specific "
            "masks), then cross it with `suit_present` for the **under-utilization** map "
            "(high potential ∧ not currently in that use) and profile realized composition "
            "by biophysical zone. Engine: `src/external.py`.\n\n"
            "**Guardrail:** MapBiomas is **mask + validation + descriptive profiling only** — "
            "it never enters the feature stack or the clusterer. The masks may *replace* the "
            "coarse Part-7b WorldCover mask for a higher-fidelity membership re-run "
            "(`external.hybrid_lc`), but that does not feed back into Parts 9–10.\n\n"
            "**Output:** `feat_realized`, `realized_vs_potential` + zone-composition tables. "
            "**DoD:** RQ2 answered; soy/cane realized footprints concentrate in high-suitability "
            "classes."
        ),
        code(INIT + "\nimport external, membership"),
        code(LOAD_AOI),
        md("### Build the 250 m realized-use image (majority class/role + masks + role fractions)"),
        code(
            "realized = external.realized_features(aoi)\n"
            "print('bands:', realized.bandNames().getInfo())"
        ),
        md("### DoD sanity — realized-role fractions and masks over AOI"),
        code("utils.range_report(realized, aoi)"),
        md("### Potential-vs-realized — under-utilization (high potential, other realized use)"),
        code(
            "suit = ee.Image(utils.asset_id(project, 'suit_present'))\n"
            "segs = list(utils.cfg('segments')['segments'])\n"
            "uu = external.underutilization(suit, realized, segs)\n"
            "print('under-utilization bands:', uu.bandNames().getInfo())\n"
            "# AOI area share flagged under-utilized per segment\n"
            "import pandas as pd\n"
            "shares = uu.reduceRegion(ee.Reducer.mean(), aoi, 1000, maxPixels=int(1e12),\n"
            "                         bestEffort=True, tileScale=8).getInfo()\n"
            "pd.Series(shares).round(3)"
        ),
        md("### Realized composition per biophysical zone (descriptive profiling)"),
        code(
            "zones = ee.Image(utils.asset_id(project, 'zones_present'))\n"
            "n_zones = int(zones.reduceRegion(ee.Reducer.max(), aoi, 1000, maxPixels=int(1e12),\n"
            "              bestEffort=True).values().get(0).getInfo()) + 1\n"
            "rows = []\n"
            "for z in range(n_zones):\n"
            "    h = (realized.select('rl_role').updateMask(zones.eq(z))\n"
            "         .reduceRegion(ee.Reducer.frequencyHistogram(), aoi, 1000,\n"
            "                       maxPixels=int(1e12), bestEffort=True, tileScale=8)\n"
            "         .getInfo()['rl_role'])\n"
            "    tot = sum(h.values())\n"
            "    rows.append({'zone': z, **{f'role_{k}': round(v / tot, 3) for k, v in h.items()}})\n"
            "pd.DataFrame(rows).fillna(0)"
        ),
        md("### Quick look — realized role + a soybean under-utilization map"),
        code(
            "Map = geemap.Map(); Map.centerObject(aoi, 7)\n"
            "role_pal = ['#eeeeee','#ffd400','#7b3294','#d95f0e','#2c7fb8','#addd8e','#006837']\n"
            "Map.addLayer(realized.select('rl_role'), {'min': 0, 'max': 6, 'palette': role_pal}, 'realized role')\n"
            "Map.addLayer(uu.select('underused_soybean'), {'min': 0, 'max': 1, 'palette': ['white','red']}, 'under-used soybean', False)\n"
            "Map.addLayer(aoi, {}, 'AOI', False)\n"
            "Map"
        ),
        md("### Export `feat_realized` + `realized_vs_potential`"),
        code(
            "utils.ensure_folder(project)\n"
            "t1 = utils.export_image(realized, project, 'feat_realized', aoi)\n"
            "t2 = utils.export_image(uu.toByte(), project, 'realized_vs_potential', aoi)\n"
            "print(utils.task_summary([t1, t2]))"
        ),
    ],
)

# ---------------------------------------------------------------- Part 14
write(
    "14_validation_proxy_rf.ipynb",
    [
        md(
            "# Part 14 — Productivity-proxy validation + RF cross-check (RQ1 validation)\n\n"
            "Validate the knowledge-based suitability against realized productivity and the "
            "realized niche: **Spearman ρ** of municipal mean suitability vs a MODIS MOD17 NPP "
            "proxy (cropland-restricted), the **Boyce index / AUC** of crop presence vs the "
            "suitability surface, an **ANOVA** of the proxy across zones, and a data-driven "
            "**random-forest** cross-check quantified by **Cohen's κ**. Engines: "
            "`src/external.py` + `src/metrics.py`.\n\n"
            "**Caveats:** MOD17 is *vegetation primary productivity, not agronomic yield* "
            "(coarse surrogate); the in-stack NDVI integral is excluded as validator (it is a "
            "suitability input → circular), so MOD17 is a distinct product with a noted residual "
            "shared-signal caveat.\n\n"
            "**Output:** validation tables (κ / ρ / Boyce / AUC / ANOVA). **DoD:** RQ1 validated."
        ),
        code(INIT + "\nimport external, metrics\nimport pandas as pd"),
        code(LOAD_AOI),
        md("### Build the MOD17 NPP productivity proxy (250 m multi-year mean, fills removed)"),
        code(
            "proxy = external.mod17_proxy(aoi)\n"
            "utils.range_report(proxy, aoi)"
        ),
        md("### Spearman ρ — municipal mean suitability vs MOD17 (cropland-restricted)"),
        code(
            "suit = ee.Image(utils.asset_id(project, 'suit_present'))\n"
            "realized = external.realized_features(aoi)\n"
            "crop = external.cropland_mask(realized)\n"
            "muni = external.municipal_fc()\n"
            "segs = list(utils.cfg('segments')['segments'])\n"
            "agg = suit.select([f'suit_{s}' for s in segs]).addBands(proxy).updateMask(crop)\n"
            "feats = external.municipal_means(muni, agg).select([f'suit_{s}' for s in segs] + ['mod17_npp'], None, False).getInfo()['features']\n"
            "df = pd.DataFrame([f['properties'] for f in feats]).dropna()\n"
            "for s in segs:\n"
            "    r = metrics.spearman(df[f'suit_{s}'], df['mod17_npp'])\n"
            "    print(f\"{s:14s} rho={r['rho']:+.3f}  p={r['p']:.1e}  n={r['n']}\")"
        ),
        md(
            "### Repaired crop validator — WITHIN-crop suitability→season-GPP gradient (2026-07-14)\n"
            "The annual NPP proxy above is confounded across land cover (positively tied to standing "
            "biomass, negatively to bare-fallow crops — the spurious soybean −0.34). The repair: "
            "**growing-season GPP** (`external.season_gpp`, MOD17A2HGF integrated over the Oct–Mar "
            "canopy window) evaluated **only on each crop's own realized pixels**, correlated against "
            "that crop's suitability (`metrics.within_crop_gradient`). This validates *how much* crops "
            "produce; the Boyce/AUC below validate *where*. Sign should be **non-negative** for the "
            "extensive crops. (Residual shared signal with the in-stack `phen_integral` remains — an "
            "IBGE-yield validator is the future upgrade.)"
        ),
        code(
            "gpp = external.season_gpp(aoi)  # sugarcane: pass months=list(range(1,13))\n"
            "for crop in ['soybean', 'sugarcane', 'other_crops']:\n"
            "    m = realized.select('rl_role').eq(external.ROLE_CODES[crop])\n"
            "    smp = (suit.select(f'suit_{crop}').addBands(gpp).updateMask(m)\n"
            "           .sample(region=aoi, scale=250, numPixels=8000, seed=7, dropNulls=True)\n"
            "           .getInfo()['features'])\n"
            "    g = pd.DataFrame([f['properties'] for f in smp])\n"
            "    r = metrics.within_crop_gradient(g[f'suit_{crop}'], g['season_gpp'])\n"
            "    print(f\"{crop:12s} within-crop rho={r['rho']:+.3f} p={r['p']:.1e} n={r['n']} monotonic={r['monotonic']}\")"
        ),
        md("### Boyce index / AUC — soybean presence (MapBiomas) vs the suitability surface"),
        code(
            "smp = (suit.select('suit_soybean').addBands(realized.select('rl_role'))\n"
            "       .sample(region=aoi, scale=250, numPixels=20000, seed=1, dropNulls=True)\n"
            "       .getInfo()['features'])\n"
            "sdf = pd.DataFrame([f['properties'] for f in smp])\n"
            "pres = sdf[sdf.rl_role == external.ROLE_CODES['soybean']]['suit_soybean']\n"
            "print('soybean Boyce index:', round(metrics.continuous_boyce(pres, sdf['suit_soybean'])['boyce'], 3))\n"
            "sdf['is_soy'] = (sdf.rl_role == external.ROLE_CODES['soybean']).astype(int)\n"
            "print('soybean AUC:', round(metrics.auc(sdf['is_soy'], sdf['suit_soybean'])['auc'], 3))"
        ),
        md("### ANOVA — MOD17 proxy across biophysical zones"),
        code(
            "zones = ee.Image(utils.asset_id(project, 'zones_present')).rename('zone')\n"
            "zs = (proxy.addBands(zones).sample(region=aoi, scale=1000, numPixels=15000, seed=2, dropNulls=True)\n"
            "      .getInfo()['features'])\n"
            "zdf = pd.DataFrame([f['properties'] for f in zs])\n"
            "groups = {int(z): g['mod17_npp'].values for z, g in zdf.groupby('zone')}\n"
            "print(metrics.anova(groups))"
        ),
        md(
            "### Data-driven RF cross-check — Cohen's κ vs the knowledge-based map\n"
            "Sample soybean presence/background on the z-stack, train `smileRandomForest` in "
            "PROBABILITY mode, threshold at 0.5, and compare to the knowledge-based S2+ map. "
            "Disagreements inform one `segments.yaml` recalibration pass."
        ),
        code(
            "z = ee.Image(utils.asset_id(project, 'feature_stack_250m_z'))\n"
            "lbl = realized.select('rl_role').eq(external.ROLE_CODES['soybean']).rename('presence')\n"
            "train = z.addBands(lbl).stratifiedSample(numPoints=3000, classBand='presence',\n"
            "        region=aoi, scale=250, seed=3, dropNulls=True)\n"
            "rf = (ee.Classifier.smileRandomForest(100).setOutputMode('PROBABILITY')\n"
            "      .train(train, 'presence', z.bandNames()))\n"
            "rf_cls = z.classify(rf).gte(0.5).rename('rf_cls')\n"
            "cmp = rf_cls.addBands(suit.select('class_soybean').gte(2).rename('kb_cls'))\n"
            "cs = cmp.sample(region=aoi, scale=250, numPixels=10000, seed=4, dropNulls=True).getInfo()['features']\n"
            "cdf = pd.DataFrame([f['properties'] for f in cs])\n"
            "print('soybean RF-vs-knowledge Cohen κ:', metrics.cohen_kappa(cdf['rf_cls'], cdf['kb_cls']))"
        ),
    ],
)

# ---------------------------------------------------------------- Part 15
write(
    "15_atlas_app.ipynb",
    [
        md(
            "# Part 15 — Synthesis: atlas figures, municipal ranking, GEE App\n\n"
            "Assemble the deliverables from the built assets: the thesis atlas figures "
            "(present + future), the municipal opportunity/vulnerability ranking over "
            "`municipal_godf`, and the interactive Earth Engine App. Figure rendering lives in "
            "`tools/make_figures.py`; the App source in `gee_js/atlas_app.js`.\n\n"
            "**Output:** `thesis/Chapters/Figures/*.png`, `thesis/Chapters/Figures/municipal_ranking.csv`, "
            "and a published App URL (manual one-click). **DoD:** all RQs reported with uncertainty; "
            "atlas figures rendered; municipal rankings produced; App source ready to publish."
        ),
        code(INIT + "\nsys.path.insert(0, os.path.abspath('../tools'))\nimport external, make_figures"),
        code(LOAD_AOI),
        md("### Render the atlas figures (present + future) → `thesis/Chapters/Figures/`"),
        code(
            "r = make_figures.Renderer()\n"
            "for name in make_figures.PRESENT + make_figures.FUTURE:\n"
            "    getattr(r, name)()"
        ),
        md("### Municipal opportunity / vulnerability ranking"),
        code(
            "import pandas as pd\n"
            "suit = ee.Image(utils.asset_id(project, 'suit_present'))\n"
            "uu = ee.Image(utils.asset_id(project, 'realized_vs_potential'))\n"
            "delta = ee.Image(utils.asset_id(project, 'delta_ssp585_2051_2070'))\n"
            "muni = external.municipal_fc()\n"
            "agg = (suit.select(['suit_soybean', 'suit_sugarcane'])\n"
            "       .addBands(uu.select(['underused_soybean', 'underused_sugarcane']))\n"
            "       .addBands(delta.select('delta_other_crops')))\n"
            "cols = ['NM_MUN', 'suit_soybean', 'underused_soybean', 'delta_other_crops']\n"
            "feats = external.municipal_means(muni, agg).select(cols, None, False).getInfo()['features']\n"
            "df = pd.DataFrame([f['properties'] for f in feats]).dropna()\n"
            "df['opportunity'] = df['suit_soybean'] * df['underused_soybean']\n"
            "df.sort_values('opportunity', ascending=False).round(3).to_csv('figures/municipal_ranking.csv', index=False)\n"
            "print('TOP OPPORTUNITY:'); print(df.nlargest(5, 'opportunity')[['NM_MUN','opportunity']].to_string(index=False))\n"
            "print('TOP VULNERABILITY:'); print(df.nsmallest(5, 'delta_other_crops')[['NM_MUN','delta_other_crops']].to_string(index=False))"
        ),
        md(
            "### Interactive GEE App\n"
            "The App source is `gee_js/atlas_app.js` (layer selector across the seven `suit_*`, FAO "
            "classes, zones, realized use, under-utilization and the CMIP6 `delta_*`; click-to-read "
            "municipal values). **Publishing is a manual one-click step** — paste the script into the "
            "[Code Editor](https://code.earthengine.google.com), then **Apps ▸ NEW APP ▸ publish**. "
            "The Python API cannot deploy an App."
        ),
    ],
)

print("done")
