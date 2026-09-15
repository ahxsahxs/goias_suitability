# CLAUDE.md — Goiás Agro-Market Suitability & CMIP6 Zoning

Single entry point for this project. It explains **what the project is, how it's built, how to run
it, and where it currently stands.** Deep detail lives in three companion docs under [`docs/`](docs/):

| Doc | What it is |
|---|---|
| [`docs/methods.md`](docs/methods.md) | **Rationale, research questions, methodology, validation theory, risks** (the "why"). |
| [`docs/execution_plan.md`](docs/execution_plan.md) | **The build runbook** — Parts 1–15 with inputs, GEE ops, cached outputs, definition-of-done. **The Part ⇄ notebook ⇄ src map lives here.** |
| [`docs/phase_b_data.md`](docs/phase_b_data.md) | **Phase B data runbook** (GEE-only): MapBiomas + GAUL L2 + MOD17 catalog datasets, verify-at-build checks, realized-use/validation steps. |

> **These three docs are the source of truth; code follows them.** When asked to change
> methodology, update the relevant doc first, then the code.

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
MODIS MOD17 productivity proxy. Full treatment in [`docs/methods.md`](docs/methods.md).

**Research questions** (detail in [`docs/methods.md`](docs/methods.md) §1):
- **RQ1 — suitability & segmentation:** how is GO/DF partitioned into agro-environmental zones, and
  what is each zone's potential-productivity profile across the seven segments?
- **RQ2 — potential vs. realized:** where does realized use (MapBiomas) / the MOD17 proxy diverge
  from modeled potential — i.e. where is land under-utilized or mismatched?
- **RQ3 — forecast:** under CMIP6 SSP2-4.5 / SSP5-8.5, how do suitability and zones shift by
  2031–2050 and 2051–2070 — winners, losers, cross-segment reallocation?

## 2. Platform & cost philosophy

**Everything runs server-side in Earth Engine** (free non-commercial / research tier). The local
machine is only for charts, table joins, and writing — no GPU, no large local archive, no cloud-ML
bill. Only small artifacts leave GEE (250 m GeoTIFFs to Drive, CSV sample/summary tables for
matplotlib). As of the **2026-06-07 redesign the pipeline is fully GEE-native — zero external
uploads** (all IBGE dependence dropped; see §9).

---

## 3. Phasing

- **Phase A — GEE-native core (the potential atlas).** AOI + six continuous feature themes + a
  generic land-cover mask + the 250 m feature-stack, then knowledge-based suitability, unsupervised
  zoning, **and** the CMIP6 forecast. Produces a complete *unvalidated* potential atlas + 2050
  projection from the bare catalog. **Parts 1–11.**
- **Phase B — Realized-use & validation (GEE-only).** Brings in MapBiomas land use, GAUL-L2
  municipalities, and the MOD17 productivity proxy — for masking, potential-vs-realized analysis,
  productivity validation, the data-driven RF cross-check, and municipal decisions. **Parts 12–15.**

The split is *biophysical potential* (A) vs *realized-use & validation* (B) — not catalog-vs-upload
(nothing uploads anymore).

## 4. Execution status — project `probformer` (as of 2026-07-16)

**Phase A + Phase B modelling complete AND both the robustness+recalibration AND the examiner-proofing
iterations are EXECUTED — Parts 1–14 BUILT & footprint-verified (31 EE assets). All three RQs answered
and written into the thesis (chapters 01–05). The only remaining build item is Part 15 (atlas App).
The examiner-proofing iteration (2026-07-25) RECONCEPTUALIZED conservation, made AHP auditable, added
spatial-CV validation + diagnostics. Full audit trails: [`docs/robustness_changelog.md`](docs/robustness_changelog.md)
+ [`docs/weaknesses_mitigation.md`](docs/weaknesses_mitigation.md).**

| Part | State | Notes |
|---|---|---|
| 1–8 | **BUILT & footprint-verified** | Ten assets incl. `feature_stack_250m(_z)` (**34 bands** each) + **`feat_siting`** (2 bands: `sit_clearness`, `sit_water_dist_seas`; kept OUT of the stack). |
| 9 — suitability | **BUILT & RECONCEPTUALIZED (2026-07-25)** | `suit_present`/`_comp`/`_sens`. Crops/cattle/solar/pisci unchanged from recal (S2+ 62.2/60.8/64.2/10.0/63.1/27.3). **Conservation reconceptualized** → conservation-VALUE index (cv_pa_dist WDPA / cv_ruggedness / cv_carbon side bands via `feat_conservation`, `cv_` routing + moving `clim_aridity`+`clim_twarm_q`; native_frac demoted 0.35→0.08; **arithmetic aggregation**). Conservation S2+ **5.3%→33.2%**. |
| 10 — zoning | **BUILT — K=7 (2026-07-25 re-profiled)** | `zones_present` **K=7** (forced, not the auto-pick K=8 — k=7 dominates on DB+stability, `tools/rezone.py`). Decorrelated PCA flow unchanged (stack untouched → cluster assignments identical). **Conservation now WINS zone 6** (dominant + comparative). `zone_profiles.csv` + `zoning_kselect.csv` (validity+ARI-stability). |
| 11 — CMIP6 shift | **BUILT & RE-EXPORTED (2026-07-25)** | 12 assets. **Conservation is now the MOST climate-EXPOSED segment** (ΔS −0.106, S2+ 33.2%→11.4%; via moving aridity+twarm) — NO structurally-invariant segment remains. Other-crops/solar unchanged losers. Delta-change engine still validated (identity → Δ=0.000). NB `clim_def_annual`/`soil`/`srad` held static → aridity (not CWD) is conservation's moving lever. |
| 12–14 — Phase B | **BUILT & RE-EXPORTED (2026-07-25)** | `realized_vs_potential`, `municipal_godf` re-aggregated (K=7 + new conservation). Validation: soybean AUC 0.83 (**spatial-block mean 0.79**), sugarcane pooled 0.83 but **block-mean 0.61** (spatial-sorting), RF κ in-sample 0.23 / **out-of-block 0.07**, conservation Spearman-vs-NPP **+0.47** (was +0.34), zone-6 native cover **77.7%**. AHP CR ≤0.002 all segments (`config/ahp_matrices.yaml`). |
| 15 — synthesis | **NOT built** | Atlas App (`gee_js/`). Figures already regenerated via `tools/make_figures.py`; municipal ranking in `docs/thesis/figures/municipal_ranking.csv`. |

- **Backup before recal:** all pre-recal assets copied server-side to
  `projects/probformer/assets/goias_backup_20260714_pre_recal` (`tools/backup_assets.py`).
- **Built assets** (`projects/probformer/assets/goias/`, **31 total**): the 28 originals + **`feat_siting`**
  + **`suit_present_comp`** + **`feat_conservation`** (cv_pa_dist/cv_ruggedness/cv_carbon). Ranges verified sane.
- **Backup before conservation reconceptualization:** `goias_backup_20260725_pre_consv` (31 assets).
- **Examiner-proofing tools:** `tools/build_ahp.py` (AHP matrices), `tools/anchor_conservation.py`,
  `tools/run_conservation_recal.py` (re-export cascade), `tools/rezone.py` (K=7 force), `tools/run_ws_analysis.py`
  (spatial-CV + variance decomp).
- **Recal extraction tools:** `tools/anchor_breakpoints.py` (percentile audit that drove the breakpoints),
  `tools/run_recal.py` (re-export cascade orchestrator), `tools/run_validation.py` (Part 14 stats),
  `tools/extract_present.py` + `tools/extract_cmip6.py` (all §4 table numbers).
- **Footprint-verified:** `tools/verify_assets.py` (metadata-only — runs even under restricted
  compute quota) confirms every asset is **EPSG:4326 @ 250 m (0.002246°)** with the exact GO+DF
  footprint (lon [-53.25, -45.90], lat [-19.50, -12.39]) — no displacement / scale error.
  ```bash
  EE_PROJECT=probformer ../.venv/bin/python tools/verify_assets.py
  ```
- **Part 9 config fix (APPLIED 2026-06-19):** `water_drain_density` breakpoints were `[0.05, 0.30]`
  but the band is a stream-cell *fraction* (max ~0.15) → the factor never fired, flooring
  pisciculture/conservation. `config/segments.yaml` carries the fix (`[0.01, 0.08]`) and
  **notebook 09 has been re-run with it, so the exported `suit_present` / `suit_present_sens` now
  reflect the corrected breakpoints.** No further action needed.

> If a layer looks displaced/mis-scaled in a notebook map, that's a `reproject`-pinned
> `Map.addLayer` *preview* artifact — load the asset directly
> (`ee.Image('projects/probformer/assets/goias/<name>')`) and it renders correctly over Goiás.

**Immediate next steps:** the robustness+recalibration iteration is fully executed — Parts 1–14 rebuilt
on recalibrated surfaces, Part 14 validation re-run, and all §4 tables + 9 figures + methods (§3.3/§3.5/
§3.7) + discussion (§5) regenerated to match. Only remaining work:
1. **(build)** Part 15 synthesis — the free GEE App (`gee_js/`). Atlas figures (present + future) are
   already rendered (`tools/make_figures.py`); the municipal opportunity/vulnerability ranking is in
   `docs/thesis/figures/municipal_ranking.csv`.

Per-part detail in [`docs/execution_plan.md`](docs/execution_plan.md).

---

## 5. Layout

```
config/datasets.yaml          # pinned EE dataset IDs, bands, scale factors (single source of truth)
config/segments.yaml          # Part 9: per-segment fuzzy-membership params + AHP weights + masks
config/mapbiomas_classes.yaml # MapBiomas code -> segment-role remap (Phase B, Part 13)
src/utils.py                  # EE init, config loader, 250 m grid, asset/export helpers
src/features.py               # ALL Part 1-8 feature builders (one source of truth; lazy ee, import-safe). derive_climate_bands() is reused by Part 11
src/membership.py             # Part 9 suitability engine: fuzzy membership + geomean + FAO + AHP/sensitivity
src/zoning.py                 # Part 10 zoning: sklearn KMeans (offline) + server-side nearest-centroid + profiling
src/cmip6.py                  # Part 11 CMIP6 delta-change: change factors + future climate + future suitability + Δ + ensemble agreement + hindcast bias
tools/gen_notebooks.py        # regenerates notebooks from a spec; optional arg = only that notebook
tools/run_phase_a.sh          # executes 01->08 in order, waits for exports, assembles stack
tools/wait_for_assets.py      # blocks until named EE assets exist (gates the stack step)
tools/verify_assets.py        # metadata-only footprint/CRS/scale check of built assets (no compute)
notebooks/01..11              # thin: import src/, build, range-report, view, export
docs/                         # methods.md, execution_plan.md, phase_b_data.md (source-of-truth design docs)
data/                         # local archive / offline cross-check only (see §10)
gee_js/                       # empty; optional Code Editor mirror
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
08_feature_stack.ipynb        -> Part 8   (src/features.py: STACK_THEMES)
09_suitability_fuzzy_ahp.ipynb-> Part 9   (src/membership.py + config/segments.yaml)
10_zoning_kmeans.ipynb        -> Part 10  (src/zoning.py)
11_cmip6_shift.ipynb          -> Part 11  (src/cmip6.py)
12_municipal_gaul.ipynb       -> Part 12  (src/external.py)        ┐
13_mapbiomas.ipynb            -> Part 13  (src/external.py)        ├ Phase B — BUILT
14_validation_proxy_rf.ipynb  -> Part 14  (src/external.py+metrics)┘
15_atlas_app.ipynb            -> Part 15  (tools/make_figures.py + gee_js/)  ── NOT built yet
```

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
| 8 | 08_feature_stack | `feature_stack_250m`, `feature_stack_250m_z` | raw + z-scored 34-band stack (land cover excluded) |
| 9 | 09_suitability_fuzzy_ahp | `suit_present`, `suit_present_sens` | 7 `suit_*` (0–1) + 7 `class_*` (FAO S1/S2/S3/N) + 7 `sens_*` (±20% AHP) |
| 10 | 10_zoning_kmeans | `zones_present` (+ `zone_profiles.csv`) | biophysical zones (offline KMeans, nearest-centroid classify) + profile cards |
| 11 | 11_cmip6_shift | `suit_future_*`, `delta_*`, `agreement_*` | future suitability per SSP/window, Δ, GCM ensemble agreement |
| 12–15 | 12..15 | `municipal_godf`, `feat_realized`, `realized_vs_potential`, … | Phase B (see [`docs/phase_b_data.md`](docs/phase_b_data.md)) |

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
  conservation uses `lc_tree_frac` as a *supportive* factor (per the Part 9 spec); no other segment
  consumes a land-cover band.
- **MapBiomas (Phase B) is mask + validation + descriptive profiling only** — same guardrail; it
  never becomes a suitability/clustering input even as its use expands.
- **Small artifacts only leave GEE** (GeoTIFFs to Drive, CSV sample/summary tables for matplotlib).

## 8. Environment & running

**Always run Python through the workspace venv at `../.venv` (clay root), never system Python, and
always with `EE_PROJECT=probformer` set.** Two equivalent ways:

```bash
# A) per-command (preferred for one-offs and scripts)
EE_PROJECT=probformer ../.venv/bin/python <script.py>

# B) activate the venv once, then `python ...` for the rest of the session
source ../.venv/bin/activate            # bash/zsh
source ../.venv/bin/activate.fish       # fish (this shell)
set -x EE_PROJECT probformer            # fish;  bash/zsh: export EE_PROJECT=probformer
python <script.py>
```

Jupyter kernel name is `goias`. Earth Engine needs a live login first. EE project resolves from
`$EE_PROJECT` → the credentials file; current project: **`probformer`** — keep it set so assets
resolve under `projects/probformer/assets/goias/`.

```bash
# one-time setup (venv already created at ../.venv)
../.venv/bin/pip install earthengine-api geemap pandas numpy matplotlib scikit-learn \
                         pyyaml nbformat nbconvert ipykernel
../.venv/bin/python -m ipykernel install --user --name goias --display-name "Python (goias)"

# authenticate (interactive OAuth — suggest `! ...` to run in-session)
../.venv/bin/earthengine authenticate

# run Phase A headless: executes 01->08, submits exports, waits, assembles the stack
bash tools/run_phase_a.sh
../.venv/bin/earthengine task list        # monitor async export tasks

# regenerate notebooks after editing src/features.py
../.venv/bin/python tools/gen_notebooks.py

# metadata-only asset check (runs under restricted quota)
EE_PROJECT=probformer ../.venv/bin/python tools/verify_assets.py
```

Parts 9+ load the cached `feat_*` / stack assets directly, so they don't recompute upstream graphs.

---

## 9. Phase B redesign — GEE-only modelling (DECIDED 2026-06-07)

Phase B's data sources were reworked: **all IBGE dependence is dropped** and the
modelling/validation stage is **exclusively GEE-native (zero uploads)**. Decisions:

1. **Fully GEE-native.** Drop IBGE PAM, PPM, *and* the municipal-mesh upload. Municipal aggregation
   uses **GAUL level-2** (`FAO/GAUL_SIMPLIFIED_500m/2015/level2`) from the catalog.
2. **Validation = productivity proxy + composition.** Replace IBGE yield validation with a **MODIS
   MOD17 GPP/NPP productivity proxy** (Spearman vs municipal mean suitability, cropland-restricted)
   **plus** descriptive **MapBiomas realized-use composition profiling** conditioned on the
   zones/suitability.
3. **Strictly descriptive — guardrail holds.** Composition profiling + the RF presence cross-check
   stay validation-only; MapBiomas/land cover never becomes a suitability or clustering input. RQ1/RQ2
   independence is preserved.

**Caveats baked into the docs:** (a) the in-stack NDVI integral (`phen_integral`) is a suitability
input, so it **cannot** be the productivity validator — MOD17 is used instead, with a noted residual
shared-signal caveat; (b) MOD17 is *vegetation productivity, not agronomic yield* — an explicit
limitation. Full Phase B plan in [`docs/phase_b_data.md`](docs/phase_b_data.md).

## 10. Data on disk (`data/`) — archive / cross-check only

- `ibge-malha_municipal/GO_DF_Municipios_2025.gpkg` — **DEPRECATED/unused** (kept as archive). The
  GEE-only redesign aggregates municipalities from **GAUL level-2** instead of uploading this mesh.
- `mapbiomas-lulc/` — Collection 10.1 GeoTIFFs, **GO clip only (DF masked to 0)**, 2016–2024, 30 m.
  Offline cross-check only; the **GEE-hosted MapBiomas asset** (covers GO+DF, all years) is the
  pipeline source. Plus a precomputed class-area CSV.
- `ibge-pam/tabela1612.xlsx` — **DEPRECATED/unused** (kept as archive). IBGE PAM/PPM productivity is
  dropped; suitability is validated against the **MOD17 productivity proxy** + MapBiomas realized use.

The old `tools/prep_mesh.sh`, `tools/fetch_sidra.py`, and the `datasets.yaml` `mesh:`/`ibge:` sections
have been removed. `config/mapbiomas_classes.yaml` stays valid.

## 11. Verify-at-build gotchas

- **Soil scale factors:** some OpenLandMap factors in `datasets.yaml` were tagged `VERIFY` (SOC, bulk
  density, pH) and are now confirmed (inline comments). The verify cell in `01_setup_aoi.ipynb` prints
  band names; each feature notebook's `range_report` prints band min/mean/max — if a range looks off,
  fix the scale in `datasets.yaml` and re-run that notebook.
- **MapBiomas GEE asset id — CONFIRMED collection 10** (`.../collection10/mapbiomas_brazil_collection10_integration_v1`,
  1985–2024, covers GO+DF); legend codes verified against `mapbiomas_classes.yaml`.
- **Suitability breakpoints (`segments.yaml`) are RECALIBRATED (2026-07-16)** — each moving breakpoint
  reconciled to its variable's realized percentile range via `tools/anchor_breakpoints.py` (crops
  tightened to the realized niche; cattle forage-graded; solar rescaled + clearness + heat de-rate;
  pisci → seasonal water). Before→after tuples in `docs/robustness_changelog.md`. `terr_slope` is in
  **degrees**.
- **Match breakpoints to the band's actual scale, not just literature** — the `water_drain_density`
  bug was a unit/scale mismatch (band is a 0–~0.15 fraction; breakpoints assumed ~0–0.3). The 2026-07
  recalibration generalized this into a percentile audit of every moving factor. Always check a band's
  real range (`range_report` / percentile `reduceRegion`) before trusting nominal breakpoints.
- **Conservation RECONCEPTUALIZED to a value/priority index (2026-07-25) — supersedes the earlier
  native-cover fix.** It was circular (native_frac + phen_amplitude = "where native veg is", 0.52 weight)
  and CMIP6-invariant. Now a conservation-VALUE index: side bands `cv_pa_dist` (WDPA distance),
  `cv_ruggedness` (SRTM elev-std), `cv_carbon` (biomass) in **`feat_conservation`**, routed via the `cv_`
  extras prefix (kept OUT of the stack/zoning, like `sit_`); moving climate factors `clim_aridity`(inc)
  + `clim_twarm_q`(dec); native_frac **demoted 0.35→0.08** (still the one sanctioned land-cover input);
  `phen_amplitude` dropped. **Aggregated by the compensatory arithmetic mean** (`aggregate: arithmetic`
  in segments.yaml → `membership.weighted_arithmetic`), NOT the geometric mean — conservation value is
  compensatory (any strong criterion), which is what lifts S2+ 5.3%→33.2%. Other 6 segments keep geomean.
  Don't revert to the native-cover-dominant surface.
- **Part 10 clustering uses offline sklearn, NOT EE weka.** `ee.Clusterer.wekaKMeans` /
  `wekaCascadeKMeans` collapse to a single cluster on the collinear z-stack, every `init` mode.
  `src/zoning.py` fits sklearn KMeans on a sample, then classifies server-side by **nearest-centroid
  band math** (negative sq-distance → `arrayArgmax`), deterministic and label-identical to sklearn.
  **Don't "fix" it back to weka.** As of 2026-07-16 clustering runs on a **decorrelated** input
  (curated 15-band `ZONING_BANDS` → theme-weight ÷√bands → PCA≥90% var), classified in PC space; this
  gave **k=7** (was 3). Raw 34-band clustering collapses to 3 low-expressiveness zones — don't revert.
- **Zone label is `comparative_segment`, NOT `dominant`/`distinctive` (2026-07-16).** After the cattle
  forage recalibration, cattle no longer wins the absolute argmax everywhere. Zones are labelled by
  `comparative_segment` = argmax of each segment's **z-normalized** suitability (`membership.comparative_present`
  / `zoning.comparative_suitability`). The old `distinctive_segment` crutch is retired.
- **Part 11 ΔSuitability subtracts a *rederived* present, never the `suit_present` asset.**
  `cmip6.suit_present_rederived` recomputes present suitability on-the-fly (same path as the future)
  so the baseline derivation cancels analytically — identity change-factors then give Δ=0.000.
  Subtracting the *exported* asset instead injects a constant export-reprojection offset
  (±0.05–0.3, e.g. a spurious +0.10 on solar, which has **no** climate factor). Don't "simplify" the
  notebook to use the asset.
- **Part 11 future climate reuses `features.derive_climate_bands`** (extracted from `climate_features`
  in a behavior-preserving refactor — recomputed baseline matches `feat_climate` to ~0.1% resample
  noise). CMIP6 change factors (pr ratio, additive K Δ for tasmax/tasmin) are applied to the
  TerraClimate **monthly** baseline; PET uses a Hargreaves *ratio* (the 0.0023·Ra term cancels, so no
  latitude/solar-geometry math). `srad` and `clim_soil_moist` are **held at baseline** (rsds is outside
  the pr/tasmax/tasmin ensemble; soil moisture needs a full water balance) — documented caveats.
- **NO structurally-invariant segment remains (2026-07-25).** Solar moves via `clim_twarm_q` (ΔS −0.06);
  **conservation is now the MOST climate-EXPOSED segment** (ΔS −0.106, S2+ 33.2%→11.4%) via its moving
  `clim_aridity`+`clim_twarm_q`. **Gotcha:** `cmip6.future_monthly` holds `def`/`soil`/`srad` STATIC, so
  `clim_def_annual` (CWD) does NOT move — conservation's water lever is **`clim_aridity` (P/PET, both
  terms move)**, not CWD. The static `sit_`/`rl_`/`cv_` side factors are threaded through CMIP6 via
  `extras` and held at baseline so Δ isolates the climate signal (conservation's `cv_` bands held static).
- **CMIP6 reductions are compute-heavy.** A single-point `getInfo` of full 5-GCM × 20-yr monthly
  climatologies ran >15 min interactively (killed) — validate the engine with synthetic/identity
  factors (no NEX-GDDP daily reduction) and run the real projection only as **batch exports**. If a
  task stalls, cache the ensemble future-climate (or change-factor) image as an intermediate asset
  first, then suitability is cheap.
- **Phase B is built + recalibrated:** `src/external.py`, `src/metrics.py`, notebooks 12–14, and
  `tools/make_figures.py` all exist. The only code not yet created is Part 15's `gee_js/` App script.
- **`utils.export_table` has NO overwrite path** (unlike `export_image(..., overwrite=True)`).
  Re-exporting a table asset that already exists FAILS with *"Cannot overwrite asset"* — **delete the
  old asset first** (`ee.data.deleteAsset`), then submit. This bit the `municipal_godf` re-export.
- **RF cross-check (recalibration DONE, 2026-07-16):** after recalibration the knowledge map is still
  more permissive than the realized niche but less so — soybean **60.8% S2+ vs RF 25.3%**, Cohen's
  **κ=0.23** (was 0.20). This is now a *documented finding*, not a to-do: GO is climatically uniform, so
  soil/terrain are the only tightening levers and the residual is partly the RQ2 (suitable-but-unused)
  signal. Don't chase κ≥0.4 by loosening the guardrails.
- **Two MOD17 products, two roles.** (1) **NPP** `MODIS/061/MOD17A3HGF` band `Npp` = the annual
  productivity proxy for the municipal Spearman check — correlates +ve with standing-biomass segments,
  confounded for crops; productivity *context* only. (2) **GPP** `MODIS/061/MOD17A2HGF` band `Gpp`,
  integrated over the Oct–Mar canopy window on each crop's own realized pixels = the **repaired
  within-crop validator** (`external.season_gpp` + `metrics.within_crop_gradient`) — retired the
  spurious soybean −0.34 (now +0.003). Presence AUC/Boyce remain the primary crop validators.
- **Validation is compute-heavy — use cached assets + `tileScale`.** Feeding live graphs
  (`external.realized_features` = 30 m MapBiomas remap; `season_gpp`; RF classify) into 10–20k-pixel
  `.sample().getInfo()` hits the interactive memory limit AND the 5000-element getInfo cap. Use the
  cached `feat_realized` asset (has `rl_role` + fracs), `tileScale=8`, and cap samples ≤4500. See
  `tools/run_validation.py` / `tools/extract_*.py`.
