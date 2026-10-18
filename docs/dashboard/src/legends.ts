/** Builds LegendSpec objects for every map layer kind in the dashboard, keeping
 * the legend colors in lockstep with the palettes actually baked into each
 * PMTiles raster (see src/palettes.ts) or passed to a MapLibre choropleth.
 *
 * Labels and domains are ARGUMENTS (from manifest.json via useManifest), never
 * literals here: the FAO class names, the ΔS window and the realized-use roles all
 * have a single source in config/ or in the pipeline. */
import { fmtNum, fmtSigned } from './format'
import { PAL_DIV, PAL_FAO, PAL_ROLE, PAL_SUIT, PAL_UNDERUSED, zonePalette } from './palettes'
import type { CategoricalLegend, GradientLegend } from './types/legend'

export function suitabilityLegend(segmentLabel: string): GradientLegend {
  const n = PAL_SUIT.length
  return {
    kind: 'gradient',
    title: `Aptidão — ${segmentLabel}`,
    stops: PAL_SUIT.map((color, i) => [i / (n - 1), color]),
    format: (v) => fmtNum(v, 2),
    caption: '0 = inapto · 1 = aptidão máxima',
  }
}

/** `classes` in raster-code order (N, S3, S2, S1), as manifest.fao_classes. */
export function faoClassLegend(classes: { code: string; label: string }[], breaks: number[]): CategoricalLegend {
  // S >= breaks[i-1] and < breaks[i]: N < b0 <= S3 < b1 <= S2 < b2 <= S1
  const range = (i: number): string => {
    const lo = i === 0 ? null : breaks[i - 1]
    const hi = i < breaks.length ? breaks[i] : null
    if (lo === null || lo === undefined) return `S < ${fmtNum(hi, 2)}`
    if (hi === null || hi === undefined) return `S ≥ ${fmtNum(lo, 2)}`
    return `${fmtNum(lo, 2)} ≤ S < ${fmtNum(hi, 2)}`
  }
  return {
    kind: 'categorical',
    title: 'Classe de aptidão (FAO)',
    items: classes.map((c, i) => ({ label: `${c.code} — ${c.label} (${range(i)})`, color: PAL_FAO[i]! })),
  }
}

/** `zoneLabels` is keyed by the 1-BASED zone id (as zone_profiles.csv, the thesis and
 * the manifest). The zones_present raster stores 0..n-1 and palette slot `i` paints
 * raster value `i` — i.e. zone `i + 1`. That offset lives here and nowhere else. */
export function zoneLegend(n: number, zoneLabels?: Record<number, string>): CategoricalLegend {
  const colors = zonePalette(n)
  return {
    kind: 'categorical',
    title: 'Zona agroambiental',
    items: Array.from({ length: n }, (_, i) => ({
      label: zoneLabels?.[i + 1] ? `Zona ${i + 1} — ${zoneLabels[i + 1]}` : `Zona ${i + 1}`,
      color: colors[i]!,
    })),
  }
}

export function deltaLegend(segmentLabel: string, scenario: string, domain: [number, number]): GradientLegend {
  return {
    kind: 'gradient',
    title: `ΔS — ${segmentLabel}`,
    stops: [
      [domain[0], PAL_DIV[0]!],
      [0, PAL_DIV[1]!],
      [domain[1], PAL_DIV[2]!],
    ],
    format: (v) => fmtSigned(v, 2),
    caption: `${scenario} · vermelho: perda de aptidão; azul: ganho. Valores fora da escala saturam a cor.`,
  }
}

/** `labels[code]` for rl_role codes 0..n-1, in PAL_ROLE order. */
export function roleLegend(labels: string[]): CategoricalLegend {
  return {
    kind: 'categorical',
    title: 'Uso atual da terra (MapBiomas, classe majoritária)',
    items: labels.map((label, i) => ({ label, color: PAL_ROLE[i]! })),
  }
}

export function underusedLegend(cropLabel: string): CategoricalLegend {
  return {
    kind: 'categorical',
    title: `Subutilização — ${cropLabel}`,
    items: [
      { label: 'Apta (S2+) e sem o uso', color: PAL_UNDERUSED[1]! },
      { label: 'Demais células avaliadas', color: PAL_UNDERUSED[0]! },
    ],
  }
}

export function continuousBandLegend(bandLabel: string, vmin: number, vmax: number): GradientLegend {
  const n = PAL_SUIT.length
  const fmt = (v: number) => fmtNum(v, Math.abs(v) >= 10 ? 0 : 2)
  return {
    kind: 'gradient',
    title: bandLabel,
    stops: PAL_SUIT.map((color, i) => [vmin + ((vmax - vmin) * i) / (n - 1), color]),
    format: fmt,
    caption: 'escala entre os percentis 5 e 95 do território',
  }
}

/** Generic wrapper for a MapPanel choropleth's own [value, color] stops (e.g. the
 * Municipal Explorer's continuous fields), so the legend always matches exactly
 * what was actually painted, not a re-derived approximation. */
export function gradientFromStops(title: string, stops: [number, string][], format?: (v: number) => string): GradientLegend {
  return { kind: 'gradient', title, stops, format }
}
