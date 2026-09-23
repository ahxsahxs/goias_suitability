# Goiás Agro-Market Suitability Atlas — Dashboard Architecture

Architecture reference for `docs/dashboard/`, the public, static, GitHub-Pages-hosted dashboard
that is the project's **only** interactive deliverable (Part 15). It superseded and replaced the
retired `gee_js/atlas_app.js` (Earth Engine App). It is live at
<https://ahxsahxs.github.io/goias_suitability>, all 11 routes are built, and it is linked from the
thesis. See `CLAUDE.md` §4 for current build/deploy status.

---

## 1. What it is

A static Vue 3 + TypeScript + Vite single-page app that serves every one of the 14 built pipeline
parts (feature engineering → suitability → zoning → CMIP6 → validation → municipal explorer) as a
distinct, navigable route, showing both final results and key intermediate modelling artifacts
(fuzzy membership curves, AHP weight bars, k-selection diagnostics), not just the finished maps.

It runs entirely on pre-exported static assets at view time — no GEE authentication, no server, no
database — and is not a replacement for the thesis PDF, but a companion explorer that cross-links
to chapter/table/figure numbers.

**Stack:** Vue 3 (Composition API) + Vue Router (hash history, so GitHub Pages needs no
server-side rewrites) + TypeScript (strict); MapLibre GL JS + PMTiles for every map panel (PMTiles
chosen because GitHub Pages has no tile server — it's a single-file tile pyramid served via HTTP
range requests, which GitHub Pages' CDN supports natively); Plotly.js for every chart; Papaparse
for typed CSV parsing; Pinia used only for the one genuinely cross-route state (the municipality
selected in the Municipal Explorer, for deep links); no CSS framework.

---

## 2. Where things live

- `docs/dashboard/` — the Vue project source (`src/`, `public/data/`); `dist/` is the gitignored
  build output that CI actually deploys.
- `tools/build_dashboard_assets.py` — the Python pipeline that exports GEE rasters/vectors,
  converts COGs to PMTiles (via `tools/palettes.py` for shared color ramps with
  `tools/make_figures.py`), and converts `config/*.yaml` to JSON, writing everything into
  `docs/dashboard/public/data/`.
- `.github/workflows/deploy-dashboard.yml` — CI: type-check + `vite build` + deploy to GitHub
  Pages, triggered on push to `docs/dashboard/**`.

Data volume: ~69 PMTiles files (~136 MB total under `public/data/`), comfortably inside GitHub
Pages' size limits — no Git LFS needed.

---

## 3. Routes

11 routes total, each mapped to a pipeline Part; routes with a segment/scenario dimension carry it
as a Vue Router param (e.g. `/suitability/:segment`) so a specific view is directly linkable.

| # | Route | Pipeline Part(s) | Primary question it answers |
|---|---|---|---|
| 0 | `/` (Home) | — | What is this, and what are the 3 RQs? |
| 1 | `/study-area` | Part 1 | Where is the study area, what datasets feed it? |
| 2 | `/feature-themes/:theme?` | Parts 2–7d | What does each of the 8 biophysical themes look like? |
| 3 | `/feature-stack` | Part 8 | How do the 34 bands combine, raw vs. standardized? |
| 4 | `/suitability/:segment?` | Part 9 | How is each segment's suitability derived (fuzzy+AHP)? |
| 5 | `/zoning` | Part 10 | How is GO/DF partitioned into zones? (RQ1) |
| 6 | `/cmip6/:ssp?/:window?/:segment?` | Part 11 | How does suitability shift by 2050/2070? (RQ3) |
| 7 | `/realized-use/:crop?` | Parts 12–13 | Where is potential under-utilized? (RQ2) |
| 8 | `/validation` | Part 14 | How trustworthy is the model (AUC/Boyce/κ/Spearman)? |
| 9 | `/municipal/:name?` | cross-cutting (9–14) | What does *my* municipality look like, across all of it? |
| 10 | `/about` | — | Methodology caveats, data sources, how to cite. |

---

## 4. Build & deploy

```bash
# local dev (Vite HMR, reads straight from public/data/ on disk)
cd docs/dashboard && npm install && npm run dev

# type-check + production build -> dist/
npm run type-check && npm run build

# local production preview (faithful stand-in for GitHub Pages' PMTiles range-request behavior)
npm run preview
```

CI (`deploy-dashboard.yml`) runs the same type-check + build, uploads `dist/` as a Pages artifact,
and deploys it. Repo setting: **Settings → Pages → Build and deployment → Source: GitHub Actions**
(already done).

Regenerating the data pipeline (after any asset re-export that changes a mapped layer):

```bash
EE_PROJECT=probformer uv run python tools/build_dashboard_assets.py
```

---

## 5. Verification checklist

1. **Type-check:** `npm run type-check` (`vue-tsc --noEmit`) — zero errors, gated in CI.
2. **Local production smoke test:** `npm run build && npm run preview`, confirm every route loads
   without console errors and every PMTiles layer renders at the correct AOI extent.
3. **Mobile-width check:** phone-width viewport — nav collapses/scrolls sanely, maps don't overflow.
4. **Data-consistency spot-check:** pick a few headline numbers shown on the dashboard (e.g. soy
   underused 41.8%, κ=+0.269, k=10) and confirm they match the *current* thesis tables exactly —
   guards against a stale export or a stale TS interface.
5. **GitHub Pages deploy dry-run:** push, confirm the `build`/`deploy` jobs succeed and the live
   URL matches the local `npm run preview` smoke test, including the `base` path resolving
   correctly under `/<repo-name>/`.
