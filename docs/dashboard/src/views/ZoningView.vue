<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref } from 'vue'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import ZoneCard from '../components/ZoneCard.vue'
import { useCsv } from '../composables/useCsv'
import { useJson } from '../composables/useJson'
import { zoneLegend } from '../legends'
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

// Keyed by the 0-based palette slot (= the zones_present raster value), while
// p.zone is the 1-based reported name — hence the -1. See zoneLegend().
const zoneLabelsByIndex = computed(() =>
  Object.fromEntries(
    (profiles.value ?? []).map((p) => [p.zone - 1, labels.value[p.comparative_segment] ?? p.comparative_segment]),
  ),
)
const mapLegend = computed(() => zoneLegend(zoneCount.value, zoneLabelsByIndex.value))

const selectedZone = ref<number | null>(null)
const selectedProfile = computed(() =>
  profiles.value?.find((p) => p.zone === selectedZone.value) ?? null,
)

const { data: kselect } = useCsv<ZoningKselectRow>('csv/zoning_kselect.csv')
const kselectData = computed<PlotlyDatum[]>(() => {
  const rows = kselect.value ?? []
  return [
    { type: 'scatter', mode: 'lines+markers', name: 'silhueta', x: rows.map((r) => r.k), y: rows.map((r) => r.silhouette) },
    { type: 'scatter', mode: 'lines+markers', name: 'davies_bouldin', x: rows.map((r) => r.k), y: rows.map((r) => r.davies_bouldin), yaxis: 'y2' },
  ]
})

// Mark the k that was actually exported. Neither curve peaks at the selected k
// (the territory is only weakly clustered at every k — the choice rests on
// stability, not on a silhouette maximum), so without this line the chart gives
// the reader no indication of which k was adopted. Mirrors fig_4_10 in the thesis.
const kselectLayout = computed(() => ({
  height: 280,
  xaxis: { title: { text: 'k' } },
  yaxis: { title: { text: 'silhueta' } },
  yaxis2: { title: { text: 'davies-bouldin' }, overlaying: 'y' as const, side: 'right' as const },
  shapes: zoneCount.value
    ? [{
        type: 'line' as const,
        x0: zoneCount.value, x1: zoneCount.value,
        yref: 'paper' as const, y0: 0, y1: 1,
        line: { color: '#d7191c', width: 1, dash: 'dash' as const },
      }]
    : [],
  annotations: zoneCount.value
    ? [{
        x: zoneCount.value, yref: 'paper' as const, y: 1,
        text: `k = ${zoneCount.value}`, showarrow: false,
        yanchor: 'bottom' as const, font: { color: '#d7191c', size: 11 },
      }]
    : [],
}))

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
    <h1>Zoneamento Agroambiental (K={{ zoneCount }})</h1>
    <p>
      KMeans do sklearn offline sobre uma entrada PCA descorrelacionada, classificado
      no servidor por matemática de banda do centróide mais próximo (Parte 10). As
      zonas são rotuladas por <code>comparative_segment</code> — o argmax da viabilidade
      z-normalizada de cada segmento, não a dominância bruta.
    </p>

    <MapPanel raster-path="zones_present.pmtiles">
      <template #legend><MapLegend :spec="mapLegend" /></template>
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
    <p v-else class="hint">Selecione uma zona acima para ver seu perfil.</p>

    <h2>Por que K={{ zoneCount }}? (diagnóstico de seleção de k)</h2>
    <PlotlyChart
      :data="kselectData"
      :layout="kselectLayout"
    />

    <h2>Decomposição da variância dos fatores</h2>
    <select v-model="selectedFvSegment">
      <option v-for="s in segmentOrder" :key="s" :value="s">{{ labels[s] ?? s }}</option>
    </select>
    <PlotlyChart :data="factorVarianceData" :layout="{ height: 260 }" />

    <h2>Descompasso de escala: rugosidade clima vs. relevo+solo</h2>
    <p v-if="roughnessRatio">
      Mesmo na escala nativa do TerraClimate (4.750 m), a variabilidade local de
      relevo+solo é <strong>{{ roughnessRatio.toFixed(0) }}x</strong> a do clima.
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
