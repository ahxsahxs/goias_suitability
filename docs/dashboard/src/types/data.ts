/**
 * TypeScript contracts for everything under public/data/.
 *
 * These interfaces are the ONLY contract between the Python exporter
 * (tools/build_dashboard_assets.py) and this app (docs/dashboard_ux_plan.md §2.1,
 * §5). Keep names 1:1 with the §5 manifest rows.
 */

/** Result of a client-side fetch of a static data file. */
export interface AsyncResult<T> {
  data: T | null
  error: Error | null
  loading: boolean
}

/** A parsed CSV row, before it is narrowed to a concrete manifest row type. */
export type CsvRow = Record<string, string | number | boolean | null>

// --- config/segments.yaml -> json/segments.json --------------------------------
export interface FaoClasses {
  breaks: number[]
  codes: Record<string, number>
}
export interface AggregationConfig {
  epsilon: number
  sensitivity_delta: number
  /** Exponent of the regional adaptation w = normalize(w_lit * sigma(mu)^lambda). */
  lambda_regional: number
  /** Spatial-holdout half sigma(mu) was measured on (machine-written by derive_weights). */
  derived_half: 'calib' | 'val' | 'full'
}
export type MembershipType = 'increasing' | 'decreasing' | 'range'
/**
 * Every factor is `limiting`: it enters the weighted aggregation and carries a
 * derived weight (`role: gate` was retired on 2026-10-02 — CLAUDE.md §11). A
 * factor may omit `role`; it is limiting either way. Factors that are spatially
 * constant today are handled by measuring sigma(mu) over the present pooled with
 * the CMIP6 horizon; some still land at weight exactly 0.
 */
export type FactorRole = 'limiting'
/** How a factor's BREAKPOINTS were placed (segments.yaml `anchor.rule`). */
export type AnchorRule = 'percentile' | 'mu_one' | 'agronomic'
export interface FactorConfig {
  /** Machine-written by tools/derive_weights.py; never hand-edited. */
  weight: number
  role?: FactorRole
  anchor?: { rule: AnchorRule; mask?: string; points?: Record<string, string> }
  type: MembershipType
  points: number[]
  /** How the BREAKPOINTS were set, not how the weight was derived. */
  basis: 'literatura' | 'empirico'
  source?: string
  locator?: string
  note: string
}
export interface SegmentDef {
  label: string
  mask: string
  aggregate?: 'arithmetic'
  factors: Record<string, FactorConfig>
}
export interface SegmentsConfig {
  fao_classes: FaoClasses
  aggregation: AggregationConfig
  extras_prefixes: Record<string, string>
  segments: Record<string, SegmentDef>
}

// --- config/ahp_matrices.yaml -> json/ahp_matrices.json -------------------------
/** One hand-written anchor: an ordinal band, plus the published priority when
 *  the factor maps onto a source criterion. */
export interface AhpAnchor {
  band: number
  r?: number
  rank?: number
  n_criteria?: number
  source?: string
  locator?: string
  block?: string
  rationale: string
}
/** Everything tools/derive_weights.py writes back. */
export interface AhpDerived {
  bands_final: Record<string, number>
  matrix: number[][]
  judgements: { pair: [string, string]; a_ij: number; rule: string; basis: string; source: string }[]
  lambda_max: number
  consistency_index: number
  random_index: number
  consistency_ratio: number
  /** w_lit — the literature prior, before the regional adaptation. */
  priority_vector: number[]
  approx_eigenvector_max_gap: number
  class_counts: { A: number; B: number; C: number }
  /** Share of pairwise judgements taken directly from a published priority ratio. */
  anchored_fraction: number
  author_judgement_count: number
  override_count: number
  revisions: Record<string, string | number>[]
}
export interface AhpSegment {
  factors: string[]
  anchors: Record<string, AhpAnchor>
  derived: AhpDerived
}
export interface AhpMatrices {
  scale: { allowed: number[]; cr_threshold: number; max_revisions_per_segment: number }
  segments: Record<string, AhpSegment>
}

// --- csv/ahp_weights.csv ---------------------------------------------------------
export interface AhpWeightRow {
  /**
   * Spatial-holdout half that sigma(mu) was measured over ('calib' since
   * 2026-10-03). Present so the file says which domain produced it; the file
   * carries one domain at a time, so views need not filter on it.
   */
  half?: 'calib' | 'val' | 'full'
  segment: string
  factor: string
  /** Literature prior (principal eigenvector of the pairwise matrix). */
  w_lit: number
  /**
   * sigma(mu) — the regional discriminating power. Measured over available land
   * in the CALIBRATION half, pooled over the present and the CMIP6 horizon
   * (not the present alone, which would zero any factor already saturated today
   * and drop it out of the geometric mean together with its climate lever).
   */
  d: number
  w_final: number
  w_atual: number | null
  delta: number | null
}

// --- json/sensitivity_<segment>.json --------------------------------------------
export interface SensitivitySummary {
  p5: number
  p25: number
  p50: number
  p75: number
  p95: number
}

// --- csv/zone_profiles.csv ------------------------------------------------------
// Named columns are the ones views consume directly; the index signature covers
// the remaining raw climate/terrain/soil covariate columns carried in the file.
export interface ZoneProfileRow {
  zone: number
  /**
   * Row count of the STRATIFIED sample behind this zone -- NOT an area share.
   * Dividing it by the column total understates zone 1 by 8.5 points and
   * overstates zone 3 by 7.5. Territory shares come from ZoneAreaRow
   * (csv/zone_area.csv, a pixelArea() group reduce). See CLAUDE.md §9.
   */
  n: number
  comparative_segment: string
  /** Runner-up comparative vocation, and the z-gap from it to the winner. */
  comparative_segment_2: string
  comparative_margin: number
  top_features: string
  suit_soybean: number
  suit_sugarcane: number
  suit_other_crops: number
  suit_pisciculture: number
  suit_cattle: number
  suit_conservation: number
  suit_solar: number
  rel_suit_soybean: number
  rel_suit_sugarcane: number
  rel_suit_other_crops: number
  rel_suit_pisciculture: number
  rel_suit_cattle: number
  rel_suit_conservation: number
  rel_suit_solar: number
  rl_soybean_frac: number
  rl_sugarcane_frac: number
  rl_other_crops_frac: number
  rl_pasture_frac: number
  rl_native_frac: number
  [key: string]: string | number
}

// --- csv/zone_area.csv ----------------------------------------------------------
// The ONLY source for "how big is zone N": a pixelArea() group reduce written by
// tools/extract_present.zone_shares. zone_profiles.csv's `n` is a sample count and
// must never stand in for it (CLAUDE.md §9).
export interface ZoneAreaRow {
  zone: number
  area_km2: number
  share_pct: number
}

// --- csv/zoning_kselect.csv ------------------------------------------------------
// Two families of column, deliberately named apart so they cannot be confused:
//   *_calib / ari_subsample  measured on the CALIBRATION half. ari_subsample is
//     reproducibility under resampling -- each replicate relabels the whole
//     sample -- so it is NOT out-of-sample validity.
//   *_val / ari_holdout      measured on the HELD-OUT half of the spatial split.
//     ari_holdout compares the calibration-fitted partition of that half against
//     one fitted independently on it. The adopted k rests on these.
// No fallback to the pre-holdout names: a CSV without the held-out columns is a
// wrong table, not a missing one (CLAUDE.md §11), and the view refuses it.
export interface ZoningKselectRow {
  k: number
  inertia: number
  gap: number
  s_k: number
  /** calibration half */
  silhouette_calib: number
  davies_bouldin_calib: number
  ari_subsample: number
  ari_subsample_std: number
  /** held-out half */
  silhouette_val: number
  davies_bouldin_val: number
  ari_holdout: number
}

// --- csv/factor_variance.csv -----------------------------------------------------
export interface FactorVarianceRow {
  segment: string
  factor: string
  weight: number
  variance_share: number
}

// --- csv/municipal_ranking.csv (7 suit_*, zone, 7 delta_* off delta_ssp585_2051_2070,
// and every underused_<crop> band that exists on realized_vs_potential — currently 4) --
export interface MunicipalRankingRow {
  NM_MUN: string
  SIGLA_UF: string
  zone: number
  suit_soybean: number
  suit_sugarcane: number
  suit_other_crops: number
  suit_pisciculture: number
  suit_cattle: number
  suit_conservation: number
  suit_solar: number
  delta_soybean: number
  delta_sugarcane: number
  delta_other_crops: number
  delta_pisciculture: number
  delta_cattle: number
  delta_conservation: number
  delta_solar: number
  underused_soybean: number
  underused_sugarcane: number
  underused_other_crops: number
  underused_pisciculture: number
}

// --- geojson/municipal_ranking.geojson properties --------------------------------
export interface MunicipalRankingProperties extends MunicipalRankingRow {
  CD_MUN: string
  NM_UF: string
}

// --- geojson/municipios.geojson properties ---------------------------------------
export interface MunicipioProperties {
  CD_MUN: string
  NM_MUN: string
  SIGLA_UF: string
  NM_UF: string
}

// --- json/datasets_catalog.json (config/datasets.yaml) ---------------------------
export interface DatasetCatalogEntry {
  theme: string
  source: string
  id: string
  native_res: string
  period: string
}

// --- json/stack_composition.json (band names of the exported feature_stack_250m) ---
export interface StackComposition {
  themes: Record<string, number>
  total_bands: number
  bands: string[]
  zoning_bands: string[]
  excluded: string[]
  note: string
}

// --- json/pca_compare.json (build_pca_compare: the whole z-stack vs ZONING_BANDS) ---
// Variant keys are semantic, never band counts: the stack has gone 34 -> 29 bands and
// ZONING_BANDS 15 -> 13, and keys naming a count silently stop matching the emitter.
// Read the count from `bands.length`.
export interface PcaVariant {
  bands: string[]
  /** Band-name prefix per band: clim/terr/soil/water. */
  themes: string[]
  /** 1/√(bands-in-theme) for the curated variant; all 1 for the full stack. */
  weights: number[]
  explained_variance_ratio: number[]
  n_pc_90: number
  /** Per band, [PC1, PC2, PC3] loadings (same order as `bands`). */
  loadings: [number, number, number][]
  /** p2/p98 of PC1..3 — the stretch baked into pca_rgb_<key>.pmtiles. */
  pc_domain: [number, number][]
  /** Silhouette of the zones_present labels in PC1–3, on the shipped points. */
  zone_silhouette_pc3: number
}

export interface PcaPoints {
  pc_full: [number, number, number][]
  pc_curated: [number, number, number][]
  /** 1-based zone ids (zones_present + 1), like zone_profiles.csv. */
  zone: number[]
  lon: number[]
  lat: number[]
  terr_elev: number[]
  clim_aridity: number[]
  soil_clay: number[]
}

export interface PcaCompare {
  variants: { full: PcaVariant; curated: PcaVariant }
  n_sample: number
  points: PcaPoints
}

// --- json/band_percentiles.json (P5/P25/P50/P75/P95 per hero band) ---------------
export interface BandPercentileSummary {
  p5: number
  p25: number
  p50: number
  p75: number
  p95: number
}
export type BandPercentiles = Record<string, BandPercentileSummary>

// --- json/validation_scorecard.json (validation_metrics.csv, held-out half) ------
export interface PresenceAucBoyceRow {
  auc: number
  boyce: number
  /** evaluated pixels / of which presences, on the held-out half */
  n: number
  presences: number | null
}
export interface WithinCropGradientRow {
  rho: number
  n: number
}
export interface ZoneAnova {
  f: number
  p_approx: number
  zone_mean_range: [number, number]
  /** 1-based zone ids; mean MOD17 NPP (scaled units) and sample size per zone */
  zones: { zone: number; mean_npp: number; n: number }[]
}
export interface RfKappa {
  soybean: number
  n: number
  knowledge_area_pct: number
  rf_area_pct: number
  note: string
}
export interface ValidationScorecard {
  /** Which half of the spatial holdout these metrics were scored on. `"val"` is
   *  the held-out half the thesis quotes; see CLAUDE.md §7. */
  half: string
  presence_auc_boyce: Record<string, PresenceAucBoyceRow>
  spearman_npp: Record<string, number>
  spearman_npp_p: Record<string, number>
  spearman_npp_n_municipalities: number
  spearman_npp_notes: Record<string, string>
  within_crop_gpp_gradient: Record<string, WithinCropGradientRow>
  zone_anova: ZoneAnova
  rf_kappa: RfKappa
  underuse_pct: Record<string, number>
  source: string
}

// --- json/home_stats.json ---------------------------------------------------------
export interface HomeStats {
  n_zones: number
  n_segments: number
  n_municipalities: number
  mean_suit_soybean: number
  top_zone: number
  top_zone_share_pct: number
  kappa_soybean: number | null
  auc_soybean: number | null
  boyce_soybean: number | null
  underused_soybean_pct: number | null
  /** Most negative territory-mean ΔS over every segment x scenario (tab:shift-mean). */
  worst_delta: { segment: string; ssp: string; window: string; delta_s: number }
}

// --- json/manifest.json (build_dashboard_assets.build_manifest) --------------------
// Every count, list, domain and pt-BR label the views would otherwise hardcode. The
// numbers come from the pipeline; the words from config/dashboard.yaml, checked at
// build time against the thesis' own table labels and against K.
export interface ManifestSegment {
  key: string
  label: string
  short: string
}
export interface ManifestZone {
  /** 1-based, canonical (descending mean elevation). */
  zone: number
  /** Landform descriptor (editorial, config/dashboard.yaml). */
  name: string
  comparative_segment: string
  comparative_segment_2: string
  comparative_margin: number
  /** margin < zone_pair_margin: the zone reads as a PAIR of vocations. */
  paired: boolean
  area_km2: number
  share_pct: number
  mean_elev_m: number
}
export interface ManifestWindow {
  key: string
  start: number
  end: number
}
export interface Manifest {
  generated_at: string
  git_sha: string | null
  segments: ManifestSegment[]
  zones: ManifestZone[]
  zone_pair_margin: number
  /** rl_role raster code -> label (JSON keys are strings). */
  roles: Record<string, string>
  realized_bands: Record<string, string>
  fao_classes: { code: string; label: string }[]
  fao_breaks: number[]
  ssps: { key: string; label: string }[]
  windows: ManifestWindow[]
  gcms: string[]
  baseline: { start: number; end: number }
  municipal_delta: { ssp: string; window: string }
  /** ssp -> window -> segments with a shipped delta PMTiles (scanned, not assumed). */
  delta_layers: Record<string, Record<string, string[]>>
  delta_domain: [number, number]
  aoi: { area_km2: number; n_municipalities: number; municipalities_by_uf: Record<string, number> }
  grid_m: number
  /** pca_var_keep = variance share the zoning PCA retains (zoning.fit_pca default); n_pc_90 counts against it */
  stack: { total_bands: number; themes: Record<string, number>; n_zoning_bands: number; pca_var_keep: number }
  hero_bands: { theme: string; band: string; stacked: boolean }[]
  themes: Record<string, string>
  anchor_rules: Record<AnchorRule, string>
  membership_types: Record<string, string>
  bands: Record<string, string>
}

// --- thesis/Chapters CSVs copied by build_diagnostics ------------------------------
export interface Cmip6ShiftMeanRow { segment: string; ssp: string; window: string; delta_s: number }
export interface Cmip6ShiftShareRow {
  segment: string; ssp: string; window: string; present_share: number; future_share: number
}
export interface Cmip6DowngradeRow { segment: string; ssp: string; window: string; downgrade_share: number }
/** FAO class transition present -> future, outras culturas anuais, worst case. */
export interface Cmip6TransitionRow { present: string; future: string; share_pct: number; ssp: string; window: string }
export interface Cmip6ZoneShiftRow { ssp: string; window: string; segment: string; zone: number; delta_s: number }
export interface RealizedCompositionRow { band: string; share_pct: number }
export interface RealizedGapRow { band: string; segment: string; area_km2: number; share_pct: number }
export interface FactorDiscriminationRow {
  segment: string
  factor: string
  half: string
  role: string
  type: string
  points: string
  sigma_mu_available: number
  sigma_mu_future: number
  sigma_mu_horizon: number
  sigma_mu_realized: number
  mean_mu_available: number
  mean_mu_future: number
  frac_saturated: number
  frac_vetoed: number
}
export interface LambdaSweepRow { half: string; segment: string; factor: string; lambda: number; weight: number }
export interface LambdaAucRow { segment: string; half: string; lambda: number; n: number; presences: number; auc: number }
export interface FactorVarianceThemeRow {
  segment: string
  raw_climate: number
  raw_terrain_soil: number
  raw_other: number
  theme_climate: number
  theme_terrain_soil: number
  theme_other: number
}
