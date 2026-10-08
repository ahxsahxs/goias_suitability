# CLAUDE.md — Goiás Agro-Market Suitability & CMIP6 Zoning

Single entry point for working in this repo. It explains **what the project is, how it's built,
how to run it, how to edit the LaTeX dissertation, and where it currently stands.**

> **Source of truth split:** the *narrative* methodology (rationale, research questions,
> validation theory, results, discussion) lives in the thesis itself —
> [`thesis/Chapters/`](thesis/Chapters/) (see §9 below). This file is the *operational* source of
> truth — conventions, environment, build/run commands, and per-part status. When the two would
> disagree, the built code + this file win for "how do I run/edit this"; the thesis chapters win
> for "why was this choice made." There is no separate `docs/methods.md`/`execution_plan.md`/
> `phase_b_data.md` — that content is now in the thesis chapters, not a standalone doc set.

For the human-facing overview (what this is, for a GitHub visitor coming from the thesis PDF),
see [`README.md`](README.md). This file assumes you already know that and need to *do* something.

---

## 1. What this is

A GEE-native **multi-segment agro-market suitability atlas + climate-projected zoning** of
**Goiás + Distrito Federal** (~340,000 km², Cerrado biome). It maps the biophysical /
agro-climatic *potential* of every 250 m cell for **seven land-use segments**, clusters the
territory into agro-environmental zones, then projects how that potential shifts to 2040/2050
under CMIP6.

**The seven segments:** soybean · sugarcane · other annual crops (corn/cotton/sorghum) ·
pisciculture (pond/reservoir aquaculture) · cattle (cultivated pasture) · forest & Cerrado
conservation · solar PV generation.

**Method, in one line:** FAO-style multi-criteria land evaluation (fuzzy membership + AHP weights,
weighted geometric mean → FAO S1/S2/S3/N) for suitability; unsupervised clustering for zoning;
delta-change CMIP6 for the future shift; validated against realized land use (MapBiomas) and a
MODIS MOD17 productivity proxy. Full treatment in `thesis/Chapters/04_methodology.tex`.

**Research questions** (full treatment in `thesis/Chapters/01_introduction.tex` and
`04_methodology.tex`):
- **RQ1 — suitability & segmentation:** how is GO/DF partitioned into agro-environmental zones, and
  what is each zone's potential-productivity profile across the seven segments?
- **RQ2 — potential vs. realized:** where does realized use (MapBiomas) / the MOD17 proxy diverge
  from modeled potential — i.e. where is land under-utilized or mismatched?
- **RQ3 — forecast:** under CMIP6 SSP2-4.5 / SSP5-8.5, how do suitability and zones shift by
  2031–2050 and 2051–2070 — winners, losers, cross-segment reallocation?

## 2. Platform & cost philosophy

**Everything runs server-side in Earth Engine** (free non-commercial / research tier). The local
machine is only for charts, table joins, and writing — no GPU, no large local archive, no cloud-ML
bill. Only small artifacts leave GEE (250 m GeoTIFFs/PNG thumbnails to Drive/local, CSV
sample/summary tables for matplotlib). The pipeline is **fully GEE-native — zero external
uploads** (no local archive of IBGE/MapBiomas source data is kept; see §7).

---

## 3. Phasing

- **Phase A — GEE-native core (the potential atlas).** AOI + six continuous feature themes + a
  generic land-cover mask + siting/conservation side-features + the 250 m feature-stack, then
  knowledge-based suitability, unsupervised zoning, **and** the CMIP6 forecast. Produces a complete
  *unvalidated* potential atlas + future projection from the bare catalog. **Parts 1–11.**
- **Phase B — Realized-use & validation (GEE-only).** Brings in MapBiomas land use, IBGE malha
  municipal boundaries, and the MOD17 productivity proxy — for masking, potential-vs-realized analysis,
  productivity validation, the data-driven RF cross-check, and municipal decisions. **Parts 12–15.**

The split is *biophysical potential* (A) vs *realized-use & validation* (B) — not catalog-vs-upload
(nothing uploads).

## 4. Execution status — project `probformer`

**Phase A + Phase B modelling are structurally complete — Parts 1–15 built & footprint-verified.** The Part-9 weighting layer was re-derived (`tools/derive_weights.py`, §11) and the full Part 9→15 cascade re-run against it on 2026-09-29/30; the zoning moved from K=10 to **K=4**.

**Spatial holdout cascade (2026-10-03, in progress).** σ(μ) and the percentile breakpoints are now measured on the calibration half only (§7), which re-derived the weights and forced Parts 9→15 to be re-exported again. Three pre-committed gates were run in order: **Gate 0** (variogram) FAILED at 45 km blocks and forced the redesign to a 6×6 / ~130 km grid with area balancing; **Gate 1a/1b** (σ(μ) zero-weight check) passed 42/42, max relative weight change 17.7%, inside the ±20% envelope the thesis already publishes; **Gate 2** (breakpoints) moved 2 of 9 percentile anchors (`cattle.clim_soil_moist` 55→51, `cattle.soil_soc` 18→17) with 0 shape violations and 0 broken μ=1. The K panel re-read on held-out columns keeps **k=4** (`ari_holdout` 0.793, the clear max; `silhouette_val` 0.225 vs 0.235 at k=6, near-flat 0.144–0.235 across the whole sweep). Parts 1–8 were *not* rebuilt: `tools/diff_vs_backup.py` against `goias_backup_ahp_20260928` found 8 of 9 feature assets bit-identical across all 39 bands, with `feat_terrain` moving only in `terr_tpi`/`terr_twi` at the documented ~0.1% tile-edge level (`terr_slope`, computed without resampling, is bit-identical — confirming the mechanism is export-time resampling, not catalog drift).

All three RQs are answered and written into the thesis (chapters 01–05), but the numbers there —
class shares, zone profiles, Δ tables, the annex weight table — were produced under the previous
weights and will move once the cascade is re-run. **Part 15 (the interactive atlas)
is finished and live** — a static Vue 3 + TypeScript + Vite dashboard (`docs/dashboard/`)
superseding the old `gee_js/atlas_app.js` EE-App plan (see `docs/dashboard_ux_plan.md`) — all 11
routes are in place, deployed via `deploy-dashboard.yml` to GitHub Pages at
<https://ahxsahxs.github.io/goias_suitability> (the repo-settings flip is done). The i18n pass and
image trim are done, and it is now linked from the thesis (`03_materials.tex`); the thesis text no
longer lists it as future work.

| Part | State | Notes |
|---|---|---|
| 1–8 | **BUILT & footprint-verified** | Ten feature assets incl. `feature_stack_250m(_z)` (34-band stack) + `feat_siting` (solar clearness / seasonal water distance) + `feat_conservation` (WDPA distance / ruggedness / carbon) — the latter two are side-images kept **out** of the stack (routed into suitability via the `sit_`/`cv_` extras prefix). |
| 9 — suitability | **BUILT (re-derived weights)** | `suit_present` / `suit_present_comp` / `suit_present_sens`: 7 `suit_*` (0–1) + 7 `class_*` (FAO S1/S2/S3/N) + 7 `sens_*` (±20% AHP). Conservation is a value/priority index (arithmetic-mean aggregation — compensatory); the other six segments use the weighted geometric mean. Weights are derived by `tools/derive_weights.py` (see §11): `w = normalize(w_lit · σ(μ)^λ)` with σ(μ) measured over available land in the **calibration half**, pooled over the present and the CMIP6 horizon. `role: gate` is **retired** — no factor leaves the AHP matrix; five climate factors still land at weight exactly 0 because μ ≡ 1 in both populations. Worst consistency ratio **0.0335** (sugarcane), **8** author judgements, 0 overrides. |
| 10 — zoning | **BUILT — K=4**, offline `k=2..20` sweep | `zones_present`, offline sklearn KMeans on a decorrelated PCA input (`src/zoning.py`), classified server-side by nearest-centroid band math. Zones labelled by `comparative_segment` (argmax of each segment's z-normalized suitability), not raw dominance. `zone_profiles.csv` + `zoning_kselect.csv`. |
| 11 — CMIP6 shift | **BUILT** | `suit_future_*`, `delta_*`, `agreement_*` assets across SSP2-4.5/SSP5-8.5 × 2031–2050/2051–2070 × 5-GCM ensemble. Delta-change engine validated against an identity change-factor (Δ=0.000). No structurally climate-invariant segment remains — every segment (including conservation and solar) moves under at least one climate lever. |
| 12–14 — Phase B | **BUILT** | `realized_vs_potential`, `municipal_godf` (IBGE malha municipal aggregation, 247 municipalities), MOD17 productivity validation (municipal Spearman + within-crop GPP gradient), RF presence cross-check (Cohen's κ = +0.269, AUC = 0.871 for soybean), AHP consistency ratios. See `config/ahp_matrices.yaml` and `thesis/Chapters/05_results.tex` / `06_discussion_conclusion.tex` for the full numbers. |
| 15 — synthesis | **BUILT & live** | `docs/dashboard/` (Vue 3 + TS + Vite SPA): 11 routes covering every Part, built via `tools/build_dashboard_assets.py` from the assets in this table + config YAML. CI (`.github/workflows/deploy-dashboard.yml`) builds/type-checks/deploys successfully to GitHub Pages at <https://ahxsahxs.github.io/goias_suitability>, i18n and image trim done, and it's linked from `03_materials.tex`. See `docs/dashboard_ux_plan.md` for the architecture. |

- **Asset backups:** pre-recalibration and pre-reconceptualization snapshots were copied server-side
  under `projects/probformer/assets/goias_backup_*` before each major re-export cascade
  (`tools/backup_assets.py`).
- **Footprint-verified:** `tools/verify_assets.py` (metadata-only — runs even under restricted
  compute quota) confirms every asset is **EPSG:4326 @ 250 m (0.002246°)** with the exact GO+DF
  footprint (lon [-53.25, -45.90], lat [-19.50, -12.39]) — no displacement / scale error.
  ```bash
  EE_PROJECT=probformer uv run python tools/verify_assets.py
  ```

**Immediate next steps:** the dashboard and its thesis link are done; what remains is the Week 3
text work tracked in the revision artifact (§10) — rewriting "Trabalhos futuros" to drop delivered
items, a final cross-chapter consistency pass, compiling the PDF, and the adviser checkpoint.
Everything else needed for the thesis (all §4 tables, figures, the three RQs) is already built and
written.

---

## 5. Layout

```
config/datasets.yaml          # pinned EE dataset IDs, bands, scale factors (single source of truth)
config/segments.yaml          # Part 9: per-segment fuzzy-membership params + AHP weights + masks
config/ahp_matrices.yaml      # Part 9: AHP INPUT -- hand-written anchors (one ordinal band per
                                # factor + the published priority where one exists); the matrix,
                                # eigenvector, CI/RI/CR are written back by tools/derive_weights.py
config/mapbiomas_classes.yaml # MapBiomas code -> segment-role remap (Phase B, Part 13)
src/utils.py                  # EE init, config loader, 250 m grid, asset/export helpers
src/features.py               # ALL Part 1-8 feature builders (one source of truth; lazy ee, import-safe)
                                # + theme_roughness_image (revision point 5: local-stdDev magnitude
                                # map of climate vs. terrain/soil, §10)
src/membership.py             # Part 9 suitability engine: fuzzy membership + geomean + FAO + AHP/sensitivity
src/zoning.py                 # Part 10 zoning: sklearn KMeans (offline) + server-side nearest-centroid + profiling
src/cmip6.py                  # Part 11 CMIP6 delta-change: change factors + future climate + future suitability + Δ + agreement
src/external.py               # Parts 12-14: IBGE malha municipal boundaries, MapBiomas realized-use, MOD17 productivity proxy
src/ibge_mesh.py              # Local IBGE malha municipal loader (geopandas) -> client-side ee.FeatureCollection/ee.Geometry, no upload
src/metrics.py                # Part 14 offline validation stats (AUC, Boyce, Cohen's kappa, Spearman, spatial-block CV)
tools/build_malha_municipal.py # merges data/input/ibge/{GO,DF}_Municipios_2025.zip -> data/mart/malha_municipal.gpkg (Part 1/12)
tools/gen_notebooks.py        # regenerates notebooks from a spec; optional arg = only that notebook
tools/run_phase_a.sh          # executes 01->08 in order, waits for exports, assembles the stack
tools/wait_for_assets.py      # blocks until named EE assets exist (gates the stack step)
tools/verify_assets.py        # metadata-only footprint/CRS/scale check of built assets (no compute)
tools/make_figures.py         # renders thesis figures (PNG) straight into thesis/Chapters/Figures/
                                # (fig_4_12 is CSV/hexbin-only, no GEE thumbnail — see §10 note)
tools/extract_present.py      # Part 9/10 summary tables; also writes municipal_ranking.csv (see §11 gotcha)
tools/extract_cmip6.py        # Part 11 summary tables
tools/derive_weights.py       # Part 9: anchors -> Saaty matrix -> principal eigenvector (w_lit)
                                # -> w = normalize(w_lit * sigma(mu)^lambda) -> config/segments.yaml.
                                # `--check` fails if segments.yaml drifts. Replaces build_ahp.py
                                # (removed), which built the matrix FROM the weights.
tools/make_calib_val_split.py # the 50/50 spatial holdout: builds it, or `--check-only` audits it
                                # (Gate 0: variogram + balance -> variogram_suit.csv, split_balance.csv)
tools/diff_sigma_domains.py   # Gate 1: sigma(mu) full vs calib -> sigma_domain_diff.csv; FAILs if
                                # restriction zeroes a factor (which would kill its CMIP6 lever)
tools/diff_breakpoints.py     # Gate 2: which breakpoints move / which notes stop being true when
                                # the percentiles are re-anchored on the calibration half. Writes
                                # NOTHING to config/ -- prints the edit, a human applies it.
tools/anchor_breakpoints.py   # `percentiles` = band distributions; `discrimination` = sigma(mu),
                                # saturated/vetoed fractions -> thesis/Chapters/factor_discrimination.csv
tools/gen_diag_csvs.py        # regenerates zoning_kselect.csv / factor_variance.csv /
                                # theme_roughness(_points).csv diagnostics
tools/sync_zotero_bib.py      # Zotero export -> thesis/Bibliography/bibliography.bib (strips file/abstract/…,
                                # checks every \cite key exists, reports entries without a local PDF) — see §12
notebooks/01..15               # thin: import src/, build, range-report, view, export — one per Part
docs/                          # supporting notes: _search_terms.md (lit-search scaffolding, not part of
                                # the thesis), ahp_literatura.md (literature -> AHP crossing + the
                                # anti-circularity protocol), metodologia_diagrama.md (PT methodology diagrams),
                                # dashboard_ux_plan.md (Part 15 architecture reference),
                                # dashboard/ (the Vue 3 + TS + Vite dashboard project itself)
thesis/                        # the LaTeX dissertation itself (NOVAthesis/NOVA IMS template) — see §9
tools/build_dashboard_assets.py # Part 15: exports GEE assets + config YAML into docs/dashboard/public/data/
tools/palettes.py              # shared vis-param/color-ramp definitions (make_figures.py + build_dashboard_assets.py)
.github/workflows/deploy-dashboard.yml # CI: type-check + vite build + GitHub Pages deploy on push to docs/dashboard/**
```

**Code architecture:** notebooks are intentionally thin and **generated** from
`tools/gen_notebooks.py` — analysis logic lives in `src/`. To change a Part 1–8 feature, edit
`src/features.py`, then `python tools/gen_notebooks.py` to regenerate the notebooks. Each `feat_*`
builder returns an `ee.Image` already harmonized to the 250 m grid and clipped to AOI; builders are
lazy (no server call at import), so `src/` is import-/syntax-checkable without EE auth.

### Notebook ⇄ Part ⇄ src map

```
01_setup_aoi.ipynb            -> Part 1   (src/features.py + src/utils.py)
02_features_climate.ipynb     -> Part 2   (src/features.py)
03_features_terrain.ipynb     -> Part 3   (src/features.py)
04_features_soil.ipynb        -> Part 4   (src/features.py)
05_features_water.ipynb       -> Part 5   (src/features.py)
06_features_phenology.ipynb   -> Part 6   (src/features.py)
07_features_access.ipynb      -> Part 7   (src/features.py)
07b_landcover_mask.ipynb      -> Part 7b  (src/features.py)
07c_siting.ipynb              -> Part 7c  (src/features.py: siting_features -> feat_siting; NOT stacked)
07d_conservation.ipynb        -> Part 7d  (src/features.py: conservation_features -> feat_conservation; NOT stacked)
08_feature_stack.ipynb        -> Part 8   (src/features.py: STACK_THEMES)
09_suitability_fuzzy_ahp.ipynb-> Part 9   (src/membership.py + config/segments.yaml + config/ahp_matrices.yaml)
10_zoning_kmeans.ipynb        -> Part 10  (src/zoning.py)
11_cmip6_shift.ipynb          -> Part 11  (src/cmip6.py)
12_municipal_gaul.ipynb       -> Part 12  (src/external.py + src/ibge_mesh.py)┐
13_mapbiomas.ipynb            -> Part 13  (src/external.py)        ├ Phase B — BUILT
14_validation_proxy_rf.ipynb  -> Part 14  (src/external.py+metrics)┘
15_atlas_app.ipynb            -> Part 15  (docs/dashboard/ + tools/build_dashboard_assets.py) ── retitled target, notebook itself not yet regenerated
```

`12_municipal_gaul.ipynb` keeps its historical filename (reflects the last executed GAUL-based
run) even though `tools/gen_notebooks.py`'s Part-12 spec now targets the IBGE mesh — it's only
renamed by an explicit `tools/gen_notebooks.py` run, which would also wipe its saved outputs.

## 6. Outputs (EE assets under `projects/<project>/assets/goias/`)

| Part | Notebook | Asset | Contents |
|---|---|---|---|
| 1 | 01_setup_aoi | `aoi` | dissolved GO+DF boundary |
| 2 | 02_features_climate | `feat_climate` | precip/PET/CWD/aridity/GDD/srad/VPD… (14 bands) |
| 3 | 03_features_terrain | `feat_terrain` | elev, slope, aspect N/E, TPI, TWI (6 bands) |
| 4 | 04_features_soil | `feat_soil` | clay, sand, SOC, pH, bulk density, AWC (0–30 cm; 6 bands) |
| 5 | 05_features_water | `feat_water` | distance-to-water, seasonality, drainage density (3 bands) |
| 6 | 06_features_phenology | `feat_phenology` | NDVI mean, amplitude, peak month, integral (4 bands) |
| 7 | 07_features_access | `feat_access` | log travel-time to cities (1 band) |
| 7b | 07b_landcover_mask | `feat_landcover` | mode class, tree/crop/grass fractions, excluded/available masks |
| 7c | 07c_siting | `feat_siting` | solar clearness, seasonal water distance (2 bands; kept out of the stack) |
| 7d | 07d_conservation | `feat_conservation` | WDPA distance, ruggedness, carbon (3 bands; kept out of the stack) |
| 8 | 08_feature_stack | `feature_stack_250m`, `feature_stack_250m_z` | raw + z-scored 34-band stack (land cover excluded) |
| 9 | 09_suitability_fuzzy_ahp | `suit_present`, `suit_present_sens` | 7 `suit_*` (0–1) + 7 `class_*` (FAO S1/S2/S3/N) + 7 `sens_*` (±20% AHP) |
| 10 | 10_zoning_kmeans | `zones_present` (+ `zone_profiles.csv`) | biophysical zones (offline KMeans, nearest-centroid classify) + profile cards |
| 11 | 11_cmip6_shift | `suit_future_*`, `delta_*`, `agreement_*` | future suitability per SSP/window, Δ, GCM ensemble agreement |
| 12–15 | 12..15 | `municipal_godf`, `feat_realized`, `realized_vs_potential`, … | Phase B (IBGE malha municipal boundaries, MapBiomas realized use, MOD17 validation) |

The 34-band stack = climate 14 + terrain 6 + soil 6 + water 3 + phenology 4 + access 1; **land cover
is deliberately excluded** (guardrail, §7).

---

## 7. Conventions & guardrails

- **Analysis grid:** 250 m, **CRS EPSG:4326**. Areas via `ee.Image.pixelArea()`, never a stored
  field. Coarse climate resampled `bilinear`; fine terrain/soil coarsened via `reduceResolution`.
  Grid helpers: `utils.to_grid_bilinear`, `utils.to_grid_mean`, `utils.grid_projection`.
- **Climate normal:** **1991–2020** (WMO) everywhere — the leak-free baseline for CMIP6 deltas.
- **Asset root & naming:** `projects/<project>/assets/goias/<name>`. Every cached output is an EE
  asset (`utils.asset_id`). Naming: `feat_<theme>`, `feature_stack_250m[_z]`, `suit_present`,
  `zones_present`, `suit_future_<ssp>_<window>`, `delta_*`, `agreement_*`.
- **Land cover is mask/context only — never a clustering or suitability input.** Avoids
  categorical-in-kmeans and the circularity of using land use to predict land use. Hard guardrail
  throughout; `STACK_THEMES` in `features.py` deliberately excludes it. **One sanctioned exception:**
  conservation uses a (demoted) native-cover fraction as a *supportive* factor; no other segment
  consumes a land-cover band.
- **MapBiomas (Phase B) is mask + validation + descriptive profiling only** — same guardrail; it
  never becomes a suitability/clustering input even as its use expands.
- **`data/` is a one-off exception for the IBGE municipal mesh, not a general archive.** The
  project used to keep a local archive of IBGE municipal-mesh and PAM/PPM files plus a MapBiomas
  offline cross-check under `data/`; that broad archive was removed and the pipeline stayed
  GEE-native (GAUL for municipalities/AOI, MOD17 for productivity validation) for everything else.
  Revision point 6 (§10) reintroduced `data/` for exactly one thing: the official IBGE
  *Malha Municipal Digital* (2025 edition, SIRGAS 2000 / EPSG:4674, 246 GO + 1 DF municipalities),
  downloaded from IBGE's `malhas-territoriais` portal. Raw per-state zips live in
  `data/input/ibge/*.zip` and are **gitignored** (regenerable from IBGE's site, rebuilt via
  `tools/build_malha_municipal.py`); only the small merged artifact
  (`data/mart/malha_municipal.gpkg`, EPSG:4326, full precision, committed) leaves that step.
  **GAUL is fully retired from the code** — `src/ibge_mesh.py` now loads this geopackage and
  builds an `ee.FeatureCollection`/`ee.Geometry` **client-side, in memory, on every run** (never
  uploaded/exported as a persistent EE asset, preserving the zero-external-uploads guardrail in
  §2) for **both** the Part-1 AOI dissolve and the Part-12 municipal reporting join — not just the
  boundary layer for the ranking output. Join key / property names are `NM_MUN`/`SIGLA_UF`/`NM_UF`
  (not GAUL's `ADM2_NAME`/`ADM1_NAME`). Geometries are simplified in memory
  (`simplify_tolerance_deg` in `config/datasets.yaml`, default ~111 m, ~5x finer than
  `GAUL_SIMPLIFIED_500m`) before being embedded in any EE request — the committed `.gpkg` itself
  stays full precision. The 2026-09-19/20 rebuild propagated this swap through the full cascade
  (Parts 1–14, `aoi`, `municipal_godf`) and the thesis text (`03_materials.tex`, `07_annex.tex`) —
  GAUL is only mentioned there historically, as the boundary source used in an earlier iteration.
- **Calibration/validation spatial holdout (2026-10-03).** Every empirically estimated parameter is
  measured on one half of the territory and every reported validation metric on the other. The split
  is a 6x6 grid of ~130 km blocks (`data/mart/calib_val_blocks.csv`, 31 blocks, seed 2026), assigned
  to halves so the two carry **equal AREA** (171,631 km2 / 174,365 km2), not an equal number of
  blocks -- the grid is a bounding box, so an edge block may hold a sliver of the AOI and equal
  counts give very unequal territory. **The block size is measured, not conventional:** 130 km comes
  from the residual autocorrelation range (105 km soybean/sugarcane, 175 km other_crops), and the
  previous 45 km grid was replaced because it left ~52% of the structured variance shared across the
  boundary. Read the split through `utils.split_mask(project, half)` / `utils.split_image(project)`,
  which load the cached `calib_val_split` asset -- **never recompute the block grid in memory**,
  because it bins `ee.Geometry(aoi).bounds()` and would silently shift if `aoi` were re-exported.
  `$SPLIT_HALF` (`calib`|`val`|`full`|`all`) selects the domain in the tools that take one.
- **Small artifacts only leave GEE** (PNG thumbnails, GeoTIFFs, CSV sample/summary tables).

## 8. Environment & running

**Always run Python through `uv run`, never `.venv/bin/python` directly and never system Python,
and always with `EE_PROJECT=probformer` set.** Two equivalent ways:

```bash
# A) per-command (preferred for one-offs and scripts)
EE_PROJECT=probformer uv run python <script.py>

# B) activate the venv once, then `python ...` for the rest of the session
source .venv/bin/activate            # bash/zsh
source .venv/bin/activate.fish       # fish
export EE_PROJECT=probformer         # bash/zsh;  fish: set -x EE_PROJECT probformer
python <script.py>
```

The environment is managed with `uv` (`pyproject.toml` + `uv.lock`); `uv sync` creates/updates
`.venv/` from the lockfile. Jupyter kernel name is `goias`. Earth Engine needs a live login first.
EE project resolves from `$EE_PROJECT` → the credentials file; current project: **`probformer`** —
keep it set so assets resolve under `projects/probformer/assets/goias/`.

GDAL and geopandas are installed on the host for the IBGE municipal-mesh work (the local vector
join between the official IBGE malha and the municipal ranking table, §7). Invoke Python
exclusively via `uv run python ...` (or `uv run <tool>`), not `.venv/bin/python` or a bare
`python3` — some host-level geo packages only resolve correctly through `uv run`'s environment.

**`docs/dashboard/` (Part 15) has its own Node/npm toolchain, entirely independent of the
`uv`-managed Python environment above** — `cd docs/dashboard && npm install && npm run dev` to
iterate on the site; running or building it never needs `uv`/EE credentials. Only
`tools/build_dashboard_assets.py` (which populates `docs/dashboard/public/data/`) is Python and
needs `EE_PROJECT=probformer uv run python ...` like every other tool in this repo.

```bash
# one-time setup
uv sync
uv run python -m ipykernel install --user --name goias --display-name "Python (goias)"

# authenticate (interactive OAuth — suggest `! ...` to run in-session)
uv run earthengine authenticate

# run Phase A headless: executes 01->08, submits exports, waits, assembles the stack
bash tools/run_phase_a.sh
uv run earthengine task list        # monitor async export tasks

# regenerate notebooks after editing src/features.py
uv run python tools/gen_notebooks.py

# metadata-only asset check (runs under restricted quota)
EE_PROJECT=probformer uv run python tools/verify_assets.py

# Part 9 weights: recompute sigma(mu), then re-derive and verify the weights
EE_PROJECT=probformer uv run python tools/anchor_breakpoints.py discrimination
uv run python tools/derive_weights.py --check   # exit 1 if segments.yaml drifted

# regenerate thesis figures (writes into thesis/Chapters/Figures/)
EE_PROJECT=probformer uv run python tools/make_figures.py all
```

Parts 9+ load the cached `feat_*` / stack assets directly, so they don't recompute upstream graphs.

---

## 9. Working with the LaTeX thesis

The dissertation source lives entirely in [`thesis/`](thesis/) — a NOVAthesis/NOVA IMS template,
tracked in this same repo (not a submodule, not a separate git history).

```
thesis/template.tex                # entry point — pulls in Config/ then Chapters/
thesis/Config/1_novathesis.tex     # language (lang=pt), degree/specialization (imsDegree/imsSpecialization)
thesis/Config/3_cover.tex          # title (pt/en), author, adviser
thesis/Chapters/01_introduction.tex
thesis/Chapters/02_estado_arte.tex
thesis/Chapters/03_materials.tex
thesis/Chapters/04_methodology.tex
thesis/Chapters/05_results.tex
thesis/Chapters/06_discussion_conclusion.tex
thesis/Chapters/07_annex.tex
thesis/Chapters/abstract-pt.tex, abstract-en.tex, abstract-{de,es,fr,gr,it}.tex
thesis/Chapters/Figures/           # fig_4_*.png etc. — regenerated by tools/make_figures.py
thesis/Bibliography/bibliography.bib            # GENERATED from Zotero — never hand-edit (§12)
thesis/Bibliography/zotero_bibliography.bib     # Zotero BibLaTeX export (local, gitignored)
thesis/Bibliography/zotero_storage/<ID>/        # Zotero attachments = the source PDFs (local, gitignored)
```

**Build:**

```bash
cd thesis
make            # default target: picks pdfLaTeX or XeLaTeX per school, runs latexmk
```

Build artifacts (`*.aux`, `*.bbl`, `*.log`, `*.pdf`, …) are gitignored (`thesis/*.<ext>` rules in
`.gitignore`) — the compiled PDF is never committed, only the `.tex`/`.bib`/figure sources are.

**Editing:** edit the relevant `Chapters/*.tex` file directly. Title/author/adviser live in
`Config/3_cover.tex`; language and degree/specialization in `Config/1_novathesis.tex`. See
`thesis/README.md` for the template's own documentation (provenance, license — LPPL 1.3c,
institution-specific customization) if you need mechanics beyond what's above.

**Tables are GENERATED, not hand-typed.** `tools/gen_thesis_tables.py` writes `\input`-able
fragments into `thesis/Chapters/Tables/*.tex` from the CSVs (`zone_profiles.csv`, `zone_area.csv`,
`cmip6_zone_shift.csv`, `ahp_weights.csv` + `breakpoint_anchoring.csv` + `factor_discrimination.csv`,
the `derived:` block of `ahp_matrices.yaml`, `validation_zone_anova.csv`). The chapters keep the
float, caption and label and `\input` the body; the zone-indexed tables' **column count follows K
automatically**. Editing a fragment by hand is silently undone on the next run. `\input` paths are
relative to `thesis/` (latexmk's CWD) — `\input{Chapters/Tables/x.tex}`, since `\graphicspath`
does not apply to `\input`. Zone area shares come from `zone_area.csv` (a `pixelArea()` group
reduce), **never** from `zone_profiles.csv`'s `n`, which is a sample count and differs by ~6 points
on the largest zone.

**Figures:** `tools/make_figures.py` renders figures straight from the built EE assets
(`ee.Image.getThumbURL` thumbnails + matplotlib composition) into `thesis/Chapters/Figures/` — run
it after any asset re-export that changes a mapped layer, then re-`make` the PDF.
`tools/extract_present.py` writes the municipal-ranking table to the same tree
(`thesis/Chapters/Figures/municipal_ranking.csv`); `tools/gen_diag_csvs.py` writes its two
diagnostic CSVs one level up, in `thesis/Chapters/` (`$SCRATCHPAD` overrides both when set) — that's
where `make_figures.py`'s own diagram readers (`_read_diag`) look for them by default.

---

## 10. Post-parecer revision cycle

The dissertation went through a **post-parecer revision** (14 Sep → 2 Oct 2026), addressing 7
points raised in the examiner's report plus a set of author TODOs left in the text, ahead of a
final checkpoint with the adviser (Prof. Roberto Henriques). The day-by-day history and current
checklist state live in this artifact — read it with the `Artifact` tool (`action: "read"`) before
assuming what's done, since it's a live checklist, not a static plan:

**https://claude.ai/artifact/HrMpse386bFykBeBsBeJN6** ("Cronograma de revisão — tese")

The two dashboard follow-ups tracked here previously — i18n/image polish and enabling GitHub Pages
— are both done (§4). The artifact was rewritten on 2026-10-02 into a five-phase cycle (A1–A4 model
changes, rebuild, text reconciliation, form, conclusions); read it before assuming any point is
closed.

**Examiner point P4 (estado da arte) — chapter written 2026-10-02.** There was no state-of-the-art
section anywhere in the thesis; `thesis/Chapters/02_estado_arte.tex` (302 lines, `\label{ch:sota}`)
now covers FAO/GAEZ v4, ZARC + ZEE-GO, GIS-MCDA and the fuzzy/AHP extension, seven per-segment case
studies, data-driven modelling, cloud platforms, spatial validation, and closes on a five-axis
research gap plus `tab:estado-arte`. **The chapter files were renumbered** when it landed — Materiais
02→03, Metodologia 03→04, Resultados 04→05, Discussão 05→06, Anexo 06→07 — registered in
`thesis/Config/4_files.tex`. Nineteen keys that sat in the `.bib` without a single `\cite` are now
cited with locators, including the three added on 2026-10-02 for this chapter: `mapa_port_2026`
(Portaria SPA/MAPA 198/2026 — ZARC soja/Goiás, the primary source for the ZARC section),
`junior_indice_2009` (the ISNA definition) and the de-duplicated `balew_identification_2022`.
`sync_zotero_bib.py --check` passes; the only entry without a local PDF is the sanctioned
`da_silva_goias_suitability_2026`.

What remains is the Week 3 text work in the artifact: rewriting "Trabalhos futuros," a final
cross-chapter consistency pass, compiling the PDF, and the adviser checkpoint.

One decision worth keeping visible here rather than only in the artifact: examiner point 5 (climate
data at TerraClimate's ~4 km resolution vs. 250 m for everything else) was resolved by keeping
TerraClimate rather than swapping pipelines. A catalog spike found no viable higher-resolution
alternative with the right 1991–2020 climatology and variable set — WorldClim's climatology window
is 1960–1990 and it lacks PET/VPD/soil-moisture; CHIRPS/CHIRTS are single-variable and, at 0.05°
(~5.6 km), actually coarser than TerraClimate's 1/24° (~4.64 km); ERA5-Land/AgERA5 have the right
variables/period but sit at 0.1° (~9–11 km, 2×+ worse), and AgERA5 isn't in the official catalog.
The mismatch is now evidenced with a genuine spatial statistic instead of asserted in prose:
`theme_roughness_image()` in `src/features.py` computes local (moving-window) stdDev of the
z-scored feature-stack bands, grouped climate vs. terrain+soil, at three window radii (250 m /
750 m / 4,750 m, the last anchored to TerraClimate's own native pixel) — even at TerraClimate's own
scale, terrain+soil local variability is 42× climate's, rising to 320× at 250 m. Landed as
`fig:scale-mismatch`/`tab:scale-mismatch` in `thesis/Chapters/07_annex.tex`. `fig_4_12()` in
`tools/make_figures.py` deliberately plots a hexbin from `theme_roughness_points.csv` rather than a
`getThumbURL` raster — a full-AOI render of this moving-window computation at native 250 m exceeds
GEE's interactive compute/size limits, and pre-coarsening the input would smooth away the exact
fine-scale variance the figure exists to show. Don't "fix" this back to a thumbnail-based render.

---

## 11. Verify-at-build gotchas

- **Weights are DERIVED, never hand-set.** `config/segments.yaml`'s `weight:` fields are written by
  `tools/derive_weights.py` from the anchors in `config/ahp_matrices.yaml`. Editing one by hand is
  silently undone on the next run and caught by `--check`. The direction is
  `anchors -> matrix -> w_lit -> x sigma(mu)^lambda -> weight`; never the reverse. `tools/build_ahp.py`,
  which built the matrix *from* the weights (and so produced CRs of ~0.001 that were a construction
  artifact), is deleted — do not reintroduce that pattern. Protocol: `docs/ahp_literatura.md`.
- **Match breakpoints to the band's actual scale, not just literature.** Every moving fuzzy-
  membership breakpoint in `config/segments.yaml` is reconciled to its variable's realized
  percentile range (`tools/anchor_breakpoints.py percentiles`). `tools/anchor_breakpoints.py
  discrimination` is the check that matters: a factor whose `frac_saturated` is near 1 or whose
  `sigma_mu_available` is near 0 is inert, however large its nominal weight — that is how
  `sugarcane.soil_awc` was found sitting entirely below its own distribution (99.3% saturated at
  weight 0.22). `terr_slope` is in **degrees**.
- **`role: gate` is RETIRED — don't reintroduce it.** Seven factors (all climatic) have
  sigma(mu) = 0 **in the present** because the observed range sits inside their optimal plateau. An
  earlier method pulled them out of the AHP matrix and re-applied them multiplicatively, gated on two
  hand-chosen thresholds (sigma < 0.05 **and** mean mu > 0.95) — the exact subjectivity the derivation
  exists to remove. They are now kept in the matrix and weighted from `sigma_mu_horizon`: sigma(mu)
  measured over the present population **pooled with** the CMIP6 horizon, so a factor saturated today
  still earns weight if warming makes it grade. Five land at weight exactly 0 anyway (mu ≡ 1 in both
  populations). `segments.yaml` now carries `role: limiting` on all 33 factors and zero `gate`. The
  thing to preserve is the *reason*: weight 0 drops a factor out of the geometric mean **and takes its
  CMIP6 lever with it**, which is what the horizon pooling prevents.
- **Conservation is a value/priority index, not a native-cover detector.** It combines WDPA
  distance, ruggedness, and carbon (`feat_conservation`, routed via the `cv_` extras prefix, kept
  out of the stack/zoning like `feat_siting`'s `sit_` prefix) with demoted native-cover and moving
  climate factors, **aggregated by the compensatory arithmetic mean** (`aggregate: arithmetic` in
  `segments.yaml` → `membership.weighted_arithmetic`), not the geometric mean used by the other six
  segments. Don't revert to a native-cover-dominant, geomean-aggregated surface — that version was
  circular (native cover predicting "where native cover is") and CMIP6-invariant.
- **`split_mask(..., 'full')` returns `None`, not `ee.Image(1)`.** Every call site branches on
  `if mask is not None`, so `None` threads through unchanged AND leaves the full-domain graph
  bit-identical to the pre-holdout one. That bit-identity is the regression test for the whole
  holdout plumbing: `SPLIT_HALF=full tools/anchor_breakpoints.py discrimination` must reproduce the
  committed `factor_discrimination.csv` exactly. Don't "simplify" it to a constant image.
- **Restrict by MASK, never by `geometry=`.** Every reduction keeps `geometry=aoi`, so the two
  domains stay directly comparable (identical extent and tiling) and the guardrail that every
  exported product covers the whole AOI is untouched by construction. **Only parameter ESTIMATION is
  restricted to a half; the suitability/zoning/CMIP6 rasters always cover the full territory.**
- **`REBUILD_FORCE` must not name `aoi` or `feat_realized` while `$SPLIT_HALF` is set.** Both feed
  the split (the block grid bins the AOI bounds; the block roles were sampled from `feat_realized`),
  so re-exporting either would desynchronise the halves from `calib_val_blocks.csv` **without
  changing `calib_val_split`** -- nothing would error. `run_rebuild_full.py` raises on this.
- **An optional `half`/`*_val` column plus a stale CSV is a WRONG table, not a missing one.**
  `gen_thesis_tables._pivot_half`, its ANOVA reader and `make_figures.fig_4_10` used to fall back to
  the legacy column names so they would still render against a pre-holdout CSV. The result was
  `presence_auc.tex`, `spearman_npp.tex` and `fig_4_10.png` carrying full-domain **in-sample** numbers
  under held-out headings and axis labels — silently, with exit code 0. All three now `SystemExit`
  with the command to re-run. Don't reintroduce a fallback: when the artifact predates the holdout,
  the only correct output is a refusal.
- **`diff_breakpoints.py` measures the shift against `anchor.anchored_at`, not against the
  full-domain percentile.** `anchored_at` records, per point, the percentile VALUE the breakpoint is
  currently written against. Without it the gate is not idempotent — `delta` stays
  `pctl_calib − pctl_full` forever, so it keeps proposing an edit that is already in the file, which
  is how `cattle.clim_soil_moist` and `cattle.soil_soc` read as "never applied" after being applied.
  Re-stamp `anchored_at` whenever a breakpoint is re-anchored, in the same edit.
- **The measured autocorrelation range GROWS with the variogram window, so there is no finite
  range.** Residual range goes 105→150 km (soybean), 105→530 (sugarcane), 175→550 (other crops)
  between the 400 km and 800 km windows, and the share still coupled at the 130 km block goes
  11/15/30% → 30/46/66%. The thesis sizes the block from the 400 km window and **says so**
  (`anx:holdout`): at 800 km the far lags approach GO+DF's own diameter and measure the regional
  trend, not local structure. No block inside the territory removes a trend that crosses the whole
  territory. Quote both windows or neither.
- **(val − calib) is a BETWEEN-HALVES difference, not an optimism gap.** Blocks 1–4 of
  `run_validation.py` score ONE `suit_present` raster on two pixel sets, so the difference is
  territorial — which is why val scores *better* almost everywhere (soybean AUC 0.820→0.864, cattle
  rho 0.088→0.506), something no optimism can produce. Only `rf_kappa` is a genuine train/test
  contrast. The column is named `half_delta` for this reason; never relabel it "optimism".
- **`ari_subsample` is NOT `ari_holdout`.** `zoning.stability_sweep` fits each replicate on an 80%
  subsample and then relabels the FULL sample via `predict`, so it measures label reproducibility
  under resampling, never out-of-sample validity. `zoning.holdout_sweep` is the real thing: it fits
  on the calibration half and scores `silhouette_val` / `davies_bouldin_val` / `ari_holdout` on the
  held-out half. The k claim rests on the holdout columns. The PCA is fitted on the calibration rows
  only, for the same reason -- fitting it on everything leaks the held-out covariance into the space
  the holdout indices are measured in.
- **`derive_weights.py` reads the domain from `aggregation.derived_half` in `segments.yaml`.** The
  weights currently come from the calibration half, so a `--check` defaulting to `full` would report
  false drift on a correct config. The field is machine-written beside the weights; `--half`
  overrides it.
- **Breakpoints carry an `anchor:` block declaring HOW they were placed** -- `percentile` (9
  factors; the value IS a percentile of a named mask), `mu_one` (8; the ex-"gate" climate levers,
  placed so the present value gives mu = 1, so their check is "does mu = 1 still hold on the calib
  half", not "did a percentile move"), or `agronomic` (25; a physical threshold not drawn from this
  territory's distribution, hence domain-exempt). Several `agronomic` notes QUOTE percentiles as
  context -- that is evidence the threshold was checked against the distribution, not set from it.
  `tools/diff_breakpoints.py` acts only on the `percentile` ones.
- **Zoning is NOT independent of the AHP weights.** `zoning.build_sample` stratifies on
  `dominant_segment_band(suit, segments)` — the argmax over `suit_present`. New weights therefore
  give new strata, a new zoning sample, and a different k-selection panel even at identical seed.
  This is why `zoning_kselect.csv` peaked at k=6 under the old weights and at k=4 under the new
  ones, and why the panel MUST be regenerated (`tools/gen_diag_csvs.py zoning`) after any
  re-derivation, before any k claim is written. Suitability is still never a *clustering input* —
  only a stratum and a profiling column — so the §7 guardrail holds.
- **K-selection lives in one place: the full `k=2..20` panel in `zoning_kselect.csv`.** Current
  panel (2026-09-30): silhouette max k=4 (0.2097), ARI max k=4 (0.9882 ± 0.0036 — the tightest
  replicate spread in the sweep), Davies–Bouldin min k=5 (1.4629), gap's Tibshirani rule fires
  only at k=15 and is an artifact of a single dip. Silhouette spans just 0.158–0.210 across the
  whole sweep: **the territory has no strong natural cluster structure at any k**, so the
  clustering is a partitioning device, not a discovery of natural groups. Never quote a k claim
  from memory or from the prose — read the CSV.
- **Zone numbering is CANONICAL: descending mean `terr_elev`, not k-means++ init order.**
  `zoning.fit_kmeans(..., order_by=df[zoning.CANONICAL_ORDER_BAND])` permutes `cluster_centers_`
  **and** `labels_` so zone 1 is always the highest ground and zone K the lowest. Without it
  sklearn's label order is arbitrary and the same four zones come back under different numbers after
  any change to the sample, the weights or the PCA — which silently invalidates every "Zona N" in the
  prose while the generated tables renumber themselves, so the text and its own tables describe
  different zones. That had already happened twice (the committed prose described Zona 1 as the
  cultivation plateau while the table's Z1 column was the drained lowland). Every tool that exports
  `zones_present` passes `order_by`; if you add one, pass it too, and never re-sort labels downstream.
- **Zone ids: the `zones_present` raster is 0-based (0..K-1); everything else is 1-based (1..K).**
  The +1 is applied once, in `zoning.profile_zones`, so `zone_profiles.csv`, the thesis tables and
  prose, the figures and the dashboard all number zones from 1. The extract/validation tools shift
  their own raw-raster reads the same way. Don't add a second +1 downstream, and don't "fix" the
  raster to match — palette slot `i` paints raster value `i`, i.e. zone `i+1`.
- **`terr_twi` shares `terr_tpi`'s ~0.1% tile-edge export noise.** A full re-export moves both in
  ~0.1% of pixels (`focalMean`/`reproject` at tile boundaries, plus `to_grid_bilinear` for TWI).
  `terr_slope`, computed without resampling, is bit-identical across re-exports — which is how
  `tools/diff_vs_backup.py` distinguishes resampling noise from real catalog drift.
- **Part 10 clustering uses offline sklearn, NOT EE weka.** `ee.Clusterer.wekaKMeans` /
  `wekaCascadeKMeans` collapse to a single cluster on the collinear z-stack, every `init` mode.
  `src/zoning.py` fits sklearn KMeans on a sample, then classifies server-side by **nearest-centroid
  band math** (negative sq-distance → `arrayArgmax`), deterministic and label-identical to sklearn.
  Clustering runs on a **decorrelated** input (curated `ZONING_BANDS` → theme-weight ÷√bands →
  PCA≥90% var), classified in PC space — raw 34-band clustering collapses to a handful of
  low-expressiveness zones. Don't "fix" it back to weka or raw-band clustering.
- **Zone label is `comparative_segment`, not `dominant`/`distinctive`.** Zones are labelled by
  argmax of each segment's **z-normalized** suitability (`membership.comparative_present` /
  `zoning.comparative_suitability`), not raw absolute suitability — after forage recalibration,
  cattle no longer wins the absolute argmax everywhere, so a raw-dominance label would be
  misleading.
- **Part 11 ΔSuitability subtracts a *rederived* present, never the `suit_present` asset.**
  `cmip6.suit_present_rederived` recomputes present suitability on-the-fly (same path as the
  future) so the baseline derivation cancels analytically — identity change-factors then give
  Δ=0.000. Subtracting the *exported* asset instead injects a constant export-reprojection offset.
  Don't "simplify" the notebook to use the asset directly.
- **Part 11 future climate reuses `features.derive_climate_bands`.** CMIP6 change factors (pr
  ratio, additive K Δ for tasmax/tasmin) are applied to the TerraClimate **monthly** baseline; PET
  uses a Hargreaves *ratio* (no latitude/solar-geometry math needed — it cancels). `srad` and
  `clim_soil_moist` are **held at baseline** (rsds is outside the pr/tasmax/tasmin ensemble; soil
  moisture needs a full water balance) — documented caveats, not bugs to fix casually.
- **CMIP6 reductions are compute-heavy.** A single-point `getInfo` of full 5-GCM × 20-yr monthly
  climatologies can run well over 10 minutes interactively — validate any engine change with
  synthetic/identity factors first, and run the real projection only as **batch exports**. If a
  task stalls, cache the ensemble future-climate (or change-factor) image as an intermediate asset
  first, then suitability is cheap.
- **`utils.export_table` has NO overwrite path** (unlike `export_image(..., overwrite=True)`).
  Re-exporting a table asset that already exists FAILS with *"Cannot overwrite asset"* — **delete
  the old asset first** (`ee.data.deleteAsset`), then submit.
- **Two MOD17 products, two roles.** (1) **NPP** `MODIS/061/MOD17A3HGF` band `Npp` = the annual
  productivity proxy for the municipal Spearman check — productivity *context* only, confounded for
  crops. (2) **GPP** `MODIS/061/MOD17A2HGF` band `Gpp`, integrated over the Oct–Mar canopy window on
  each crop's own realized pixels = the within-crop validator (`external.season_gpp` +
  `metrics.within_crop_gradient`). Presence AUC/Boyce remain the primary crop validators.
- **Validation is compute-heavy — use cached assets + `tileScale`.** Feeding live graphs
  (`external.realized_features` = 30 m MapBiomas remap; `season_gpp`; RF classify) into 10–20k-pixel
  `.sample().getInfo()` hits the interactive memory limit AND the 5000-element getInfo cap. Use the
  cached `feat_realized` asset (has `rl_role` + fracs), `tileScale=8`, and cap samples ≤4500. See
  `tools/run_validation.py` / `tools/extract_*.py`.
- **TWI breakpoints are data-anchored, so no manual offset is needed any more.**
  `conservation.terr_twi` is set from the observed P10–P90 (`anchor_breakpoints.py discrimination`),
  not from a literature value plus a hand-written `+ln(dx/250)` correction. If the HydroSHEDS
  nominal scale changes again, re-run that tool and then `derive_weights.py`; there is no constant
  left to keep in step. The paragraph below records why the shift once existed.
- **TWI's catchment area uses the HydroSHEDS cell (≈464 m), not the 250 m grid step.**
  `terrain_features` computes a = (n+1)·Δx with Δx = the 15ACC image's `nominalScale()`, because n
  counts HydroSHEDS cells. Until 2026-09-26 it used `scale_m()`, a constant −0.618 offset. The fix
  was a pure additive shift: the z-stack, the zoning and the RF were unchanged, and the conservation
  `terr_twi` breakpoints in `segments.yaml` were moved by the same +0.618 so membership is identical.
  Only `feat_terrain` and `feature_stack_250m` were re-exported, as the backup
  (`goias_backup_20260926_twi`) with `terr_twi += ln(Δx/250)` exactly. A full rebuild would also
  have moved `terr_tpi` in ~0.1% of pixels (tile-edge export noise in `focalMean`/`reproject`).
  If you change Δx again, shift those breakpoints with it.
- If a layer looks displaced/mis-scaled in a notebook map preview, that's usually a
  `reproject`-pinned `Map.addLayer` artifact, not a real error — load the asset directly
  (`ee.Image('projects/probformer/assets/goias/<name>')`) and it renders correctly over Goiás.
- **`zoning.build_strat_band()` must cast its grid-cell-id band to int.** Built via
  `.floor()`/`.clamp()`/`.multiply()`/`.add()`, it needs an explicit `.toInt()` before
  `ee.Image.stratifiedSample(classBand=...)` — EE rejects a non-integer class band. `zoning.
  build_sample()` already applies its own `.toInt()`, but any new caller of `build_strat_band()`
  directly needs to do the same.

---

## 12. Bibliography & PDFs as the primary citation source

**Zotero is the source of truth for the bibliography.** Its BibLaTeX export lives at
`thesis/Bibliography/zotero_bibliography.bib`, with every attachment under
`thesis/Bibliography/zotero_storage/<ID>/`. Both are **local-only and gitignored**
(`thesis/Bibliography/zotero*`) because of copyright. `bibliography.bib` (loaded by
`Config/4_files.tex`) is **generated** from that export, committed so the thesis builds anywhere,
and **never edited by hand**. A new source or a field correction goes into Zotero, gets
re-exported to the same path, and then:

```bash
uv run python tools/sync_zotero_bib.py           # regenerate bibliography.bib (+ key check, PDF report)
uv run python tools/sync_zotero_bib.py --check   # report only, writes nothing
```

The script strips `file`/`abstract`/`keywords`/`urldate`/`shorttitle`, so no local Windows paths
and no abstract text reach the public repo or the APA list. It **refuses to write** (exit ≠ 0) if
any `\cite*{}` key in `Chapters/`/`Config/` is missing from the export. If a Zotero re-export
changes a key (e.g. after you give an item an author), `--rewrite-keys` remaps the `\cite`s by DOI
or title from the current `bibliography.bib`. Before running it, commit or back up that file.

**Citation keys** follow Zotero's native format, `author_titleword_year`
(`abatzoglou_terraclimate_2018`). The pre-Zotero keys (`Abatzoglou2018`) were migrated on
2026-09-26. When Zotero has duplicates (it adds a `-1` suffix), cite the unsuffixed key and merge
the items in Zotero.

**The PDF is the primary source for every citation.** Before you write or change a sentence that
cites a source:
1. Find its PDF: the entry's `file` field in `zotero_bibliography.bib` has the form
   `C:\…\Zotero\storage\<ID>\<name>.pdf`, which resolves locally to
   `thesis/Bibliography/zotero_storage/<ID>/<name>.pdf`.
2. Read the relevant passage in the PDF itself (Read with `pages`, or the `pdf` skill). Never
   cite from memory, the abstract, or the `.bib` metadata.
3. When the claim is a specific datum, use a locator: `\citep[p.~X]{key}`, a table, or an
   equation. Examples: AHP weights/matrices from other studies, Saaty's random-index table,
   the Landis & Koch κ bands, GAEZ/ZARC classes and thresholds, Spawn's resolution/reference
   year.
4. An entry with no local PDF (`sync_zotero_bib.py` lists them) must not back a new claim. Flag
   it and ask for the attachment. The only accepted exception is `da_silva_goias_suitability_2026`
   (the repo itself).
5. PDFs never leave the machine: not into git, not into artifacts, not to external services.
   Only the key and the citation go into the thesis.

This is the "Fonte primeiro" rule of the revision schedule (§10 artifact): a lilac step (AHP
rewrite, state of the art, spatial validation, conclusions, bibliography) starts only once its
sources are in Zotero **with a PDF** and the passage to cite is noted.
