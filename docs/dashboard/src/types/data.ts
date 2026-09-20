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

// --- csv/municipal_ranking.csv (v1-safe: 7 suit_* + zone, no delta/underused) ----
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

// --- TODO(v2): one interface per remaining §5 manifest row, added when consumed --
// DatasetCatalogEntry      <- json/datasets_catalog.json   (config/datasets.yaml)
// BandPercentiles          <- json/band_percentiles.json
// StackComposition         <- json/stack_composition.json
// ValidationScorecardRow   <- json/validation_scorecard.json
