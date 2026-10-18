import { computed } from 'vue'
import { fmtRange } from '../format'
import type { Manifest, ManifestZone } from '../types/data'
import { useJson } from './useJson'

/**
 * json/manifest.json + the label helpers every view needs. useJson caches by URL, so
 * every component calling this shares one fetch.
 *
 * The rule this enforces: a view never spells a segment, zone, scenario, band count or
 * domain itself. Words come from config/dashboard.yaml (checked against the thesis at
 * build time), numbers from the pipeline. Unknown keys fall back to the raw key so a
 * missing label is visible rather than silently wrong.
 */
export function useManifest() {
  const { data: manifest, error, loading } = useJson<Manifest>('json/manifest.json')

  const segmentKeys = computed(() => manifest.value?.segments.map((s) => s.key) ?? [])
  const segmentLabels = computed<Record<string, string>>(() =>
    Object.fromEntries((manifest.value?.segments ?? []).map((s) => [s.key, s.label])),
  )
  const segmentLabel = (key: string): string => segmentLabels.value[key] ?? key
  const segmentShort = (key: string): string =>
    manifest.value?.segments.find((s) => s.key === key)?.short ?? key

  const zones = computed<ManifestZone[]>(() => manifest.value?.zones ?? [])
  const zone = (z: number): ManifestZone | undefined => zones.value.find((x) => x.zone === z)
  /** "Planalto de cultivo alto e argiloso" */
  const zoneName = (z: number): string => zone(z)?.name ?? ''
  /** Comparative vocation; both segments when the margin is below zone_pair_margin. */
  const zoneVocation = (z: number): string => {
    const m = zone(z)
    if (!m) return ''
    return m.paired
      ? `${segmentShort(m.comparative_segment)} / ${segmentShort(m.comparative_segment_2)}`
      : segmentShort(m.comparative_segment)
  }
  /** "Zona 1 — Planalto de cultivo alto e argiloso" */
  const zoneTitle = (z: number): string => (zoneName(z) ? `Zona ${z} — ${zoneName(z)}` : `Zona ${z}`)

  const sspLabel = (key: string): string => manifest.value?.ssps.find((s) => s.key === key)?.label ?? key
  const windowLabel = (key: string): string => {
    const w = manifest.value?.windows.find((x) => x.key === key)
    return w ? fmtRange(w.start, w.end) : key
  }
  /** "SSP5-8.5, 2051–2070" */
  const scenarioLabel = (ssp: string, window: string): string => `${sspLabel(ssp)}, ${windowLabel(window)}`

  const bandLabel = (band: string): string => manifest.value?.bands[band] ?? band
  const themeLabel = (theme: string): string => manifest.value?.themes[theme] ?? theme
  const roleLabels = computed<string[]>(() => {
    const roles = manifest.value?.roles ?? {}
    return Object.keys(roles)
      .map(Number)
      .sort((a, b) => a - b)
      .map((k) => roles[String(k)]!)
  })

  return {
    manifest,
    error,
    loading,
    segmentKeys,
    segmentLabels,
    segmentLabel,
    segmentShort,
    zones,
    zone,
    zoneName,
    zoneVocation,
    zoneTitle,
    sspLabel,
    windowLabel,
    scenarioLabel,
    bandLabel,
    themeLabel,
    roleLabels,
  }
}
