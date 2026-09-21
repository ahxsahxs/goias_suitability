<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import SegmentSelector from '../components/SegmentSelector.vue'
import { useCsv } from '../composables/useCsv'
import { useJson } from '../composables/useJson'
import { roleLegend, underusedLegend } from '../legends'
import type { MunicipalRankingRow, SegmentsConfig, ValidationScorecard } from '../types/data'

// Only these 4 crops have an underused_<crop> band — realized_vs_potential's
// ROLE_CODES cover soybean/sugarcane/other_crops/pisciculture only; cattle,
// conservation, and solar have no realized-role counterpart by construction.
const UNDERUSED_CROPS = ['soybean', 'sugarcane', 'other_crops', 'pisciculture']

const route = useRoute()
const router = useRouter()

const { data: segmentsCfg } = useJson<SegmentsConfig>('json/segments.json')
const labels = computed<Record<string, string>>(() =>
  segmentsCfg.value
    ? Object.fromEntries(Object.entries(segmentsCfg.value.segments).map(([k, v]) => [k, v.label]))
    : {},
)

const selectedCrop = ref((route.params.crop as string) || 'soybean')
watch(selectedCrop, (crop) => router.replace({ name: 'realized-use', params: { crop } }))
watch(
  () => route.params.crop,
  (crop) => {
    if (typeof crop === 'string' && crop) selectedCrop.value = crop
  },
)

const { data: scorecard } = useJson<ValidationScorecard>('json/validation_scorecard.json')
const { data: municipal } = useCsv<MunicipalRankingRow>('csv/municipal_ranking.csv')

const underusedBarData = computed<PlotlyDatum[]>(() => {
  const pct = scorecard.value?.underuse_pct ?? {}
  return [
    {
      type: 'bar',
      x: UNDERUSED_CROPS.map((c) => labels.value[c] ?? c),
      y: UNDERUSED_CROPS.map((c) => pct[c] ?? 0),
    },
  ]
})

const meanUnderused = computed(() => {
  const rows = municipal.value ?? []
  if (rows.length === 0) return null
  const key = `underused_${selectedCrop.value}` as keyof MunicipalRankingRow
  const vals = rows.map((r) => Number(r[key] ?? 0))
  return (100 * vals.reduce((a, b) => a + b, 0)) / vals.length
})

const roleMapLegend = computed(() => roleLegend())
const underusedMapLegend = computed(() => underusedLegend(labels.value[selectedCrop.value] ?? selectedCrop.value))
</script>

<template>
  <section>
    <h1>Uso Realizado &amp; Lacuna de Potencial</h1>
    <p>
      Onde o uso realizado da terra (MapBiomas) diverge do potencial modelado?
      &ldquo;Subutilizado&rdquo; = viável ou melhor (FAO S1/S2) para uma cultura, mas
      não cultivado atualmente com ela &mdash; majoritariamente pastagem existente,
      não vegetação nativa (Partes 12-13, QP2).
    </p>

    <SegmentSelector v-model="selectedCrop" :segments="UNDERUSED_CROPS" :labels="labels" />

    <div class="map-row">
      <MapPanel raster-path="rl_role.pmtiles">
        <template #legend><MapLegend :spec="roleMapLegend" /></template>
      </MapPanel>
      <MapPanel :raster-path="`underused_${selectedCrop}.pmtiles`">
        <template #legend>
          <MapLegend :spec="underusedMapLegend" />
          <p v-if="meanUnderused !== null" class="underused-mean">
            {{ meanUnderused.toFixed(1) }}% dos municípios, em média
          </p>
        </template>
      </MapPanel>
    </div>

    <h2>Parcela subutilizada por cultura</h2>
    <PlotlyChart
      :data="underusedBarData"
      :layout="{ height: 260, yaxis: { title: { text: '% do território' } } }"
    />
  </section>
</template>

<style scoped>
.underused-mean {
  margin-top: var(--space-1);
  color: var(--color-muted);
  font-size: 0.8rem;
}

.map-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
  margin-block: var(--space-3);
}

@media (max-width: 720px) {
  .map-row {
    grid-template-columns: 1fr;
  }
}
</style>
