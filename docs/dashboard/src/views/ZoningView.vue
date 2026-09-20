<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref } from 'vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import ZoneCard from '../components/ZoneCard.vue'
import { useCsv } from '../composables/useCsv'
import { useJson } from '../composables/useJson'
import type {
  FactorVarianceRow,
  SegmentsConfig,
  ThemeRoughnessPointRow,
  ThemeRoughnessRow,
  ZoneProfileRow,
  ZoningKselectRow,
} from '../types/data'

const { data: segmentsCfg } = useJson<SegmentsConfig>('json/segments.json')
const segmentOrder = computed(() => (segmentsCfg.value ? Object.keys(segmentsCfg.value.segments) : []))
const labels = computed<Record<string, string>>(() =>
  segmentsCfg.value
    ? Object.fromEntries(Object.entries(segmentsCfg.value.segments).map(([k, v]) => [k, v.label]))
    : {},
)

const { data: profiles } = useCsv<ZoneProfileRow>('csv/zone_profiles.csv')
const zoneCount = computed(() => profiles.value?.length ?? 0)
const totalN = computed(() => (profiles.value ?? []).reduce((sum, p) => sum + p.n, 0))

const selectedZone = ref<number | null>(null)
const selectedProfile = computed(() =>
  profiles.value?.find((p) => p.zone === selectedZone.value) ?? null,
)

const { data: kselect } = useCsv<ZoningKselectRow>('csv/zoning_kselect.csv')
const kselectData = computed<PlotlyDatum[]>(() => {
  const rows = kselect.value ?? []
  return [
    { type: 'scatter', mode: 'lines+markers', name: 'silhouette', x: rows.map((r) => r.k), y: rows.map((r) => r.silhouette) },
    { type: 'scatter', mode: 'lines+markers', name: 'davies_bouldin', x: rows.map((r) => r.k), y: rows.map((r) => r.davies_bouldin), yaxis: 'y2' },
  ]
})

const { data: factorVariance } = useCsv<FactorVarianceRow>('csv/factor_variance.csv')
const selectedFvSegment = ref('soybean')
const factorVarianceData = computed<PlotlyDatum[]>(() => {
  const rows = (factorVariance.value ?? []).filter((r) => r.segment === selectedFvSegment.value)
  return [{ type: 'bar', x: rows.map((r) => r.factor), y: rows.map((r) => r.variance_share) }]
})

const { data: roughness } = useCsv<ThemeRoughnessRow>('csv/theme_roughness.csv')
const { data: roughnessPoints } = useCsv<ThemeRoughnessPointRow>('csv/theme_roughness_points.csv')
const roughnessRatio = computed(() => {
  const r4750 = (roughness.value ?? []).filter((r) => r.radius_m === 4750)
  const climate = r4750.find((r) => r.group === 'climate')
  const terrain = r4750.find((r) => r.group === 'terrain_soil')
  if (!climate || !terrain || climate.mean_std === 0) return null
  return terrain.mean_std / climate.mean_std
})
const hexbinData = computed<PlotlyDatum[]>(() => {
  const pts = roughnessPoints.value ?? []
  return [
    {
      type: 'histogram2d',
      x: pts.map((p) => p.longitude),
      y: pts.map((p) => p.latitude),
      z: pts.map((p) => p.rough_terrain_soil_r4750 - p.rough_climate_r4750),
      histfunc: 'avg',
      colorscale: 'RdYlGn',
    } as PlotlyDatum,
  ]
})
</script>

<template>
  <section>
    <h1>Agro-Environmental Zoning (K={{ zoneCount }})</h1>
    <p>
      Offline sklearn KMeans on a decorrelated PCA input, classified server-side by
      nearest-centroid band math (Part 10). Zones are labelled by
      <code>comparative_segment</code> — the argmax of each segment's z-normalized
      suitability, not raw dominance.
    </p>

    <MapPanel raster-path="zones_present.pmtiles">
      <template #legend>Zone (click a card below for its profile)</template>
    </MapPanel>

    <div class="zone-buttons">
      <button
        v-for="p in profiles"
        :key="p.zone"
        type="button"
        :class="['zone-btn', { active: p.zone === selectedZone }]"
        @click="selectedZone = p.zone"
      >
        Z{{ p.zone }}
      </button>
    </div>

    <ZoneCard
      v-if="selectedProfile"
      :profile="selectedProfile"
      :segments="segmentOrder"
      :labels="labels"
      :total-n="totalN"
    />
    <p v-else class="hint">Select a zone above to see its profile.</p>

    <h2>Why K={{ zoneCount }}? (k-selection diagnostics)</h2>
    <PlotlyChart
      :data="kselectData"
      :layout="{
        height: 280,
        xaxis: { title: { text: 'k' } },
        yaxis: { title: { text: 'silhouette' } },
        yaxis2: { title: { text: 'davies-bouldin' }, overlaying: 'y', side: 'right' },
      }"
    />

    <h2>Factor variance decomposition</h2>
    <select v-model="selectedFvSegment">
      <option v-for="s in segmentOrder" :key="s" :value="s">{{ labels[s] ?? s }}</option>
    </select>
    <PlotlyChart :data="factorVarianceData" :layout="{ height: 260 }" />

    <h2>Scale mismatch: climate vs. terrain+soil roughness</h2>
    <p v-if="roughnessRatio">
      At TerraClimate's own native scale (4,750 m), terrain+soil local variability is
      <strong>{{ roughnessRatio.toFixed(0) }}x</strong> climate's.
    </p>
    <PlotlyChart :data="hexbinData" :layout="{ height: 320 }" />
  </section>
</template>

<style scoped>
.zone-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-block: var(--space-3);
}

.zone-btn {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius);
  cursor: pointer;
  font: inherit;
}

.zone-btn.active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: white;
}

.hint {
  color: var(--color-muted);
}
</style>
