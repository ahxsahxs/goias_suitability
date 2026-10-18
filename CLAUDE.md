# CLAUDE.md — Goiás Agro-Market Suitability & CMIP6 Zoning

Operational guide: what the project is, how it runs, the rules that must not be
broken. The *why* of each methodological choice lives in the thesis
(`thesis/Chapters/04_methodology.tex` and the annex). The human overview and the
step-by-step reproduce/adapt guide are in `README.md` (PT).

## 1. What this is

A GEE-native suitability atlas and climate-projected zoning at 250 m. The default
territory is Goiás + DF; any UF set can be configured in `config/territory.yaml`. It
covers **seven segments**: soybean, sugarcane, other annual crops, pisciculture, cattle
(pasture), conservation, solar PV.

- **Suitability (Part 9).** Fuzzy membership per factor, with AHP weights derived from
  literature anchors. The six crop/production segments combine factors with a weighted
  geometric mean; conservation is a value index and uses the arithmetic mean. Results
  are classified into FAO S1/S2/S3/N.
- **Zoning (Part 10).** sklearn KMeans on a calibration-fitted PCA of 13 curated
  z-bands (K=4 for Goiás).
- **Future (Part 11).** CMIP6 delta-change (NEX-GDDP; 2 SSPs × 2 windows × 5 GCMs).
- **Validation (Parts 12–14).** Against MapBiomas, MOD17 and IBGE municipalities, on a
  50/50 spatial holdout.
- **Atlas (Part 15).** The Vue dashboard in `docs/dashboard/`.

Everything heavy runs server-side in Earth Engine. Only small CSVs/PNGs leave GEE,
and nothing is uploaded: the municipal mesh is embedded client-side on every run.

## 2. Layout

```
pipeline.py                  single CLI; each subcommand runs tools/ scripts (see §3)
config/territory.yaml        THE territory: asset folder, UFs, IBGE mesh, join key,
                             municipal asset name, growing season, split grid, output dir
                             ($TERRITORY=<file> selects another one)
config/datasets.yaml         pinned EE dataset IDs/bands/scales, grid, CMIP6 setup
config/segments.yaml         Part 9 factors, membership shapes, masks; weights MACHINE-WRITTEN
config/ahp_matrices.yaml     AHP INPUT anchors; `derived:` blocks MACHINE-WRITTEN
config/mapbiomas_classes.yaml MapBiomas code -> role / land-cover groups
config/dashboard.yaml        dashboard pt-BR labels only (never numbers)
src/utils.py                 config (cfg merges territory), EE init, grid, export/wait helpers,
                             out_dir()/out_path()/scratch_path(), split_mask()
src/features.py              Parts 1-8 builders (AOI, climate, terrain, soil, water,
                             landcover, siting, conservation, stack)
src/ibge_mesh.py             territory mesh -> client-side ee.FeatureCollection/Geometry
src/membership.py            Part 9 engine (+ offline AHP eigenvector/CR utilities)
src/zoning.py                Part 10 (sample, PCA, KMeans, k panel, profiles)
src/cmip6.py                 Part 11 delta-change engine
src/external.py              Parts 12-14 data (municipalities, MapBiomas, MOD17)
src/metrics.py               offline validation statistics
tools/run_rebuild_full.py    builds every EE asset, Parts 1-13 (idempotent stages)
tools/make_calib_val_split.py  holdout: --from-csv | --new | --check-only (Gate 0)
tools/export_horizon_climate.py  caches clim_future_ssp585_2051_2070
tools/anchor_breakpoints.py  percentiles / sigma(mu) discrimination
tools/diff_breakpoints.py    Gate 2: PRINTS breakpoint edits; a human applies them
tools/diff_sigma_domains.py  Gate 1: sigma(mu) full vs calib
tools/derive_weights.py      anchors -> Saaty matrix -> w_lit x sigma(mu)^lambda -> weights
tools/lambda_diagnostic.py   lambda sweep (lambda_auc.csv)
tools/probe_zoning_candidates.py  read-only test of side bands as zoning axes
tools/run_validation.py      Part 14 metrics
tools/extract_present.py / extract_cmip6.py / gen_diag_csvs.py   summary CSVs
tools/gen_thesis_tables.py   CSVs -> thesis/Chapters/Tables/*.tex (GENERATED)
tools/make_figures.py        figures -> thesis/Chapters/Figures/ (palettes.py shared)
tools/build_dashboard_assets.py  -> docs/dashboard/public/data/
tools/build_malha_municipal.py   IBGE zips -> territory mesh gpkg
tools/verify_assets.py       metadata-only footprint/CRS/scale check
tools/backup_assets.py / diff_vs_backup.py  server-side backup + per-band regression diff
tools/sync_zotero_bib.py     Zotero export -> thesis/Bibliography/bibliography.bib
```

Parts 6 and 7 are intentionally vacant: phenology and market access were removed
because they encode current land use.

## 3. Environment & running

Always `uv run python ...` (never bare `python`/`.venv/bin/python`). Set
`EE_PROJECT=probformer` for this author's assets; third parties use their own project.

```bash
uv sync && uv run earthengine authenticate
EE_PROJECT=probformer uv run python pipeline.py --help     # full ordered sequence
uv run python pipeline.py check                             # offline regression suite
EE_PROJECT=probformer uv run python pipeline.py verify      # metadata only, works in restricted mode
```

The subcommands are `mesh`, `build [--until S] [--force a,b|suit|zones] [--k K]`,
`split [--new|--check]`, `horizon`, `calibrate {breakpoints,weights}`, `validate`,
`diagnostics`, `report`, `dashboard [--only stage]`, `verify`, `backup` and `check`.
`build` maps onto `REBUILD_UNTIL` / `REBUILD_FORCE` / `ZONE_K` of `run_rebuild_full.py`.
`--force` DELETES the asset before exporting, so run `backup` first.

Outputs:
- **EE assets:** `projects/$EE_PROJECT/assets/<asset_subfolder>/<name>`.
- **CSVs:** `utils.out_dir()`, which is the territory `output_dir`
  (= `thesis/Chapters`) unless `$SCRATCHPAD` is set.
- **Scratch files:** `data/scratch/` (gitignored).

The dashboard (`docs/dashboard/`) has its own npm toolchain:
`npm install && npm run dev`. CI deploys it to GitHub Pages
(<https://ahxsahxs.github.io/goias_suitability>).

## 4. Guardrails (do not break)

- **Grid & data.** EPSG:4326 at 250 m; areas always via `ee.Image.pixelArea()`. Climate
  normal 1991–2020. Coarse climate is resampled bilinear; fine terrain/soil is coarsened
  with `reduceResolution`.
- **Four band policies; the stack is not "the model".** `feature_stack_250m` = climate 14
  + terrain 6 + soil 6 + water 3. Each consumer takes its own subset:
  - suitability selects factor by factor by prefix (`sit_`/`cv_`/`rl_`/`lc_` side images);
  - zoning uses `ZONING_BANDS` (13);
  - the RF cross-check and the dashboard PCA take the whole z-stack.

  Adding a theme to `STACK_THEMES` silently widens the RF predictors.
- **No circularity.**
  - Land cover is mask/context only. The one exception is conservation's demoted
    `rl_native_frac`.
  - MapBiomas is mask + validation + profiling only.
  - Never use land use, NDVI or travel time as a suitability or clustering input.
  - The five `sit_`/`cv_` bands were measured and rejected as zoning axes
    (`zoning_candidates*.csv`). Don't re-litigate that without reading them.
- **Weights are DERIVED, never hand-set.**
  - Direction: anchors → matrix → `w_lit` → × σ(μ)^λ → `weight:`. `derive_weights.py
    --check` catches drift.
  - σ(μ) is `sigma_mu_horizon` (present ∪ CMIP6 horizon), so a factor saturated today
    keeps its CMIP6 lever.
  - There is no `role: gate` (don't reintroduce it).
  - `derived_half: calib` tells `--check` which domain to use.
- **Breakpoints.** Each carries an `anchor:` (`percentile` | `mu_one` | `agronomic`).
  Only `percentile` ones move with the data (`diff_breakpoints.py`). Re-stamp
  `anchored_at` in the same edit. `terr_slope` is in degrees.
- **Spatial holdout.**
  - Every estimated parameter (σ(μ), percentiles, PCA, centroids) comes from the
    calibration half; every reported metric from the validation half.
  - Read the split only through `utils.split_mask/split_image` (the `calib_val_split`
    asset). Never recompute the grid in memory.
  - Restrict by MASK, never by `geometry=`. Products always cover the whole AOI.
  - `split_mask('full')` returns `None` on purpose.
  - Never re-export `aoi`/`feat_realized` while `$SPLIT_HALF` is set.
  - `(val − calib)` is a between-halves difference, not optimism. Only `rf_kappa` is a
    train/test contrast.
  - `ari_subsample` ≠ `ari_holdout`. K claims rest on the holdout columns.
  - A stale CSV without `half` columns must make tools refuse, not fall back.
- **Zoning.**
  - Offline sklearn plus server-side nearest-centroid band math. Never weka, never raw
    29-band clustering.
  - Zones are canonically numbered by descending mean `terr_elev` (`fit_kmeans(order_by=)`).
  - The raster is 0-based; every CSV, table, figure and the dashboard are 1-based. The +1
    is applied once, in `profile_zones`.
  - Labels use `comparative_segment` (z-normalized argmax).
  - The zoning sample is stratified on the `suit_present` argmax, so re-run the k panel
    after any weight change. The silhouette is near-flat at every k: zoning is a
    partitioning device, not a discovery of natural groups.
- **CMIP6.**
  - Δ subtracts `cmip6.suit_present_rederived`, never the exported asset; identity
    factors give Δ = 0.
  - Future climate reuses `features.derive_climate_bands`. srad and soil moisture are
    held at baseline (documented caveat).
  - Run real projections only as batch exports.
- **EE practicalities.**
  - Use the cached `feat_realized` asset, `tileScale=8`, and samples ≤ 4500 (getInfo cap).
  - `zoning.build_strat_band()` needs `.toInt()` before `stratifiedSample`.
  - `terr_tpi`/`terr_twi` differ in ~0.1% of pixels between re-exports (tile-edge noise);
    `terr_slope` is bit-identical.
  - TWI catchment uses the HydroSHEDS cell (~464 m), not 250 m.
  - A layer that looks displaced in a map preview is usually a `reproject` artifact; load
    the asset directly.
- **MOD17.** NPP (`MOD17A3HGF`) is municipal context only. GPP (`MOD17A2HGF`, integrated
  over `growing_months`) is the within-crop validator. Presence AUC/Boyce are the primary
  crop validators.
- **Generated files are never hand-edited.** That covers:
  - `thesis/Chapters/Tables/*.tex` (`gen_thesis_tables.py`);
  - `thesis/Bibliography/bibliography.bib` (`sync_zotero_bib.py`);
  - `weight:` / `derived:` in config;
  - `docs/dashboard/public/data/`.

  Zone area shares come from `zone_area.csv` (pixelArea), never from
  `zone_profiles.csv`'s sample `n`. Never quote a k or any metric from memory: read the CSV.
- **Decide by measurement.** A structural objection gets a read-only probe and an argued
  paragraph, never a cascade that silently moves published numbers.

## 5. Thesis (LaTeX)

`thesis/` is a NOVAthesis/NOVA IMS template. The entry point is `template.tex`.
- Chapters are `Chapters/01_introduction … 07_annex.tex`, plus `02_estado_arte.tex` (P4).
- The cover is set in `Config/3_cover.tex`; language and degree in
  `Config/1_novathesis.tex`.

Build with `cd thesis && make` (latexmk). Build artifacts and the PDF are gitignored.
`\input` paths are relative to `thesis/` (`\input{Chapters/Tables/x.tex}`). Zone-indexed
tables follow K automatically. After any asset re-export that changes a mapped layer,
run `pipeline.py report`, then `make`.

**Bibliography: source first.**
- Zotero is the source of truth. Its export (`Bibliography/zotero_bibliography.bib`) and
  the PDFs (`Bibliography/zotero_storage/<ID>/`) are local and gitignored (copyright).
  Run `uv run python tools/sync_zotero_bib.py [--check]`.
- Keys follow `author_titleword_year`.
- Before writing or changing a sentence that cites a source, read the passage in the
  PDF itself (never from memory, the abstract or the .bib). Give a locator for any
  specific datum (`\citep[p.~X]{key}`).
- An entry with no local PDF cannot back a new claim; the one exception is
  `da_silva_goias_suitability_2026`.
- PDFs never leave the machine.

## 6. Status

- Parts 1–15 are built and footprint-verified under project `probformer`.
- The thesis chapters 01–07 answer RQ1–RQ3.
- The dashboard is live.

The post-examiner revision checklist lives in the artifact
<https://claude.ai/artifact/HrMpse386bFykBeBsBeJN6>. Read it before assuming any item is
closed.
