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
MODIS MOD17 productivity proxy. Full treatment in `thesis/Chapters/03_methodology.tex`.

**Research questions** (full treatment in `thesis/Chapters/01_introduction.tex` and
`03_methodology.tex`):
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

**Phase A + Phase B modelling are complete — Parts 1–14 BUILT & footprint-verified.** All three
RQs are answered and written into the thesis (chapters 01–05). The only remaining build item is
**Part 15 (atlas App)** — the Earth Engine App script is written (`gee_js/atlas_app.js`) but not
yet published from the Code Editor.

| Part | State | Notes |
|---|---|---|
| 1–8 | **BUILT & footprint-verified** | Ten feature assets incl. `feature_stack_250m(_z)` (34-band stack) + `feat_siting` (solar clearness / seasonal water distance) + `feat_conservation` (WDPA distance / ruggedness / carbon) — the latter two are side-images kept **out** of the stack (routed into suitability via the `sit_`/`cv_` extras prefix). |
| 9 — suitability | **BUILT** | `suit_present` / `suit_present_comp` / `suit_present_sens`: 7 `suit_*` (0–1) + 7 `class_*` (FAO S1/S2/S3/N) + 7 `sens_*` (±20% AHP). Conservation is a value/priority index (arithmetic-mean aggregation — compensatory); the other six segments use the weighted geometric mean. |
| 10 — zoning | **BUILT — K=7** | `zones_present`, offline sklearn KMeans on a decorrelated PCA input (`src/zoning.py`), classified server-side by nearest-centroid band math. Zones labelled by `comparative_segment` (argmax of each segment's z-normalized suitability), not raw dominance. `zone_profiles.csv` + `zoning_kselect.csv`. |
| 11 — CMIP6 shift | **BUILT** | `suit_future_*`, `delta_*`, `agreement_*` assets across SSP2-4.5/SSP5-8.5 × 2031–2050/2051–2070 × 5-GCM ensemble. Delta-change engine validated against an identity change-factor (Δ=0.000). No structurally climate-invariant segment remains — every segment (including conservation and solar) moves under at least one climate lever. |
| 12–14 — Phase B | **BUILT** | `realized_vs_potential`, `municipal_godf` (IBGE malha municipal aggregation), MOD17 productivity validation (municipal Spearman + within-crop GPP gradient), RF presence cross-check, AHP consistency ratios. See `config/ahp_matrices.yaml` and `thesis/Chapters/04_results.tex` / `05_discussion_conclusion.tex` for the numbers. |
| 15 — synthesis | **App script written, NOT published** | `gee_js/atlas_app.js` (present suitability, zones, realized use, CMIP6 shift, municipal click-to-read) is ready; publishing from the GEE Code Editor is the one remaining manual step. Figures already regenerated via `tools/make_figures.py` into `thesis/Chapters/Figures/`. |

- **Asset backups:** pre-recalibration and pre-reconceptualization snapshots were copied server-side
  under `projects/probformer/assets/goias_backup_*` before each major re-export cascade
  (`tools/backup_assets.py`).
- **Footprint-verified:** `tools/verify_assets.py` (metadata-only — runs even under restricted
  compute quota) confirms every asset is **EPSG:4326 @ 250 m (0.002246°)** with the exact GO+DF
  footprint (lon [-53.25, -45.90], lat [-19.50, -12.39]) — no displacement / scale error.
  ```bash
  EE_PROJECT=probformer uv run python tools/verify_assets.py
  ```

**Immediate next step:** publish Part 15's Earth Engine App (`gee_js/atlas_app.js`) from the GEE
Code Editor. Everything else needed for the thesis (all §4 tables, figures, and the three RQs) is
already built and written.

**Pending rebuild (2026-09-15):** `src/features.py`/`src/external.py` now derive the AOI and
municipal boundaries from the local IBGE malha municipal mesh (`src/ibge_mesh.py`) instead of
GAUL — see §7. The already-built `aoi` EE asset (and everything downstream: Parts 1–14, plus
`municipal_godf`) still reflects the old GAUL-derived boundary until Part 1 is explicitly
re-run and the cascade rebuilt — an approval-gated step (§10), not done as part of this change.

---

## 5. Layout

```
config/datasets.yaml          # pinned EE dataset IDs, bands, scale factors (single source of truth)
config/segments.yaml          # Part 9: per-segment fuzzy-membership params + AHP weights + masks
config/ahp_matrices.yaml      # Part 9: AHP pairwise-comparison matrices + consistency ratios
config/mapbiomas_classes.yaml # MapBiomas code -> segment-role remap (Phase B, Part 13)
src/utils.py                  # EE init, config loader, 250 m grid, asset/export helpers
src/features.py               # ALL Part 1-8 feature builders (one source of truth; lazy ee, import-safe)
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
tools/extract_present.py      # Part 9/10 summary tables; also writes municipal_ranking.csv (see §11 gotcha)
tools/extract_cmip6.py        # Part 11 summary tables
tools/gen_diag_csvs.py        # regenerates zoning_kselect.csv / factor_variance.csv diagnostics
notebooks/01..15               # thin: import src/, build, range-report, view, export — one per Part
docs/                          # supporting notes: _search_terms.md (lit-search scaffolding, not part of
                                # the thesis), metodologia_diagrama.md (PT methodology diagrams)
thesis/                        # the LaTeX dissertation itself (NOVAthesis/NOVA IMS template) — see §9
gee_js/atlas_app.js            # Part 15 Earth Engine App script (Code Editor mirror)
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
15_atlas_app.ipynb            -> Part 15  (tools/make_figures.py + gee_js/atlas_app.js) ── script written, not published
```

`12_municipal_gaul.ipynb` keeps its historical filename (reflects the last executed GAUL-based
run) even though `tools/gen_notebooks.py`'s Part-12 spec now targets the IBGE mesh — the notebook
itself isn't regenerated until the pending rebuild (see §4, §7) to avoid wiping its saved outputs.

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
  stays full precision. **Caveat:** this is a code-level swap only — the already-built `aoi` EE
  asset and everything downstream (Parts 1–14, `municipal_godf`) still reflect the old
  GAUL-derived boundary until an explicitly-approved rebuild (see §4, §10). If you need the
  original IBGE/GAUL reasoning, it is written up in `thesis/Chapters/03_methodology.tex` (not yet
  updated for this swap).
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

> **Assistant note (2026-09-15):** GDAL and geopandas were installed on the host for the IBGE
> municipal-mesh work (§10 point 6 — local vector join between the official IBGE malha and the
> municipal ranking table). Invoke Python exclusively via `uv run python ...` (or `uv run
> <tool>`), not `.venv/bin/python` or a bare `python3` — some host-level geo packages only
> resolve correctly through `uv run`'s environment.

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
thesis/Chapters/02_materials.tex
thesis/Chapters/03_methodology.tex
thesis/Chapters/04_results.tex
thesis/Chapters/05_discussion_conclusion.tex
thesis/Chapters/06_annex.tex
thesis/Chapters/abstract-pt.tex, abstract-en.tex, abstract-{de,es,fr,gr,it}.tex
thesis/Chapters/Figures/           # fig_4_*.png etc. — regenerated by tools/make_figures.py
thesis/Bibliography/bibliography.bib
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

**Figures:** `tools/make_figures.py` renders figures straight from the built EE assets
(`ee.Image.getThumbURL` thumbnails + matplotlib composition) into `thesis/Chapters/Figures/` — run
it after any asset re-export that changes a mapped layer, then re-`make` the PDF.
`tools/extract_present.py` writes the municipal-ranking table to the same tree
(`thesis/Chapters/Figures/municipal_ranking.csv`); `tools/gen_diag_csvs.py` writes its two
diagnostic CSVs one level up, in `thesis/Chapters/` (`$SCRATCHPAD` overrides both when set) — that's
where `make_figures.py`'s own diagram readers (`_read_diag`) look for them by default.

---

## 10. Current revision cycle

The dissertation is under a **3-week post-parecer revision** (14 Sep → 2 Oct 2026), addressing 7
points raised in the examiner's report, before a checkpoint with the adviser (Prof. Roberto
Henriques) and final submission. The day-by-day plan — what's done, what's next, and which two
steps ("requer aprovação": rewriting the published git history, and launching a heavy GEE
re-execution) always need explicit confirmation before running — lives in this artifact:

**https://claude.ai/artifact/HrMpse386bFykBeBsBeJN6** ("Cronograma de revisão — tese")

Read it with the `Artifact` tool (`action: "read"`) at the start of a session touching the
revision to see the current checkbox state (it's a live checklist, not a static plan) before
assuming what's already done.

The 7 points, in brief (see the artifact for the full day-by-day mapping):
1. Abstract listed only results, no conclusions → rewritten (Day 1).
2. Missing economic discussion → drafted (Day 1).
3. Limitations should cover soil *and* elevation (SRTM) data accuracy → Day 2.
4. κ=0.07 needs more explanation (vs. AUC=0.83) → Day 3.
5. Climate at ~4 km vs. 250 m for everything else needs explicit callout in the results reading,
   plus a spike into higher-resolution alternatives → Day 4–5, possible pipeline upgrade weeks 2.
6. Why not the official IBGE municipal mesh instead of GAUL? → Days 2–3, 11. **Code done
   (2026-09-15):** `src/ibge_mesh.py` replaces GAUL for both AOI and municipal reporting (§7);
   still pending the approved EE rebuild + the thesis text update (`02_materials.tex`,
   `06_annex.tex` still describe GAUL).
7. Code/atlas/ranking should ship now, not stay "future work" → Days 1–12 (this README/CLAUDE.md
   rewrite is part of point 7).

As of this writing: **Day 1 done, Day 2 in progress** — this file and `README.md` are the last
item of Day 2 (`d2-3`, "finish repo cleanup, write a new root README.md for GitHub visitors").

---

## 11. Verify-at-build gotchas

- **Match breakpoints to the band's actual scale, not just literature.** Every moving fuzzy-
  membership breakpoint in `config/segments.yaml` was reconciled to its variable's realized
  percentile range (`tools/anchor_breakpoints.py`) rather than trusted from nominal literature
  ranges — always check a band's real range (`range_report` / percentile `reduceRegion`) before
  trusting a breakpoint. `terr_slope` is in **degrees**.
- **Conservation is a value/priority index, not a native-cover detector.** It combines WDPA
  distance, ruggedness, and carbon (`feat_conservation`, routed via the `cv_` extras prefix, kept
  out of the stack/zoning like `feat_siting`'s `sit_` prefix) with demoted native-cover and moving
  climate factors, **aggregated by the compensatory arithmetic mean** (`aggregate: arithmetic` in
  `segments.yaml` → `membership.weighted_arithmetic`), not the geometric mean used by the other six
  segments. Don't revert to a native-cover-dominant, geomean-aggregated surface — that version was
  circular (native cover predicting "where native cover is") and CMIP6-invariant.
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
- If a layer looks displaced/mis-scaled in a notebook map preview, that's usually a
  `reproject`-pinned `Map.addLayer` artifact, not a real error — load the asset directly
  (`ee.Image('projects/probformer/assets/goias/<name>')`) and it renders correctly over Goiás.
