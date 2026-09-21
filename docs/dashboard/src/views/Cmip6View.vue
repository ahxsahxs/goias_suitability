<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import ScenarioSelector from '../components/ScenarioSelector.vue'
import type { Scenario } from '../components/ScenarioSelector.vue'
import SegmentSelector from '../components/SegmentSelector.vue'
import { useJson } from '../composables/useJson'
import { deltaLegend } from '../legends'
import type { SegmentsConfig } from '../types/data'

// Delta PMTiles cover 5 segments (docs/dashboard_ux_plan.md §5's manifest) — not
// all 7, since the manifest curates to the segments the thesis discusses for CMIP6.
const DELTA_SEGMENTS = ['soybean', 'sugarcane', 'other_crops', 'conservation', 'solar']

const route = useRoute()
const router = useRouter()

const { data: segmentsCfg } = useJson<SegmentsConfig>('json/segments.json')
const labels = computed<Record<string, string>>(() =>
  segmentsCfg.value
    ? Object.fromEntries(Object.entries(segmentsCfg.value.segments).map(([k, v]) => [k, v.label]))
    : {},
)

const scenario = ref<Scenario>({
  ssp: (route.params.ssp as string) || 'ssp585',
  window: (route.params.window as string) || '2051_2070',
})
const selectedSegment = ref((route.params.segment as string) || 'other_crops')

watch(
  [scenario, selectedSegment],
  ([s, seg]) => router.replace({ name: 'cmip6', params: { ssp: s.ssp, window: s.window, segment: seg } }),
  { deep: true },
)
watch(
  () => [route.params.ssp, route.params.window, route.params.segment],
  ([ssp, window, seg]) => {
    if (typeof ssp === 'string' && ssp) scenario.value.ssp = ssp
    if (typeof window === 'string' && window) scenario.value.window = window
    if (typeof seg === 'string' && seg) selectedSegment.value = seg
  },
)

const deltaPath = computed(
  () => `delta_${scenario.value.ssp}_${scenario.value.window}_${selectedSegment.value}.pmtiles`,
)

const deltaMapLegend = computed(() =>
  deltaLegend(
    labels.value[selectedSegment.value] ?? selectedSegment.value,
    scenario.value.ssp,
    scenario.value.window.replace('_', '-'),
  ),
)
</script>

<template>
  <section>
    <h1>Mudança Climática — CMIP6</h1>
    <p>
      Mudança de viabilidade pelo método dos fatores de mudança (Parte 11), conjunto de
      5 GCMs, dois cenários SSP x duas janelas de 20 anos. Nenhum segmento permanece
      estruturalmente invariante ao clima — todos os 7 segmentos se movem sob pelo
      menos uma alavanca climática.
    </p>

    <ScenarioSelector v-model="scenario" />
    <SegmentSelector v-model="selectedSegment" :segments="DELTA_SEGMENTS" :labels="labels" />

    <div class="map-row">
      <MapPanel :raster-path="deltaPath">
        <template #legend><MapLegend :spec="deltaMapLegend" /></template>
      </MapPanel>
    </div>
  </section>
</template>

<style scoped>
.map-row {
  margin-block: var(--space-3);
}
</style>
