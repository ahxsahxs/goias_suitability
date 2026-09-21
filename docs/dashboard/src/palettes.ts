/**
 * Client-side mirror of tools/palettes.py — the dashboard's PMTiles rasters are
 * pre-colorized server-side (build_dashboard_assets.py), so there is no palette
 * metadata to read from a data file at runtime. These constants must stay
 * byte-for-byte in sync with tools/palettes.py so the map legends (MapLegend.vue)
 * describe the colors actually baked into each raster.
 */

export const PAL_SUIT = ['#d7191c', '#fdae61', '#ffffbf', '#a6d96a', '#1a9641'] // 0..1 red->green
export const PAL_FAO = ['#d7191c', '#fdae61', '#a6d96a', '#1a9641'] // N, S3, S2, S1
export const PAL_ROLE = ['#eeeeee', '#ffd400', '#7b3294', '#d95f0e', '#2c7fb8', '#addd8e', '#006837']
export const PAL_DIV = ['#b2182b', '#f7f7f7', '#2166ac'] // diverging deltaS
export const PAL_AGREEMENT = ['#ffffcc', '#a1dab4', '#41b6c4', '#225ea8'] // sequential, GCM sign-agreement
export const PAL_UNDERUSED = ['#f7f7f7', '#d7301f'] // binary, potential-vs-realized gap

export const FAO_ORDER = ['N', 'S3', 'S2', 'S1'] as const

/** rl_role band codes (src/external.py ROLE_CODES), 0 = other/none, in PAL_ROLE order. */
export const ROLE_LABELS_PT = [
  'Outro / nenhum',
  'Soja',
  'Cana-de-açúcar',
  'Outras culturas anuais',
  'Piscicultura',
  'Pastagem',
  'Vegetação nativa',
]

const TAB10 = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]
const TAB20 = [
  '#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c', '#98df8a', '#d62728', '#ff9896',
  '#9467bd', '#c5b0d5', '#8c564b', '#c49c94', '#e377c2', '#f7b6d2', '#7f7f7f', '#c7c7c7',
  '#bcbd22', '#dbdb8d', '#17becf', '#9edae5',
]

/**
 * Mirrors tools/palettes.py's zone_palette(n): samples matplotlib's discrete
 * tab10/tab20 ListedColormap the same way (floor(i * N / (n-1)), clipped to N-1),
 * so a given zone count always maps to the exact same colors as the server-side
 * `zones_present.pmtiles` raster.
 */
export function zonePalette(n: number): string[] {
  const table = n <= 10 ? TAB10 : TAB20
  const size = table.length
  if (n <= 1) return [table[0]!]
  return Array.from({ length: n }, (_, i) => {
    const idx = Math.min(size - 1, Math.floor((i * size) / (n - 1)))
    return table[idx]!
  })
}
