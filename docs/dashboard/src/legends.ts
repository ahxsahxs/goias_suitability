/** Builds LegendSpec objects for every map layer kind in the dashboard, keeping
 * the legend colors in lockstep with the palettes actually baked into each
 * PMTiles raster (see src/palettes.ts) or passed to a MapLibre choropleth. */
import { FAO_ORDER, PAL_AGREEMENT, PAL_DIV, PAL_FAO, PAL_ROLE, PAL_SUIT, PAL_UNDERUSED, ROLE_LABELS_PT, zonePalette } from './palettes'
import type { CategoricalLegend, GradientLegend } from './types/legend'

const FAO_LABELS_PT: Record<(typeof FAO_ORDER)[number], string> = {
  N: 'N — inapto',
  S3: 'S3 — aptidão marginal',
  S2: 'S2 — moderadamente apto',
  S1: 'S1 — altamente apto',
}

export function suitabilityLegend(segmentLabel: string): GradientLegend {
  const n = PAL_SUIT.length
  return {
    kind: 'gradient',
    title: `Aptidão — ${segmentLabel}`,
    stops: PAL_SUIT.map((color, i) => [i / (n - 1), color]),
    format: (v) => v.toFixed(2),
    caption: '0 = inapto · 1 = altamente apto',
  }
}

export function faoClassLegend(): CategoricalLegend {
  return {
    kind: 'categorical',
    title: 'Classe FAO',
    items: FAO_ORDER.map((code, i) => ({ label: FAO_LABELS_PT[code], color: PAL_FAO[i]! })),
  }
}

/** `zoneLabels[i]` (optional) is the comparative-segment label for zone i, shown
 * alongside "Zona i" when the caller already has that mapping (e.g. from
 * zone_profiles.csv) — falls back to a bare zone number otherwise. */
export function zoneLegend(n: number, zoneLabels?: Record<number, string>): CategoricalLegend {
  const colors = zonePalette(n)
  return {
    kind: 'categorical',
    title: 'Zona agroambiental',
    items: Array.from({ length: n }, (_, i) => ({
      label: zoneLabels?.[i] ? `Zona ${i} — ${zoneLabels[i]}` : `Zona ${i}`,
      color: colors[i]!,
    })),
  }
}

export function deltaLegend(segmentLabel: string, ssp: string, windowLabel: string): GradientLegend {
  return {
    kind: 'gradient',
    title: `ΔAptidão — ${segmentLabel}`,
    stops: [
      [-0.15, PAL_DIV[0]!],
      [0, PAL_DIV[1]!],
      [0.15, PAL_DIV[2]!],
    ],
    format: (v) => (v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2)),
    caption: `${ssp.toUpperCase()}, ${windowLabel} — vermelho: perda de aptidão · azul: ganho`,
  }
}

export function agreementLegend(): GradientLegend {
  const n = PAL_AGREEMENT.length
  return {
    kind: 'gradient',
    title: 'Concordância entre modelos (GCMs)',
    stops: PAL_AGREEMENT.map((color, i) => [i / (n - 1), color]),
    format: (v) => (v <= 0 ? 'menor' : v >= 1 ? 'maior' : ''),
    caption: 'Escala relativa (do percentil 2 dos dados até 1,0) — amarelo: menor concordância · azul: maior concordância',
  }
}

export function roleLegend(): CategoricalLegend {
  return {
    kind: 'categorical',
    title: 'Uso realizado da terra (MapBiomas)',
    items: ROLE_LABELS_PT.map((label, i) => ({ label, color: PAL_ROLE[i]! })),
  }
}

export function underusedLegend(cropLabel: string): GradientLegend {
  return {
    kind: 'gradient',
    title: `Subutilização — ${cropLabel}`,
    stops: [
      [0, PAL_UNDERUSED[0]!],
      [1, PAL_UNDERUSED[1]!],
    ],
    format: (v) => (v >= 1 ? 'subutilizado' : 'não subutilizado'),
  }
}

export function continuousBandLegend(bandLabel: string, vmin: number, vmax: number): GradientLegend {
  const n = PAL_SUIT.length
  const fmt = (v: number) => (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(2))
  return {
    kind: 'gradient',
    title: bandLabel,
    stops: PAL_SUIT.map((color, i) => [vmin + ((vmax - vmin) * i) / (n - 1), color]),
    format: fmt,
  }
}

/** Generic wrapper for a MapPanel choropleth's own [value, color] stops (e.g. the
 * Municipal Explorer's continuous fields), so the legend always matches exactly
 * what was actually painted, not a re-derived approximation. */
export function gradientFromStops(title: string, stops: [number, string][], format?: (v: number) => string): GradientLegend {
  return { kind: 'gradient', title, stops, format }
}
