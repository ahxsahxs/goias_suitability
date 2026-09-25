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
}
export type MembershipType = 'increasing' | 'decreasing' | 'range'
export interface FactorConfig {
  weight: number
  type: MembershipType
  points: number[]
  ref: string
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
  segments: Record<string, SegmentDef>
}

// --- config/ahp_matrices.yaml -> json/ahp_matrices.json -------------------------
export interface AhpSegment {
  factors: string[]
  matrix: number[][]
  consistency_ratio: number
  priority_vector: number[]
  config_weights: number[]
}
export interface AhpMatrices {
  _note: string
  segments: Record<string, AhpSegment>
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
  n: number
  dominant_segment: string
  comparative_segment: string
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

// --- csv/zoning_kselect.csv ------------------------------------------------------
export interface ZoningKselectRow {
  k: number
  inertia: number
  silhouette: number
  davies_bouldin: number
  gap: number
  s_k: number
  ari: number
  ari_std: number
}

// --- csv/factor_variance.csv -----------------------------------------------------
export interface FactorVarianceRow {
  segment: string
  factor: string
  weight: number
  variance_share: number
}

// --- csv/theme_roughness.csv / theme_roughness_points.csv ------------------------
export interface ThemeRoughnessRow {
  group: string
  radius_m: number
  mean_std: number
  median_std: number
  n: number
}
export interface ThemeRoughnessPointRow {
  longitude: number
  latitude: number
  rough_climate_r4750: number
  rough_terrain_soil_r4750: number
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

// --- json/datasets_catalog.json (config/datasets.yaml, hand-curated) -------------
export interface DatasetCatalogEntry {
  theme: string
  source: string
  id: string
  native_res: string
  period: string
}

// --- json/stack_composition.json (static, from STACK_THEMES) ---------------------
export interface StackComposition {
  themes: Record<string, number>
  total_bands: number
  excluded: string[]
  note: string
}

// --- json/pca_compare.json (build_pca_compare: 34-band z-stack vs 15 ZONING_BANDS) --
export interface PcaVariant {
  bands: string[]
  /** Band-name prefix per band: clim/terr/soil/water/phen/access. */
  themes: string[]
  /** 1/√(bands-in-theme) for the 15-band variant; all 1 for the 34-band one. */
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
  pc34: [number, number, number][]
  pc15: [number, number, number][]
  zone: number[]
  lon: number[]
  lat: number[]
  terr_elev: number[]
  clim_aridity: number[]
  soil_clay: number[]
}

export interface PcaCompare {
  variants: { '34': PcaVariant; '15': PcaVariant }
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

// --- json/validation_scorecard.json (hand-transcribed from the thesis tables) ----
export interface PresenceAucBoyceRow {
  auc: number
  boyce: number
}
export interface WithinCropGradientRow {
  rho: number
  n: number
}
export interface ZoneAnova {
  f: number
  p_approx: number
  zone_mean_range: [number, number]
}
export interface RfKappa {
  soybean: number
  n: number
  knowledge_area_pct: number
  rf_area_pct: number
  note: string
}
export interface ValidationScorecard {
  presence_auc_boyce: Record<string, PresenceAucBoyceRow>
  spearman_npp: Record<string, number>
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
  mean_delta_other_crops_ssp585_2051_2070: number | null
}
