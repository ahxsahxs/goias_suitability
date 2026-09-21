<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import ScenarioSelector from '../components/ScenarioSelector.vue'
import type { Scenario } from '../components/ScenarioSelector.vue'
import SegmentSelector from '../components/SegmentSelector.vue'
import { useJson } from '../composables/useJson'
import { agreementLegend, deltaLegend } from '../legends'
import type { SegmentsConfig } from '../types/data'

// Delta PMTiles cover 5 segments (docs/dashboard_ux_plan.md §5's manifest) — not
// all 7, since the manifest curates to the segments the thesis discusses for CMIP6.
const DELTA_SEGMENTS = ['soybean', 'sugarcane', 'other_crops', 'conservation', 'solar']

// Only these 2 (ssp, window) combos ship an agreement layer — the territory-mean
// agreement is ~0.999 and near-uniform everywhere, so the full ~20-combo matrix
// would mostly duplicate near-identical maps (see thesis 03_methodology.tex's
// concordância paragraph). The agreement panel is deliberately NOT driven by
// SegmentSelector — it's always other_crops, the most climate-exposed segment.
const AGREEMENT_COMBOS = new Set(['ssp585:2051_2070', 'ssp245:2031_2050'])

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
const agreementKey = computed(() => `${scenario.value.ssp}:${scenario.value.window}`)
const agreementAvailable = computed(() => AGREEMENT_COMBOS.has(agreementKey.value))
const agreementPath = computed(() =>
  agreementAvailable.value
    ? `agreement_${scenario.value.ssp}_${scenario.value.window}_other_crops.pmtiles`
    : null,
)

const deltaMapLegend = computed(() =>
  deltaLegend(
    labels.value[selectedSegment.value] ?? selectedSegment.value,
    scenario.value.ssp,
    scenario.value.window.replace('_', '-'),
  ),
)
const agreementMapLegend = computed(() => agreementLegend())
</script>

<template>
  <section>
    <h1>Mudança Climática — CMIP6</h1>
    <p>
      Mudança de aptidão pelo método dos fatores de mudança (Parte 11), conjunto de
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
      <MapPanel v-if="agreementPath" :raster-path="agreementPath">
        <template #legend><MapLegend :spec="agreementMapLegend" /></template>
      </MapPanel>
      <div v-else class="no-agreement">
        <p>
          Nenhuma camada de concordância disponível para este cenário/janela —
          apenas SSP5-8.5 2051-2070 e SSP2-4.5 2031-2050 estão incluídas (ver nota
          abaixo).
        </p>
      </div>
    </div>

    <p class="note">
      Apenas 2 das 16 combinações possíveis de cenário/janela/segmento de
      concordância são disponibilizadas, ambas para <strong>outras culturas
      anuais</strong> (o segmento mais exposto ao clima): a superfície de
      concordância do conjunto é ~0,999 na média territorial e quase uniforme em
      toda parte, em todos os cenários testados — então mesmo o caso mais exposto
      mostra quase nenhum contraste espacial. O painel de concordância não segue o
      seletor de segmento acima; é uma ilustração fixa e representativa desse
      achado, não uma camada genérica por segmento.
    </p>
  </section>
</template>

<style scoped>
.map-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
  margin-block: var(--space-3);
}

.no-agreement {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius);
  padding: var(--space-4);
  color: var(--color-muted);
  text-align: center;
}

.note {
  color: var(--color-muted);
  font-size: 0.875rem;
}

@media (max-width: 720px) {
  .map-row {
    grid-template-columns: 1fr;
  }
}
</style>
