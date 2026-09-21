/** What MapLegend.vue can render, fed by src/legends.ts's builder functions. */

export interface GradientLegend {
  kind: 'gradient'
  title: string
  /** Ordered [value, color] stops — same shape as MapPanel's ChoroplethLayer.stops. */
  stops: [number, string][]
  /** Formats a stop's numeric value for display; defaults to 2 decimals. */
  format?: (v: number) => string
  /** Optional caption shown under the bar (e.g. scenario/window context). */
  caption?: string
}

export interface CategoricalLegend {
  kind: 'categorical'
  title: string
  items: { label: string; color: string }[]
  caption?: string
}

export type LegendSpec = GradientLegend | CategoricalLegend
