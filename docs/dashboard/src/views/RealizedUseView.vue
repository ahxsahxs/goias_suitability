<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DataTable from '../components/DataTable.vue'
import type { DataTableColumn } from '../components/DataTable.vue'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import SegmentSelector from '../components/SegmentSelector.vue'
import { useCsv } from '../composables/useCsv'
import { useManifest } from '../composables/useManifest'
import { fmtKm2, fmtNum, fmtPct, fmtShare } from '../format'
import { roleLegend, underusedLegend } from '../legends'
import type { MunicipalRankingRow, RealizedCompositionRow, RealizedGapRow } from '../types/data'

const route = useRoute()
const router = useRouter()
const { manifest, segmentKeys, segmentLabels, segmentLabel, roleLabels } = useManifest()

const { data: composition } = useCsv<RealizedCompositionRow>('csv/realized_composition.csv')
const { data: gap } = useCsv<RealizedGapRow>('csv/realized_gap.csv')
const { data: municipal } = useCsv<MunicipalRankingRow>('csv/municipal_ranking.csv')

// Segments with an underuse layer = the rows of realized_gap.csv (one per
// underused_<crop> band of realized_vs_potential), in thesis segment order.
const gapSegments = computed(() => {
  const have = new Set((gap.value ?? []).map((r) => r.segment))
  return segmentKeys.value.filter((s) => have.has(s))
})

const selectedCrop = ref((route.params.crop as string) || 'soybean')
watch(selectedCrop, (crop) => router.replace({ name: 'realized-use', params: { crop } }))
watch(
  () => route.params.crop,
  (crop) => {
    if (typeof crop === 'string' && crop) selectedCrop.value = crop
  },
)

// --- tab:realized-composition ------------------------------------------------------
const compositionRows = computed(() => {
  const labels = manifest.value?.realized_bands ?? {}
  const rows = (composition.value ?? []).map((r) => ({ label: labels[r.band] ?? r.band, share: r.share_pct }))
  const rest = 100 - rows.reduce((a, r) => a + r.share, 0)
  return [...rows.sort((a, b) => b.share - a.share), ...(rest > 0.05 ? [{ label: 'Outras classes', share: rest }] : [])]
})
const compositionData = computed<PlotlyDatum[]>(() => {
  const rows = [...compositionRows.value].reverse()
  return [{
    type: 'bar',
    orientation: 'h',
    x: rows.map((r) => r.share),
    y: rows.map((r) => r.label),
    text: rows.map((r) => (r.share < 0.1 ? '< 0,1%' : fmtPct(r.share))),
    textposition: 'outside',
    cliponaxis: false,
    hoverinfo: 'y+text',
  }]
})

// --- tab:pot-real-gap ----------------------------------------------------------------
const gapRows = computed(() => [...(gap.value ?? [])].sort((a, b) => b.area_km2 - a.area_km2))
const gapColumns: DataTableColumn<RealizedGapRow>[] = [
  { key: 'segment', label: 'Segmento', format: (r) => segmentLabel(r.segment) },
  { key: 'area_km2', label: 'Terra apta e sem o uso', format: (r) => fmtKm2(r.area_km2) },
  { key: 'share_pct', label: 'Parcela do território', format: (r) => fmtPct(r.share_pct) },
]

const meanUnderused = computed(() => {
  const rows = municipal.value ?? []
  if (rows.length === 0) return null
  const key = `underused_${selectedCrop.value}` as keyof MunicipalRankingRow
  const vals = rows.map((r) => Number(r[key] ?? 0))
  return vals.reduce((a, b) => a + b, 0) / vals.length
})

const roleMapLegend = computed(() => roleLegend(roleLabels.value))
const underusedMapLegend = computed(() => underusedLegend(segmentLabel(selectedCrop.value)))
</script>

<template>
  <section>
    <h1>Uso atual da terra e lacuna em relação ao potencial</h1>
    <p>
      O uso atual da terra vem do MapBiomas (coleção 10), reclassificado nos papéis dos segmentos
      e agregado na grade de análise. Ele é usado apenas como máscara, validação e descrição, nunca
      como entrada da aptidão ou do zoneamento. A lacuna entre potencial e uso atual é a terra
      classificada como apta (S2 ou melhor) para um segmento, mas sem esse uso hoje.
    </p>

    <h2>Composição do uso atual</h2>
    <PlotlyChart
      :data="compositionData"
      :layout="{ height: 360, margin: { l: 170, r: 48 }, yaxis: { dtick: 1 }, xaxis: { title: { text: '% do território' }, ticksuffix: '%' } }"
    />
    <p class="note">
      O MapBiomas não separa milho nem sorgo, que ficam diluídos na classe de mosaico de culturas.
    </p>

    <h2>Potencial <em>versus</em> uso atual</h2>
    <DataTable :columns="gapColumns" :rows="gapRows" />

    <SegmentSelector v-model="selectedCrop" :segments="gapSegments" :labels="segmentLabels" />
    <div class="map-row">
      <MapPanel raster-path="rl_role.pmtiles">
        <template #legend><MapLegend :spec="roleMapLegend" /></template>
      </MapPanel>
      <MapPanel :raster-path="`underused_${selectedCrop}.pmtiles`">
        <template #legend>
          <MapLegend :spec="underusedMapLegend" />
          <p v-if="meanUnderused !== null" class="underused-mean">
            Em média, {{ fmtShare(meanUnderused) }} da área de cada município é apta para
            {{ segmentLabel(selectedCrop).toLowerCase() }} e não tem esse uso.
          </p>
        </template>
      </MapPanel>
    </div>
    <p class="note">
      A maior parte da terra apta e sem uso é pastagem existente, e não vegetação nativa: o
      potencial não aproveitado concentra-se em áreas já convertidas.
      <template v-if="gapRows.length">
        A maior lacuna absoluta é a de {{ segmentLabel(gapRows[0]!.segment).toLowerCase() }},
        com {{ fmtKm2(gapRows[0]!.area_km2) }} ({{ fmtNum(gapRows[0]!.share_pct, 1) }}% do território).
      </template>
    </p>
  </section>
</template>

<style scoped>
.underused-mean {
  margin-top: var(--space-1);
  color: var(--color-muted);
  font-size: 0.8rem;
}

.note {
  color: var(--color-muted);
  font-size: 0.875rem;
  max-width: 80ch;
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
