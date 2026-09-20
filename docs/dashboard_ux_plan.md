# Goiás Agro-Market Suitability Atlas — Static Dashboard UX Plan

Design plan for the public, static, GitHub-Pages-hosted dashboard that becomes the project's
**only** interactive deliverable. `gee_js/atlas_app.js` (the Earth Engine App) is retired; this
document replaces it as the spec for Part 15.

This is a planning document only — no dashboard code exists yet. A future build session executes
against this spec.

---

## 1. Goals & non-goals

**Goals**

- Serve every one of the 14 built pipeline parts (feature engineering → suitability → zoning →
  CMIP6 → validation) as a distinct, navigable route, showing both **final results** and
  **intermediate modelling artifacts** (e.g. fuzzy membership curves, AHP weight bars, k-selection
  diagnostics) — not just the finished maps.
- Run entirely on pre-exported static assets at *view time*. No GEE authentication, no server,
  no database — only two build-time pipelines: a one-time (re-run-on-change) **Python** data-export
  script, and a standard **Vite** production build of the site itself (§2.5).
- Deploy to GitHub Pages via GitHub Actions, viewable from a public URL with no login.
- Be self-explanatory to a reader who has not read the thesis — every route carries a short
  explainer and the guardrails that matter (e.g. "land cover is never a suitability input").
- Be built on a typed, componentized stack (Vue 3 + TypeScript) so the ~11-route, ~15-component
  surface stays maintainable as it grows, instead of ad-hoc DOM wiring.

**Non-goals**

- Full parity with `atlas_app.js`'s ~100-layer combinatorial matrix (7 segments × {suit, class,
  sens} × zones × realized × underused × 2 SSP × 2 windows × agreement). Curated instead: every
  part gets its headline layer(s), not every permutation.
- No live GEE compute at view-time. No user-uploaded data. No account/login.
- No server-side rendering, no API backend, no database — the "app" is a pure client-side SPA
  reading static files; the framework buys structure/types, not a server.
- No claim of replacing the thesis PDF — the dashboard is a companion explorer, cross-linking to
  chapter/table/figure numbers, not a restatement of the full narrative.

---

## 2. Site architecture

### 2.1 Stack

- **Vue 3** (Composition API, `<script setup lang="ts">`) as the SPA framework — components,
  reactivity, and **Vue Router** (hash history, to avoid needing server-side rewrites on GitHub
  Pages) for the ~11 routes plus their segment/scenario sub-routes (e.g.
  `#/suitability/soybean`, `#/cmip6/ssp245/2031_2050/sugarcane`).
- **TypeScript**, strict mode, for every `.ts`/`.vue` file. All static data files (§4/§5 manifest)
  get a matching interface in `src/types/data.ts`, generated/maintained by hand from the same
  `config/*.yaml` schemas the Python build script reads — so a shape mismatch between the Python
  export and the Vue consumer is a compile error, not a runtime `undefined`.
- **Vite** as the build tool/dev server (`npm create vite@latest -- --template vue-ts`). Fast HMR
  locally; `vite build` produces the static `dist/` that actually ships to Pages (§2.5). Vite's
  `vite preview` (built on `sirv`) serves `dist/` with proper HTTP `Range` support, which matters
  for local PMTiles testing (§8) — unlike a plain `python -m http.server`.
- **MapLibre GL JS** (npm package, ships its own TS types) for all map panels — vector (GeoJSON)
  and raster (PMTiles) layers, wrapped in one `MapPanel.vue` component (§2.6).
- **PMTiles** (npm package `pmtiles`) as the raster tile transport — its `Protocol` is registered
  once against `maplibregl.addProtocol('pmtiles', ...)` in `src/main.ts`. Chosen because GitHub
  Pages has no tile server; PMTiles is a single-file tile pyramid fetched via HTTP range requests,
  which GitHub Pages' CDN (Fastly) supports natively. This is the mechanism, not a scope change,
  behind the "COG tiles" decision: **GEE exports COGs → a local Python script
  re-projects/colorizes/tiles them into PMTiles → the site reads PMTiles.**
- **Plotly.js** (npm package `plotly.js-dist-min` + `@types/plotly.js` for typing) for every chart:
  membership curves, AHP bars, zone radar/bars, k-selection diagnostics, CMIP6 transition bars,
  validation scorecard charts — wrapped in one thin `PlotlyChart.vue` component (§2.6) rather than
  a community Vue-Plotly wrapper, to keep the dependency surface and bundle size under direct
  control.
- **Papaparse** (+ `@types/papaparse`) for typed CSV parsing (`zone_profiles.csv`,
  `municipal_ranking.csv`, etc.) instead of a hand-rolled splitter.
- **Pinia**, used sparingly, only for state genuinely shared *across* routes (e.g. the currently
  selected municipality carried from the Municipal Explorer into a deep link). Per-route selector
  state (segment/scenario/window toggles) stays local to that route's component tree via
  `ref`/route params — no global store needed for it.
- No CSS framework — a small hand-written `style.css` (design tokens as CSS custom properties) is
  enough for an 11-route dashboard; pulling in Tailwind/Vuetify would add build complexity this
  project doesn't need.

### 2.2 Directory layout

```
docs/
  dashboard_ux_plan.md          # this file
  dashboard/                    # Vue 3 + TS + Vite project (source; NOT the deployed output)
    index.html                  # Vite entry (mounts #app)
    package.json
    tsconfig.json
    vite.config.ts              # base: '/<repo-name>/' for the GitHub Pages project-page URL
    public/
      data/                     # copied verbatim into dist/ on build — the exported data (§5)
        pmtiles/                # hero raster layers
        png/                    # lightweight static chips (feature-theme gallery, etc.)
        geojson/                # aoi.geojson, municipios.geojson, municipal_ranking.geojson
        csv/                    # zone_profiles.csv, zoning_kselect.csv, factor_variance.csv,
                                 # theme_roughness*.csv, municipal_ranking.csv
        json/                   # segments.json, ahp_matrices.json (converted from config/*.yaml),
                                 # datasets_catalog.json (from config/datasets.yaml)
    src/
      main.ts                   # app bootstrap: creates the Vue app, router, Pinia; registers
                                 # the PMTiles MapLibre protocol once
      App.vue                   # shell: header, nav, <router-view>
      router.ts                 # Vue Router, hash history, one route per tab + sub-routes
      styles/tokens.css          # color ramps/spacing as CSS custom properties (ported from
                                 # tools/palettes.py so site and thesis PNGs never drift)
      types/
        data.ts                 # TS interfaces for every file in the §5 manifest (SegmentConfig,
                                 # AhpMatrix, ZoneProfileRow, MunicipalRankingFeature, ...)
      composables/
        useJson.ts               # typed fetch+cache: useJson<T>(url) -> { data, error, loading }
        useCsv.ts                # typed fetch+parse (Papaparse) -> Ref<T[]>
        useMapLayer.ts            # add/remove/update a MapLibre PMTiles or GeoJSON layer, tied to
                                 # a component's lifecycle (onUnmounted cleanup)
      components/
        MapPanel.vue              # MapLibre instance wrapper; props: layers, center, zoom, legend
        PlotlyChart.vue           # thin Plotly wrapper; props: data, layout, config (typed)
        SegmentSelector.vue       # the 7-segment tab/button group, reused on 4+ routes
        ScenarioSelector.vue      # SSP × window 2x2 selector (CMIP6 route)
        ZoneCard.vue              # one zone's profile card (radar/bar + composition + stats)
        DataTable.vue             # generic typed table (validation scorecard, dataset catalog)
        StatChip.vue              # small headline-number chip (Home route, Municipal Explorer)
      views/                      # one per top-level route, matches §3's IA
        HomeView.vue
        StudyAreaView.vue
        FeatureThemesView.vue
        FeatureStackView.vue
        SuitabilityView.vue
        ZoningView.vue
        Cmip6View.vue
        RealizedUseView.vue
        ValidationView.vue
        MunicipalExplorerView.vue
        AboutView.vue
      stores/
        useSelectionStore.ts       # Pinia: cross-route selection (e.g. deep-linked municipality)
    dist/                        # Vite build output — gitignored; this is what CI deploys (§2.5)
tools/
  build_dashboard_assets.py     # Python: orchestrates the GEE export/convert pipeline (§2.3),
                                 # writes into docs/dashboard/public/data/
  palettes.py                   # shared vis-param/color-ramp definitions, imported by both
                                 # build_dashboard_assets.py and make_figures.py (dedup); mirrored
                                 # by hand into src/styles/tokens.css so the site matches
.github/
  workflows/
    deploy-dashboard.yml        # CI: npm ci && npm run build inside docs/dashboard, then
                                 # actions/upload-pages-artifact + actions/deploy-pages (§2.5)
```

`tools/make_figures.py` is untouched in intent — it keeps rendering the thesis PDF's static PNGs.
It gets refactored only to import shared palettes from the new `tools/palettes.py`, so the
dashboard and the thesis figures never drift into two different color scales for the same layer.

### 2.3 Data build pipeline (Python, offline, one-time / re-run on asset change)

`tools/build_dashboard_assets.py`, run via `EE_PROJECT=probformer uv run python
tools/build_dashboard_assets.py [--only <tab>]`. Unchanged in substance from the original plan —
only its output path moves under Vite's `public/` so a site build picks it up automatically:

1. **Vector assets** — pull `aoi`, `municipal_fc` (IBGE mesh) from `src/ibge_mesh.py`, plus the
   already-built `municipal_ranking.csv`; join and simplify geometry; write GeoJSON directly to
   `docs/dashboard/public/data/geojson/`. No GEE export needed (client-side FeatureCollection
   already).
2. **Hero raster assets** — for each entry in the manifest (§5): `ee.batch.Export.image.toDrive`
   with `fileFormat='GeoTIFF', formatOptions={'cloudOptimized': True}`, at native 250 m, clipped to
   AOI. Poll/wait like `tools/wait_for_assets.py` already does for other exports.
3. **Local COG → PMTiles conversion** — per downloaded COG: apply the matching palette from
   `tools/palettes.py` (GDAL color-relief, matching `make_figures.py`'s existing per-layer vis
   params) → reproject to Web Mercator → tile (`gdal2tiles.py` or `rio pmtiles`) → single
   `.pmtiles` file into `docs/dashboard/public/data/pmtiles/`. Only 2–3 zoom levels are needed
   (native resolution is 250 m over a ~340,000 km² AOI — no benefit tiling down to street-level
   zoom).
4. **Lightweight PNG gallery** — for the ~30 non-hero feature-theme bands (§5), reuse
   `make_figures.py`-style single-shot thumbnails (already exists as a pattern) into
   `docs/dashboard/public/data/png/`, no PMTiles conversion.
5. **CSV passthrough** — copy already-produced `zone_profiles.csv`, `zoning_kselect.csv`,
   `factor_variance.csv`, `theme_roughness.csv`, `theme_roughness_points.csv` into
   `docs/dashboard/public/data/csv/` verbatim (these already exist per `tools/gen_diag_csvs.py` /
   `src/zoning.py`).
6. **Config → JSON** — convert `config/segments.yaml` (membership breakpoints + weights) and
   `config/ahp_matrices.yaml` (pairwise matrices + CR) to flat JSON for client-side Plotly curve
   plotting; convert `config/datasets.yaml` to a small catalog JSON for the Study Area route's
   source table. Each JSON's shape must match its `src/types/data.ts` interface — a schema drift
   check (`--check-types` flag, comparing keys against a small JSON-schema mirror of the TS types)
   is worth adding once the interfaces stabilize, so a config edit that breaks the frontend fails
   at build time, not silently in the browser.

### 2.4 Known risk: static asset volume

GitHub repos/Pages have an informal ~1 GB soft ceiling and a 100 MB hard per-file limit
(without Git LFS). Real PMTiles sizes aren't known until §2.3 step 3 runs once. Mitigations to
evaluate at build time, not decided now: trim zoom-range further, use `git-lfs` for
`docs/dashboard/public/data/pmtiles/`, or fetch large PMTiles from a GitHub Release asset /
external object storage at runtime instead of bundling them into the Pages deploy (Vite's `public/`
files still need to exist locally for dev, but the CI workflow could substitute a fetch step for a
release download instead of a git-committed copy, if size forces the issue). Flagged here so the
future build session budgets time for it — this also now affects local git working-tree size, not
just the Pages hard limit, since `public/data/` is a real tracked directory in this repo.

### 2.5 Site build & deploy pipeline (Vite + GitHub Actions)

This is new relative to the original vanilla-JS plan, which had no site build step at all.

- **Local dev:** `cd docs/dashboard && npm install && npm run dev` — Vite dev server with HMR,
  reading straight from `public/data/` on disk (no build needed to iterate on a component).
- **Type-check:** `npm run type-check` (`vue-tsc --noEmit`) — run in CI before build so a type
  error fails fast instead of shipping a broken bundle.
- **Production build:** `npm run build` (`vite build`) → `docs/dashboard/dist/`. `vite.config.ts`
  sets `base: '/<repo-name>/'` so asset URLs resolve correctly under the project-page path
  (`https://<user>.github.io/<repo-name>/`); this becomes `base: '/'` only if the project ever
  moves to a custom domain or an org/user root page.
- **Local production preview:** `npm run preview` (`vite preview`) serves `dist/` via `sirv`, which
  honors `Range` requests — the faithful local stand-in for GitHub Pages' PMTiles behavior (see
  §8, which replaces the earlier `python -m http.server` / `npx serve` workaround).
- **CI/CD:** `.github/workflows/deploy-dashboard.yml`, triggered on push to `main` touching
  `docs/dashboard/**` (path-filtered so unrelated thesis/pipeline commits don't retrigger a
  deploy):
  1. checkout, `actions/setup-node`, `npm ci` in `docs/dashboard`.
  2. `npm run type-check && npm run build`.
  3. `actions/upload-pages-artifact@v3` with `path: docs/dashboard/dist`.
  4. a `deploy` job depending on the build job, using `actions/deploy-pages@v4`.
  - Repo setting: **Settings → Pages → Build and deployment → Source: GitHub Actions** (not
    "Deploy from a branch" — that legacy mode would try to serve `docs/dashboard/` as source,
    which is now a Vite project, not a servable site, since the actual site is the *build output*).
- **`.gitignore` additions:** `docs/dashboard/node_modules/`, `docs/dashboard/dist/`.

### 2.6 Shared component inventory

Every route composes from the same small set of typed, reusable components rather than
reimplementing map/chart/selector wiring per route:

| Component | Purpose | Used by (routes) |
|---|---|---|
| `MapPanel.vue` | MapLibre instance; PMTiles/GeoJSON layers, legend slot | Study Area, Feature Themes, Suitability, Zoning, CMIP6, Realized Use, Municipal Explorer |
| `PlotlyChart.vue` | Typed Plotly wrapper (`newPlot`/`react`/`purge` lifecycle) | Feature Stack, Suitability, Zoning, CMIP6, Validation |
| `SegmentSelector.vue` | 7-segment button group, emits `segment` selection | Suitability, CMIP6, Realized Use, Municipal Explorer |
| `ScenarioSelector.vue` | SSP × window 2×2 toggle | Climate Shift (CMIP6) |
| `ZoneCard.vue` | One zone's profile (radar + composition + stats) | Zoning, Home (headline strip) |
| `DataTable.vue` | Generic typed table | Study Area (dataset catalog), Validation (scorecard) |
| `StatChip.vue` | Small headline-number chip | Home, Municipal Explorer |

Each of these has a `defineProps<{...}>()` TypeScript interface in the component itself, and where
its data comes from a manifest file, that shape is imported from `src/types/data.ts` — so, e.g.,
`ZoneCard.vue`'s props are typed as `ZoneProfileRow` (the parsed-CSV row shape), not `any`.

---

## 3. Information architecture

Top nav, grouped into 4 sections plus a standalone landing route — **11 routes total**, each mapped
to a pipeline Part so "Split different modelling steps into tabs" is literal, not just thematic.
Routes with a segment/scenario dimension carry it as a Vue Router param (e.g.
`/suitability/:segment`, `/cmip6/:ssp/:window/:segment`) rather than component-internal state, so a
specific view is directly linkable/shareable.

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 🌾 Goiás Suitability Atlas          [Home]                              │
├───────────────────────┬───────────────────┬──────────────────┬─────────┤
│ FEATURE ENGINEERING    │ MODELLING          │ FORECAST & VALID. │ EXPLORE │
│ · Study Area & Data(1) │ · Suitability (9)  │ · Climate Shift(11)│ · Municipal Explorer│
│ · Feature Themes(2-7d) │ · Zoning (10)      │ · Realized Use(12-13)│ · About/Guardrails │
│ · Feature Stack (8)    │                    │ · Validation (14)  │         │
└───────────────────────┴───────────────────┴──────────────────┴─────────┘
```

| # | Route | Pipeline Part(s) | Primary question it answers |
|---|---|---|---|
| 0 | `/` (Home) | — | What is this, and what are the 3 RQs? |
| 1 | `/study-area` | Part 1 | Where is the study area, what datasets feed it? |
| 2 | `/feature-themes/:theme?` | Parts 2–7d | What does each of the 8 biophysical themes look like? |
| 3 | `/feature-stack` | Part 8 | How do the 34 bands combine, raw vs. standardized? |
| 4 | `/suitability/:segment?` | Part 9 | How is each segment's suitability derived (fuzzy+AHP)? |
| 5 | `/zoning` | Part 10 | How is GO/DF partitioned into 7 zones? (RQ1) |
| 6 | `/cmip6/:ssp?/:window?/:segment?` | Part 11 | How does suitability shift by 2050/2070? (RQ3) |
| 7 | `/realized-use/:crop?` | Parts 12–13 | Where is potential under-utilized? (RQ2) |
| 8 | `/validation` | Part 14 | How trustworthy is the model (AUC/Boyce/κ/Spearman)? |
| 9 | `/municipal/:name?` | cross-cutting (9–14) | What does *my* municipality look like, across all of it? |
| 10 | `/about` | — | Methodology caveats, data sources, how to cite. |

---

## 4. Route-by-route wireframes

The ASCII layouts below are unchanged from the original UX pass (they describe the UI, not the
framework); each "Components:" line now names the actual Vue view/component doing the work.

### 4.0 Home — `HomeView.vue`

```
┌───────────────────────────────────────────────────────────────────┐
│  Goiás Agro-Market Suitability & CMIP6 Zoning                      │
│  A 250 m atlas of biophysical potential for 7 land-use segments,   │
│  clustered into agro-environmental zones and projected to 2050.    │
│                                                                      │
│  [ RQ1: Zoning ]   [ RQ2: Potential vs. Realized ]   [ RQ3: Forecast]│
│      ↓ /zoning            ↓ /realized-use                ↓ /cmip6   │
│                                                                      │
│  ┌───────────────── hero map: zones_present (K=7) ─────────────┐   │
│  │                [interactive MapLibre, PMTiles]               │   │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Headline numbers:  7 zones · 7 segments · 5-GCM ensemble ·         │
│  soy underuse 48% · κ=0.07 (spatial-block) · AUC=0.83 (soy)         │
└───────────────────────────────────────────────────────────────────┘
```
Components: `MapPanel.vue` (hero PMTiles `zones_present`), 3 RQ cards (plain `<RouterLink>`s) to
their routes, a `StatChip.vue` strip pulling from a small `home_stats.json` written at Python
build time (aggregated once from `municipal_ranking.csv` / `factor_variance.csv`, not recomputed
client-side).

### 4.1 Study Area & Data — `StudyAreaView.vue`

```
┌───────────────────────────────────────────────────────────────────┐
│  Study Area & Data Sources                          (Part 1)       │
│  ┌───────────────── map: aoi + municipios.geojson ─────────────┐  │
│  │  GO + DF boundary, 247 municipalities (IBGE malha 2025)      │  │
│  └────────────────────────────────────────────────────────────────┘│
│  Dataset catalog (from config/datasets.yaml)                        │
│  ┌────────────┬──────────────┬───────────┬────────────────────┐   │
│  │ Theme      │ Source        │ Native res│ Period              │   │
│  │ Climate    │ TerraClimate  │ ~4.6 km   │ 1991–2020 normal    │   │
│  │ Terrain    │ SRTM GL1      │ 30 m      │ static              │   │
│  │ ...        │ ...           │ ...       │ ...                 │   │
│  └────────────┴──────────────┴───────────┴────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```
Components: `MapPanel.vue` (vector-only: `aoi.geojson` + `municipios.geojson`, no PMTiles needed
here), `DataTable.vue` typed against `DatasetCatalogEntry[]` (`useJson<DatasetCatalogEntry[]>`
reading `datasets_catalog.json`).

### 4.2 Feature Themes — `FeatureThemesView.vue` (nested by `:theme?` param)

```
┌───────────────────────────────────────────────────────────────────┐
│  Feature Themes                                    (Parts 2–7d)    │
│  [Climate] [Terrain] [Soil] [Water] [Phenology] [Access]            │
│  [Land-cover mask] [Siting] [Conservation]                          │
│  ─────────────────────────────────────────────────────────────      │
│  Band: [ clim_aridity ▾ ]        (dropdown, per-theme band list)   │
│  ┌───────────────── map (PMTiles hero OR PNG chip) ──────────────┐ │
│  └───────────────────────────────────────────────────────────────┘ │
│  Histogram / percentile range (Plotly) — P5/P50/P95 markers        │
└───────────────────────────────────────────────────────────────────┘
```
Components: a theme `<RouterLink>` strip (9 sub-routes via `:theme` param), a band `<select>`
bound to a `ref<string>`. Each theme's band dropdown swaps either `MapPanel.vue` (PMTiles, only for
the 1–2 "representative" bands per theme flagged as hero in §5) or a plain `<img>` (remaining
bands, PNG chips) — a small `v-if`/`v-else` in the view, not two separate components. Histogram is
`PlotlyChart.vue` fed by `band_percentiles.json` (extends `tools/anchor_breakpoints.py`'s
range-report output into per-band JSON at build time).

### 4.3 Feature Stack — `FeatureStackView.vue`

```
┌───────────────────────────────────────────────────────────────────┐
│  Feature Stack (34 bands)                              (Part 8)    │
│  ┌── theme composition (stacked bar: 14+6+6+3+4+1 bands) ────────┐ │
│  └───────────────────────────────────────────────────────────────┘ │
│  [ Raw ]  [ Standardized (z-score) ]     ← toggle                  │
│  Note: land cover is deliberately excluded from this stack —       │
│  never a suitability/clustering input. [why? → About]              │
└───────────────────────────────────────────────────────────────────┘
```
Components: one `PlotlyChart.vue` (theme → band count, stacked/grouped bar) fed by
`stack_composition.json`, a raw/z-score toggle (`ref<'raw' | 'z'>`) that only relabels the chart —
no separate maps needed here (spatial pattern is already covered per-band in Feature Themes).

### 4.4 Suitability Modelling — `SuitabilityView.vue` (nested by `:segment?`) — the most
detail-dense route

```
┌───────────────────────────────────────────────────────────────────┐
│  Suitability Modelling                                  (Part 9)   │
│  Segment: [Soybean][Sugarcane][Other crops][Pisciculture]           │
│           [Cattle][Conservation][Solar]                             │
│  ─────────────────────────────────────────────────────────────     │
│  ┌── suit map (PMTiles) ──┐  ┌── FAO class map (S1/S2/S3/N) ─────┐ │
│  └─────────────────────────┘  └────────────────────────────────────┘│
│  AHP weights (bar, CR=0.002)      Fuzzy membership curves (per      │
│  ┌─────────────────────────┐      factor, Plotly line + P5–P95     │
│  │ clim_pr    ███ 0.22      │      markers from anchor_breakpoints)│
│  │ soil_clay  ██  0.15      │      ┌─────────────────────────────┐│
│  │ terr_slope █   0.08      │      │  μ(x)                        ││
│  │ ...                       │      │   1 ┤      ___________       ││
│  └─────────────────────────┘      │     0 ┼──/                    ││
│                                    └─────────────────────────────┘│
│  Sensitivity (±20% AHP): [ histogram of Smax−Smin per pixel ]       │
│  Aggregation: weighted geometric mean                               │
│  (Conservation only: weighted arithmetic mean — compensatory)       │
└───────────────────────────────────────────────────────────────────┘
```
Components: `SegmentSelector.vue` (drives the `:segment` route param), two `MapPanel.vue` instances
(suit + class PMTiles), a `PlotlyChart.vue` AHP weight bar annotated with the segment's consistency
ratio (typed `AhpMatrix` from `ahp_matrices.json`), a factor-selector `<select>` driving a second
`PlotlyChart.vue` membership-curve plot (typed `SegmentConfig` from `segments.json`'s breakpoints),
and a sensitivity histogram `PlotlyChart.vue` fed by a small per-segment `sens_<segment>.json`
(reduceRegion percentiles at Python build time, not the full raster). This route is the direct
answer to "show intermediate modelling steps," per the user's explicit ask.

### 4.5 Agro-Environmental Zoning — `ZoningView.vue`

```
┌───────────────────────────────────────────────────────────────────┐
│  Agro-Environmental Zoning (K=7)                       (Part 10)   │
│  ┌───────────────── zone map (PMTiles, 7 colors) ─────────────┐   │
│  └────────────────────────────────────────────────────────────────┘│
│  Zone: [Z1][Z2][Z3][Z4][Z5][Z6][Z7]  → click a zone card:           │
│  ┌── Z1: "privileged crop plateau" — comparative: soy/cane ──────┐ │
│  │  radar/bar: mean suit_* per segment (z-normalized)             │ │
│  │  19.2% of territory · realized composition: 61% pasture...     │ │
│  └───────────────────────────────────────────────────────────────┘ │
│  k-selection diagnostics (silhouette/DB/gap/ARI vs k) — why k=7     │
│  Factor variance decomposition (per-segment, which factors drive it)│
│  Scale-mismatch (climate vs. terrain+soil roughness, 42×–320×)      │
└───────────────────────────────────────────────────────────────────┘
```
Components: `MapPanel.vue` (PMTiles zone map), 7 `ZoneCard.vue` instances (typed `ZoneProfileRow[]`
from `useCsv<ZoneProfileRow>('zone_profiles.csv')`), a `PlotlyChart.vue` k-selection line chart
(`zoning_kselect.csv`), a `PlotlyChart.vue` factor-variance bar (`factor_variance.csv`), and a
`PlotlyChart.vue` scale-mismatch hexbin (`theme_roughness_points.csv` + `theme_roughness.csv`) —
this is `fig_4_10`/`fig_4_11`/`fig_4_12` reborn as interactive Plotly instead of static PNG.

### 4.6 Climate Shift (CMIP6) — `Cmip6View.vue` (nested by `:ssp?/:window?/:segment?`)

```
┌───────────────────────────────────────────────────────────────────┐
│  Climate Shift — CMIP6                                 (Part 11)   │
│  Scenario: [SSP2-4.5] [SSP5-8.5]   Window: [2031-50] [2051-70]      │
│  Segment:  [Soybean][Sugarcane][Other crops][Conservation][Solar]    │
│  ┌── ΔSuitability map (diverging PMTiles) ─┐ ┌── Agreement (5-GCM)─┐│
│  └───────────────────────────────────────────┘ └─────────────────────┘│
│  Present vs. future climate (precip/temp small-multiples)           │
│  Transition table: FAO class downgrades (S1→S2 share, etc.)         │
└───────────────────────────────────────────────────────────────────┘
```
Components: `ScenarioSelector.vue` (drives `:ssp`/`:window`), `SegmentSelector.vue` restricted to
the 5 segments actually discussed in the thesis (per §5 manifest — not all 7), two `MapPanel.vue`
instances (ΔS PMTiles + agreement PMTiles), a static `<img>` reuse of `fig_4_14.png` for the
present/future climate comparison (not re-plotted interactively), and a `DataTable.vue`
transition-share bar via `PlotlyChart.vue`.

### 4.7 Realized Use & Potential Gap — `RealizedUseView.vue` (nested by `:crop?`)

```
┌───────────────────────────────────────────────────────────────────┐
│  Realized Use & Potential Gap                        (Parts 12–13) │
│  ┌── realized land-use role map (PMTiles) ──┐ ┌── underused map ──┐│
│  │  (rl_role: soy/cane/other/pisc/pasture/  │ │ (suitable≥S2 AND  ││
│  │   native)                                  │ │  not-in-that-use)││
│  └────────────────────────────────────────────┘ └────────────────────┘│
│  Crop: [Soybean][Sugarcane][Other crops][Pisciculture]               │
│  Realized-composition table · underused-share bar (48%/58%/63%/10%) │
└───────────────────────────────────────────────────────────────────┘
```
Components: `SegmentSelector.vue` restricted to the 4 crops with an `underused_<crop>` layer, two
`MapPanel.vue` instances (`rl_role` PMTiles + `underused_<crop>` PMTiles), a `PlotlyChart.vue` bar
of underused shares.

### 4.8 Validation — `ValidationView.vue`

```
┌───────────────────────────────────────────────────────────────────┐
│  Validation                                            (Part 14)   │
│  Scorecard                                                          │
│  ┌────────────┬───────┬───────┬──────────────────┬────────────┐   │
│  │ Segment    │ AUC   │ Boyce │ Block-CV AUC      │ note        │   │
│  │ Soybean    │ 0.83  │ 0.66  │ 0.79 ± 0.13       │             │   │
│  │ Sugarcane  │ 0.83  │ 0.74  │ 0.61 ± 0.13       │ spatial art.│   │
│  │ Other crops│ 0.64  │ 0.66  │ —                 │             │   │
│  └────────────┴───────┴───────┴──────────────────┴────────────┘   │
│  NPP Spearman by segment (bar) · GPP within-crop gradient (scatter) │
│  RF cross-check: in-sample κ=0.23 vs. spatial-block κ=0.07          │
│  [ why the drop? → About explainer, ties to tab:presence-auc ]      │
└───────────────────────────────────────────────────────────────────┘
```
Components: `DataTable.vue` typed against `ValidationScorecardRow[]` (`validation_scorecard.json`),
a `PlotlyChart.vue` Spearman bar, a `PlotlyChart.vue` GPP scatter, a short prose callout
(static content in the `.vue` template) on the AUC/κ discrepancy (point 4 of the revision cycle —
reuse the thesis's own explanation).

### 4.9 Municipal Explorer — `MunicipalExplorerView.vue` (nested by `:name?`) — the
cross-cutting, `atlas_app.js`-replacing route

```
┌───────────────────────────────────────────────────────────────────┐
│  Municipal Explorer                              (cross-cutting)   │
│  🔍 [ search municipality... ]                                      │
│  ┌───────────────── map: municipios.geojson (click-hit-test) ────┐ │
│  │  choropleth: [Opportunity score ▾] (dropdown: opportunity /   │ │
│  │   vulnerability / zone / suit_soybean / suit_sugarcane / ...) │ │
│  └───────────────────────────────────────────────────────────────┘ │
│  Selected: Simolândia (GO)                                          │
│  ┌── per-segment suitability (bar) ──┐ ┌── zone: Z1, ΔS(2051-70)──┐│
│  └────────────────────────────────────┘ └────────────────────────────┘│
│  Opportunity: 0.63 (top-3 statewide) · Vulnerability rank: —        │
└───────────────────────────────────────────────────────────────────┘
```
Components: a `<input>` search bound to a `ref<string>` filtering `MunicipalRankingFeature[]`,
`MapPanel.vue` (choropleth from `municipal_ranking.geojson`, click sets the `:name` route param and
`useSelectionStore` — the one genuinely cross-route Pinia state, so a deep link from Home or
another route can land here pre-selected), a `PlotlyChart.vue` per-segment bar, and `StatChip.vue`
instances for opportunity/vulnerability. This is the direct functional replacement for
`atlas_app.js`'s click-to-read panel — built entirely on `municipal_ranking.geojson`/`.csv`
(already exists) extended at Python build time to carry **all** 7 segments' suitability + zone +
ΔS values per municipality (not just the current curated 8 columns), so the click panel can show
everything without needing raw pixel decoding. No COG/PMTiles pixel query needed — this is
deliberately vector-only, satisfying the "click a municipality and read values" interaction the old
EE App had, at zero extra tiling cost.

### 4.10 About / Guardrails — `AboutView.vue`

```
┌───────────────────────────────────────────────────────────────────┐
│  About this Atlas                                                   │
│  · What this is / isn't (methodology-in-brief, links to thesis)     │
│  · Guardrails: land cover is mask-only, never a suitability input   │
│  · Why geomean vs. arithmetic mean (conservation)                   │
│  · Why comparative_segment, not raw dominance, labels zones          │
│  · Data provenance & citation block                                 │
│  · Link to full dissertation PDF / repo                             │
└───────────────────────────────────────────────────────────────────┘
```
Static-content route, no data dependencies — prose lives directly in the `.vue` template, pulled
near-verbatim from `CLAUDE.md` §7's guardrails and the thesis abstract.

---

## 5. Data asset manifest

Legend: **H** = hero (full interactive PMTiles), **G** = gallery (static PNG chip only), **V** =
vector (GeoJSON), **T** = tabular (CSV/JSON). All targets are under `docs/dashboard/public/data/`.

| Route | Asset | Source | Target | Tier |
|---|---|---|---|---|
| Study Area | `aoi` | EE FeatureCollection (`src/ibge_mesh.py`) | `geojson/aoi.geojson` | V |
| Study Area | `municipal_fc` | EE FeatureCollection (`src/ibge_mesh.py`) | `geojson/municipios.geojson` | V |
| Study Area | dataset catalog | `config/datasets.yaml` | `json/datasets_catalog.json` | T |
| Feature Themes | 1–2 repr. bands/theme (e.g. `clim_aridity`, `terr_slope`, `soil_clay`, `water_dist`, `phen_amplitude`, `access_logtt`, `sit_clearness`, `cv_wdpa_dist`) | `feat_*` EE assets | `pmtiles/feat_<band>.pmtiles` | H |
| Feature Themes | remaining ~30 bands | `feat_*` EE assets | `png/feat_<band>.png` | G |
| Feature Themes | per-band percentiles | offline `reduceRegion` | `json/band_percentiles.json` | T |
| Feature Stack | band/theme composition | static (from `STACK_THEMES`) | `json/stack_composition.json` | T |
| Suitability | `suit_present` (7 segments) | EE asset | `pmtiles/suit_<segment>.pmtiles` | H |
| Suitability | `class_<segment>` (7) | EE asset | `pmtiles/class_<segment>.pmtiles` | H |
| Suitability | `sens_<segment>` percentiles (7) | EE asset, `reduceRegion` | `json/sensitivity_<segment>.json` | T |
| Suitability | AHP weights + CR (7) | `config/ahp_matrices.yaml` | `json/ahp_matrices.json` | T |
| Suitability | membership breakpoints (7×factors) | `config/segments.yaml` | `json/segments.json` | T |
| Zoning | `zones_present` | EE asset | `pmtiles/zones_present.pmtiles` | H |
| Zoning | zone profiles | `zone_profiles.csv` (exists) | `csv/zone_profiles.csv` | T |
| Zoning | k-selection | `zoning_kselect.csv` (exists) | `csv/zoning_kselect.csv` | T |
| Zoning | factor variance | `factor_variance.csv` (exists) | `csv/factor_variance.csv` | T |
| Zoning | scale mismatch | `theme_roughness*.csv` (exist) | `csv/theme_roughness*.csv` | T |
| CMIP6 | `delta_<ssp>_<window>` for soy/cane/other_crops/conservation/solar | EE assets (5 of 7 segments) | `pmtiles/delta_<ssp>_<window>_<seg>.pmtiles` | H |
| CMIP6 | `agreement_<ssp>_<window>` (same 5) | EE assets | `pmtiles/agreement_<ssp>_<window>_<seg>.pmtiles` | H |
| CMIP6 | present/future climate small-multiples | reuse `fig_4_14.png` | `png/fig_4_14.png` | G |
| Realized Use | `feat_realized` (`rl_role`) | EE asset | `pmtiles/rl_role.pmtiles` | H |
| Realized Use | `underused_<crop>` (4) | EE asset | `pmtiles/underused_<crop>.pmtiles` | H |
| Validation | scorecard numbers | thesis tables (hand-transcribed once) | `json/validation_scorecard.json` | T |
| Municipal Explorer | extended municipal ranking (all 7 segments + zone + ΔS) | extend `tools/extract_present.py`'s `municipal()` | `geojson/municipal_ranking.geojson` (extended), `csv/municipal_ranking.csv` | V+T |

Total hero PMTiles count: ~9 (feature themes) + 14 (7 suit + 7 class) + 1 (zones) + 20 (5 segments
× 2 SSP × 2 windows delta) + 20 (agreement, same count — optional, could cut to fewer segments if
size becomes a problem) + 5 (realized/underused) ≈ **69 PMTiles files**. This is the number to
watch against the §2.4 size risk; agreement layers are the first candidate to cut if needed (they
were already the least load-bearing layer in the thesis — near-uniform 0.92–1.00 everywhere).

Every row above has a corresponding TypeScript interface in `src/types/data.ts` (e.g.
`DatasetCatalogEntry`, `SegmentConfig`, `AhpMatrix`, `ZoneProfileRow`, `ZoningKselectRow`,
`FactorVarianceRow`, `ValidationScorecardRow`, `MunicipalRankingFeature`) — the Python build script
and the Vue app are two independent codebases, and these interfaces are the only contract between
them, so keeping them named 1:1 with the manifest rows above matters for future maintainers.

---

## 6. Migration / decommission checklist

- [ ] Delete `gee_js/atlas_app.js`.
- [ ] `CLAUDE.md` §4 — rewrite the Part 15 row: "App script written, NOT published" →
      "Static Vue+TS dashboard (`docs/dashboard/`), built by Vite and deployed via GitHub Actions
      — see `docs/dashboard_ux_plan.md`"; update "Immediate next step" to point at scaffolding the
      dashboard, not publishing an EE App.
- [ ] `CLAUDE.md` §5 (layout) — remove the `gee_js/atlas_app.js` line; add `docs/dashboard/`
      (Vue/TS/Vite project), `tools/build_dashboard_assets.py`, `tools/palettes.py`, and
      `.github/workflows/deploy-dashboard.yml`.
- [ ] `CLAUDE.md` §6 — no change needed (asset table is about EE assets, not the app).
- [ ] `CLAUDE.md` §8 (environment) — note that `docs/dashboard/` has its own Node/npm toolchain,
      independent of the `uv`-managed Python environment; running the site never needs `uv`.
- [ ] `README.md` — update Part 15 description for GitHub visitors to point at the live GitHub
      Pages URL once deployed.
- [ ] Repo **Settings → Pages**: set "Build and deployment" source to **GitHub Actions**.
- [ ] `notebooks/15_atlas_app.ipynb` — retarget via `tools/gen_notebooks.py` once
      `tools/build_dashboard_assets.py` exists (thin notebook: call the build script, verify
      output counts), replacing its current "mirror gee_js/atlas_app.js" spec.

---

## 7. Phasing

**v0 (scaffold)** — `npm create vite@latest -- --template vue-ts` inside `docs/dashboard/`; add
Vue Router (hash history) + Pinia; write `App.vue`'s shell (header/nav/`<router-view>`) and the
`useJson`/`useCsv` composables + `src/types/data.ts` skeleton; wire the empty `deploy-dashboard.yml`
workflow end-to-end against a placeholder "hello world" route, so the CI → Pages path is proven
before any real content lands.

**v1 (core RQ coverage)** — Home, Suitability Modelling, Agro-Environmental Zoning, Municipal
Explorer. These four carry RQ1 and the most novel "show your work" content (membership curves, AHP
weights, zone profiles) plus the municipal click-through that most directly succeeds
`atlas_app.js`.

**v2** — Study Area & Data, Feature Themes, Feature Stack (build out the full feature-engineering
story), Climate Shift/CMIP6, Realized Use & Potential Gap, Validation, About.

Rationale: v1 is buildable from data that already exists almost entirely as CSVs
(`zone_profiles.csv`, `segments.yaml`, `ahp_matrices.yaml`, `municipal_ranking.csv`) plus a handful
of GEE exports (`suit_present`, `zones_present`), so it can ship without the full ~69-PMTiles
build-out, letting the size-risk (§2.4) get resolved with real numbers before committing to the
full manifest. v0 is small on purpose — it exists to de-risk the CI/Pages pipeline (a new moving
part this revision introduces) independently of any content work.

---

## 8. Verification plan (for the future build session)

1. **Type-check:** `cd docs/dashboard && npm run type-check` (`vue-tsc --noEmit`) — must pass with
   zero errors before every build; wired into CI (§2.5) so it gates deploys, not just a local habit.
2. **Local production smoke test:** `npm run build && npm run preview`, open in a browser, confirm
   every route loads without console errors and every PMTiles layer renders at the correct AOI
   extent (same footprint-check philosophy as `tools/verify_assets.py`). `vite preview`'s `sirv`
   server honors `Range` requests out of the box, so this is a faithful stand-in for GitHub Pages'
   PMTiles behavior — no need for the `python -m http.server` / `npx serve` workaround the earlier
   plan called for.
3. **Mobile-width check:** resize to a phone-width viewport; nav must collapse/scroll sanely, maps
   must not overflow.
4. **Data-consistency spot-check:** pick 3 numbers shown on the dashboard (e.g. soy underused
   48.0%, κ=0.07, k=7 silhouette) and confirm they match the corresponding thesis table exactly —
   guards against a stale export, a stale TS interface, or a copy-paste error in
   `validation_scorecard.json`.
5. **GitHub Pages deploy dry-run:** push to a branch, open the workflow run in the Actions tab,
   confirm the `build`/`deploy` jobs both succeed and the live URL (`https://<user>.github.io/
   <repo-name>/`) matches the local `npm run preview` smoke test — including the `base` path
   resolving correctly (a common first-deploy bug: assets 404 under `/<repo-name>/` if `base` was
   left at Vite's default `/`).

   > Item 4's example numbers are now stale — see §9: zoning is currently K=10, not
   > k=7 (`zone_profiles.csv` row count is the ground truth, not this list).

---

## 9. Build log

Running log of what's actually been built against this spec, kept up to date as each phase lands —
read this before resuming work, especially after the CMIP6/realized-use pipeline rebuild finishes.

### v0 — scaffold (2026-09-19, done)

Built and verified end-to-end per §7/§8: Node installed via nvm (v24.21.0 LTS, not previously
present on this machine), `docs/dashboard/` scaffolded with `npm create vite@latest -- --template
vue-ts`, Vue Router (hash history) + Pinia wired, `useJson`/`useCsv` composables + `src/types/
data.ts` skeleton written, `.github/workflows/deploy-dashboard.yml` written (repo's first
workflow — `base: '/goias_suitability/'`, confirmed from `git remote`, not the local checkout
folder name which is `goias_suitability-main`). Verified: the type-check gate actually fails on a
broken type (not a no-op against the template's solution-style tsconfig — required switching
`type-check` to `vue-tsc --build --force`, not the literal `--noEmit`), `npm run build` +
`npm run preview` served correctly under the base path with zero 404s. **Not yet pushed** — the
GitHub Actions run / live Pages URL / repo Pages-source setting are still unverified in practice.

### v1 — Home, Suitability, Zoning, Municipal Explorer (2026-09-19, done)

**Scope negotiated with the user first:** the CMIP6 forecast + realized-use rebuild was running in
the background during this session. Confirmed safe to pull: everything up to and including
`zones_present`/`suit_present*` (Parts 1–10 + 12, the IBGE municipal mesh). Confirmed **off-limits**
(still recomputing as of 2026-09-19): `suit_future*`, `delta_*`, `agreement_*`,
`realized_vs_potential`, `feat_realized`. This is why Climate Shift, Realized Use, and Validation
stayed out of v1 (they need those assets) even though the UI shell would have been easy to add —
**re-run `tools/build_dashboard_assets.py` for those layers once the pipeline settles**, don't just
add the routes against stale/absent data.

**New tools:**
- `tools/palettes.py` — palettes shared between `make_figures.py` and the dashboard build (as
  §2.2 specified). `make_figures.py` now imports from it instead of redefining the constants
  inline; behavior verified unchanged (`--check-i18n` still passes).
- `tools/build_dashboard_assets.py` — implements §2.3 for the v1-safe asset set: vectors
  (`aoi.geojson`, `municipios.geojson`, pure geopandas, no EE call), config→JSON
  (`segments.json`, `ahp_matrices.json`), a **new, v1-safe** `municipal_ranking.csv`/`.geojson`
  (all 7 `suit_*` + `zone`, no `delta_other_crops`/`underused_*` — those columns in the *existing*
  `thesis/Chapters/Figures/municipal_ranking.csv` depend on the off-limits assets, so this is a
  separate file, not an overwrite), diagnostic CSV passthrough, `sensitivity_<segment>.json`
  (percentiles, not a full histogram — that's what `reduceRegion` actually gives us), and all 15
  hero raster PMTiles layers (`suit_<segment>`×7, `class_<segment>`×7, `zones_present`). Run with
  `--only {vectors,config,municipal,diagnostics,rasters,home_stats}` for one stage at a time.
- **New Python deps** (`uv add rio-pmtiles`): pulled in `rasterio` and the `pmtiles` package too.
  `pyproject.toml`/`uv.lock` now reflect this — not previously present.

**Two real bugs found while building the export script (both fixed):**
1. `getDownloadURL` has a 48 MiB cap; a full-AOI float32 250 m band is ~93 MB. Fixed by casting
   each band to `uint8` server-side before download (continuous bands scaled ×254, sentinel value
   255 = nodata) — ~23 MB, and plenty of precision for a colorized visualization tile. See
   `_prep_band`/`_colorize` in `build_dashboard_assets.py`.
2. The first vector export used **full-precision** geometry for `municipios.geojson` and
   `municipal_ranking.geojson` (only the dissolved AOI was simplified) — 100 MB for 247 polygons.
   Fixed by applying `config/datasets.yaml`'s `municipal_mesh.simplify_tolerance_deg` to the
   per-municipality layer too, matching what `ibge_mesh.municipal_ee_fc()` already does. Now 6 MB
   total for all three vector files. **Lesson for the future export passes:** always simplify
   per-feature geometry explicitly — `ibge_mesh._load_gdf()` returns full precision by design (the
   committed `.gpkg` is meant to stay full precision; simplification is the caller's job).

**Total `public/data/` size so far: ~72 MB** (66 MB pmtiles, 6 MB geojson, <1 MB csv/json) — well
inside the §2.4 risk budget; no LFS/release-asset workaround needed yet at this scale.

**Frontend additions:** `MapPanel.vue` (MapLibre + PMTiles, blank background style — no external
basemap tile dependency), `PlotlyChart.vue` (needed a `plotly.js-dist-min` type shim —
`@types/plotly.js` only types the `plotly.js` module name; see `src/types/plotly-dist-min.d.ts`),
`SegmentSelector.vue`, `StatChip.vue`, `ZoneCard.vue`, `useMapLayer.ts`. `DataTable.vue` from the
§2.6 inventory was **not** built — its only listed consumers (Study Area, Validation) are v2 routes,
so it would have shipped unused.

**A real reactivity bug in the v0 composables surfaced immediately:** `useJson`/`useCsv` fetched
once at call time and never reacted to the path argument changing — fine for v0's static Home
fetch, broken for v1's per-segment sensitivity JSON. Fixed by accepting `MaybeRefOrGetter<string>`
and wrapping the fetch in `watchEffect` (with a request-token guard against a stale response
overwriting a newer one). Any v2 code calling these with a dynamic path should already get this for
free; static-string call sites are unaffected.

**Bundle size:** `plotly.js-dist-min` alone is ~1.4 MB gzipped. Router routes are now lazy-loaded
(`component: () => import(...)`) so Home doesn't pay for Plotly, matching the "curated, not every
permutation" spirit of §1. `maplibre-gl` (~140 KB gzip) still loads on every route including Home,
since Home's hero map needs it too — that one's structural, not a splitting opportunity.

**Found, deliberately NOT fixed (flagged for a separate decision):** `zone_profiles.csv` now has
**10 zones (0–9), not 7**. CLAUDE.md §4's Part-10 row ("BUILT — K=7") and
`tools/make_figures.py`'s zoning-figure call (`visualize(min=0, max=6, palette=PAL_ZONE)`, a
7-color palette) are both stale against this — a rezone appears to have run since either was last
updated (`zone_profiles.csv` was already showing as locally modified at the start of this session).
The dashboard reads the zone count from data (`zone_count()` in the build script, never a hardcoded
literal), so it renders correctly either way — but **the thesis PDF's zoning figure is likely
rendering with a truncated palette/wrong value range right now.** Worth checking before the next
`make_figures.py all` run regenerates it.

**Not committed / not pushed** (per standing instruction not to commit without being asked).

### Still open before v2

- Push v0+v1, confirm the Pages deploy actually works live (§8 item 5) — never done yet, only
  simulated locally via `vite preview`.
- Once the CMIP6/realized-use pipeline settles: re-run the build script's deferred layers
  (`delta_*`/`agreement_*` PMTiles, `underused_*`, extend `municipal_ranking` back with those
  columns), then build Climate Shift + Realized Use + Validation views.
- Decide on the `zone_profiles.csv` K=7→K=10 doc drift (CLAUDE.md §4, `make_figures.py` zoning
  figure) — separate from the dashboard, but noticed while building it.
- `home_stats.json` deliberately has no κ/AUC/underuse numbers (those need the off-limits assets)
  — revisit once `validation_scorecard.json` exists (v2).
