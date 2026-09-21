# Goiás Agro-Market Suitability Atlas — Static Dashboard Architecture

Architecture reference for `docs/dashboard/`, the public, static, GitHub-Pages-hosted dashboard
that is the project's **only** interactive deliverable (Part 15). It superseded and replaced the
retired `gee_js/atlas_app.js` (Earth Engine App) plan. The dashboard was built against this spec —
see `CLAUDE.md` §4 for current build/deploy status, and the commit history
(`41a7dfe`, `798f45e`, `be25a40`) for how it was built. Two follow-ups remain before it's linked
from the thesis: an i18n pass + trimming some images, and enabling GitHub Pages
(Settings → Pages → Source → "GitHub Actions").

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

### 2.4 Static asset volume

GitHub repos/Pages have an informal ~1 GB soft ceiling and a 100 MB hard per-file limit (without
Git LFS). The full built manifest (~50 PMTiles files across feature themes, suitability, zoning,
CMIP6 delta/agreement, and realized-use layers) comes to **~136 MB** under `docs/dashboard/public/
data/`, with no single file exceeding ~7 MB — comfortably inside the budget, so no `git-lfs` /
GitHub-Release-asset workaround was needed.

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
│  ┌───────────────── hero map: zones_present (K=10) ────────────┐   │
│  │                [interactive MapLibre, PMTiles]               │   │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Headline numbers:  10 zones · 7 segments · 5-GCM ensemble ·        │
│  soy underuse 41.8% · κ=0.269 (RF-vs-knowledge) · AUC=0.871 (soy)   │
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
│  Agro-Environmental Zoning (K=10)                      (Part 10)   │
│  ┌───────────────── zone map (PMTiles, 10 colors) ────────────┐   │
│  └────────────────────────────────────────────────────────────────┘│
│  Zone: [Z0]..[Z9]  → click a zone card:                             │
│  ┌── Z5: comparative "privileged crop plateau" — soy/cane ──────┐ │
│  │  bar: mean rel_suit_* per segment (z-normalized)               │ │
│  │  17.6% of territory (largest zone) · realized composition ...  │ │
│  └───────────────────────────────────────────────────────────────┘ │
│  k-selection diagnostics (silhouette/DB/gap/ARI vs k) — why k=10    │
│  Factor variance decomposition (per-segment, which factors drive it)│
│  Scale-mismatch (climate vs. terrain+soil roughness, 42×–320×)      │
└───────────────────────────────────────────────────────────────────┘
```
Components: `MapPanel.vue` (PMTiles zone map), N `ZoneCard.vue` instances — N is read from
`zone_profiles.csv`'s row count at run time, never hardcoded to 7 or 10 (typed `ZoneProfileRow[]`
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
│  Realized-composition table · underused-share bar (41.8/51.6/57.3/9.4%)│
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
│  ┌────────────┬───────┬───────┐                                    │
│  │ Segment    │ AUC   │ Boyce │                                    │
│  │ Soybean    │ 0.871 │ 0.964 │                                    │
│  │ Sugarcane  │ 0.821 │ 0.769 │                                    │
│  │ Other crops│ 0.698 │ 0.792 │                                    │
│  └────────────┴───────┴───────┘                                    │
│  NPP Spearman by segment (bar) · within-crop GPP gradient (bar)     │
│  RF cross-check: κ=+0.269 (n=16160) — knowledge map marks 52.8% of  │
│  the territory viable vs. 21.6% for the RF classifier               │
│  [ why the gap? → prose in the view itself, ties to 04_results.tex ]│
└───────────────────────────────────────────────────────────────────┘
```
Components: `DataTable.vue` typed against a flattened `presence_auc_boyce` (`validation_scorecard.json`),
a `PlotlyChart.vue` Spearman bar, a `PlotlyChart.vue` within-crop GPP-gradient bar (a bar of rho per
crop, not a true point scatter — the scorecard only carries the summary statistic, not raw points),
and a short prose callout (static content in the `.vue` template) on the AUC/κ discrepancy (point 4
of the revision cycle) using the *current* thesis framing (52.8% vs. 21.6% area, a single
stratified-sample kappa) — not the older "in-sample vs. spatial-block-CV" framing this wireframe
used to describe, which no longer matches what `tools/run_validation.py` actually computes.

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

## 6. Migration from `gee_js/atlas_app.js`

The migration is complete: `gee_js/atlas_app.js` (the Earth Engine App) was deleted and replaced by
this static SPA. `CLAUDE.md` §4/§5 and `README.md` describe the current dashboard state; the only
open infrastructure step is enabling GitHub Pages (Settings → Pages → Source → "GitHub Actions").

---

## 7. Phasing

The dashboard was delivered in three incremental phases: **v0** scaffolded the Vue Router/Pinia
shell and proved the CI → Pages build pipeline against a placeholder route; **v1** shipped the four
routes carrying RQ1's core content (Home, Suitability Modelling, Agro-Environmental Zoning,
Municipal Explorer); **v2** completed the remaining seven routes (Study Area, Feature Themes,
Feature Stack, Climate Shift/CMIP6, Realized Use & Potential Gap, Validation, About). All 11 routes
in §3 are built.

---

## 8. Verification plan

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
   41.8%, κ=+0.269, k=10 silhouette) and confirm they match the corresponding *current* thesis
   table exactly — guards against a stale export, a stale TS interface, or a copy-paste error in
   `validation_scorecard.json`.
5. **GitHub Pages deploy dry-run:** push to a branch, open the workflow run in the Actions tab,
   confirm the `build`/`deploy` jobs both succeed and the live URL (`https://<user>.github.io/
   <repo-name>/`) matches the local `npm run preview` smoke test — including the `base` path
   resolving correctly (a common first-deploy bug: assets 404 under `/<repo-name>/` if `base` was
   left at Vite's default `/`).
