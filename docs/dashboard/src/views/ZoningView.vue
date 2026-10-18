<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref } from 'vue'
import DataTable from '../components/DataTable.vue'
import type { DataTableColumn } from '../components/DataTable.vue'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import ZoneCard from '../components/ZoneCard.vue'
import { useCsv } from '../composables/useCsv'
import { useManifest } from '../composables/useManifest'
import { fmtKm2, fmtNum, fmtPct } from '../format'
import { zoneLegend } from '../legends'
import type { ManifestZone, ZoneProfileRow, ZoningKselectRow } from '../types/data'

const { manifest, zones, zoneVocation, segmentShort } = useManifest()
const { data: profiles } = useCsv<ZoneProfileRow>('csv/zone_profiles.csv')
const zoneCount = computed(() => zones.value.length)

const mapLegend = computed(() =>
  zoneLegend(zoneCount.value, Object.fromEntries(zones.value.map((z) => [z.zone, z.name]))),
)

const selectedZone = ref<number>(1)
const selectedProfile = computed(() => profiles.value?.find((p) => p.zone === selectedZone.value) ?? null)

// --- zone summary (tab:zone-suit's label rows + zone_area.csv) ------------------
const zoneColumns: DataTableColumn<ManifestZone>[] = [
  { key: 'zone', label: 'Zona', format: (r) => `Z${r.zone}` },
  { key: 'name', label: 'Descrição' },
  { key: 'area_km2', label: 'Área', format: (r) => fmtKm2(r.area_km2) },
  { key: 'share_pct', label: 'Parcela', format: (r) => fmtPct(r.share_pct) },
  { key: 'comparative_segment', label: 'Vocação primária', format: (r) => segmentShort(r.comparative_segment) },
  { key: 'comparative_segment_2', label: 'Vocação secundária', format: (r) => segmentShort(r.comparative_segment_2) },
  { key: 'comparative_margin', label: 'Margem (z)', format: (r) => fmtNum(r.comparative_margin, 2) },
]
const pairedShare = computed(() => zones.value.filter((z) => z.paired).reduce((a, z) => a + z.share_pct, 0))
const pairedZones = computed(() => zones.value.filter((z) => z.paired).map((z) => String(z.zone)))

// --- k selection (zoning_kselect.csv, held-out columns only) -----------------------
// No fallback to pre-holdout column names: a CSV without them is a WRONG table, not a
// missing one (CLAUDE.md), so the chart refuses instead of plotting in-sample values.
const { data: kselect } = useCsv<ZoningKselectRow>('csv/zoning_kselect.csv')
const kselectValid = computed(() => (kselect.value ?? []).every((r) => Number.isFinite(r.ari_holdout)))
const kRows = computed(() => (kselectValid.value ? kselect.value ?? [] : []))
const kBest = computed(() => {
  const rows = kRows.value
  if (!rows.length) return null
  return rows.reduce((a, b) => (b.ari_holdout > a.ari_holdout ? b : a))
})
const kAdoptedRow = computed(() => kRows.value.find((r) => r.k === zoneCount.value) ?? null)
const silRange = computed(() => {
  const s = kRows.value.map((r) => r.silhouette_val)
  return s.length ? [Math.min(...s), Math.max(...s)] : null
})
const kselectData = computed<PlotlyDatum[]>(() => {
  const rows = kRows.value
  const x = rows.map((r) => r.k)
  return [
    { type: 'scatter', mode: 'lines+markers', name: 'ARI de validação espacial (↑)', x, y: rows.map((r) => r.ari_holdout) },
    { type: 'scatter', mode: 'lines+markers', name: 'silhueta, metade de validação (↑)', x, y: rows.map((r) => r.silhouette_val) },
    {
      type: 'scatter', mode: 'lines+markers', name: 'Davies–Bouldin, metade de validação (↓)',
      x, y: rows.map((r) => r.davies_bouldin_val), yaxis: 'y2', line: { dash: 'dot' },
    },
  ]
})
const kselectLayout = computed(() => ({
  height: 320,
  xaxis: { title: { text: 'k' }, dtick: 2 },
  yaxis: { title: { text: 'ARI / silhueta' } },
  yaxis2: { title: { text: 'Davies–Bouldin' }, overlaying: 'y' as const, side: 'right' as const },
  legend: { orientation: 'h' as const, y: -0.25 },
  shapes: zoneCount.value
    ? [{
        type: 'line' as const, x0: zoneCount.value, x1: zoneCount.value, yref: 'paper' as const, y0: 0, y1: 1,
        line: { color: '#d7191c', width: 1, dash: 'dash' as const },
      }]
    : [],
  annotations: zoneCount.value
    ? [{
        x: zoneCount.value, yref: 'paper' as const, y: 1, text: `k adotado = ${zoneCount.value}`,
        showarrow: false, yanchor: 'bottom' as const, font: { color: '#d7191c', size: 11 },
      }]
    : [],
}))
</script>

<template>
  <section>
    <h1>Zoneamento agroambiental</h1>
    <p v-if="manifest">
      O território é particionado em <strong>{{ zoneCount }} zonas agroambientais</strong> por
      <em>k</em>-médias aplicado a {{ manifest.stack.n_zoning_bands }} bandas biofísicas selecionadas,
      ponderadas por tema e descorrelacionadas por análise de componentes principais. A aptidão nunca
      é variável de agrupamento: serve apenas para estratificar a amostra e descrever as zonas. As
      zonas são numeradas por elevação média decrescente e rotuladas pelo
      <strong>melhor segmento comparativo</strong>, isto é, o segmento cuja aptidão, padronizada por
      escore <em>z</em> entre as zonas, é a mais alta.
    </p>

    <MapPanel raster-path="zones_present.pmtiles">
      <template #legend><MapLegend :spec="mapLegend" /></template>
    </MapPanel>

    <h2>Síntese das zonas</h2>
    <DataTable :columns="zoneColumns" :rows="zones" />
    <p v-if="pairedZones.length" class="note">
      {{ pairedZones.length > 1 ? `Nas Zonas ${pairedZones.join(' e ')}` : `Na Zona ${pairedZones[0]}` }}
      ({{ fmtPct(pairedShare) }} do território), a margem entre os dois
      primeiros segmentos é inferior a {{ fmtNum(manifest?.zone_pair_margin, 2) }} desvio-padrão: essas
      zonas devem ser lidas como pares de usos, e não por um rótulo único.
    </p>

    <h2>Perfil da zona</h2>
    <div class="zone-buttons" role="tablist" aria-label="Zona">
      <button
        v-for="z in zones"
        :key="z.zone"
        type="button"
        role="tab"
        :aria-selected="z.zone === selectedZone"
        :class="['zone-btn', { active: z.zone === selectedZone }]"
        :title="z.name"
        @click="selectedZone = z.zone"
      >
        Zona {{ z.zone }} · {{ zoneVocation(z.zone) }}
      </button>
    </div>
    <ZoneCard v-if="selectedProfile" :profile="selectedProfile" />

    <h2>Seleção do número de zonas</h2>
    <p v-if="kRows.length && kBest && silRange" class="note">
      O número de zonas foi varrido de k = {{ kRows[0]!.k }} a {{ kRows[kRows.length - 1]!.k }}, com a
      partição ajustada na metade de calibração e avaliada na metade de validação. O ARI de validação
      espacial é máximo em k = {{ kBest.k }} ({{ fmtNum(kBest.ari_holdout, 3) }})<template
        v-if="kAdoptedRow && kAdoptedRow.k !== kBest.k">; o k adotado tem ARI {{ fmtNum(kAdoptedRow.ari_holdout, 3) }}</template>.
      A silhueta na metade de validação varia apenas entre {{ fmtNum(silRange[0], 3) }} e
      {{ fmtNum(silRange[1], 3) }} em toda a varredura: o território não tem estrutura de agrupamento
      forte em nenhum k, e o zoneamento é um dispositivo de partição, não a descoberta de grupos
      naturais.
    </p>
    <p v-else-if="kselect && !kselectValid" role="alert">
      O arquivo <code>zoning_kselect.csv</code> não traz as colunas da metade de validação e foi
      recusado; regenere-o com <code>tools/gen_diag_csvs.py zoning</code>.
    </p>
    <PlotlyChart v-if="kRows.length" :data="kselectData" :layout="kselectLayout" />
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
  color: var(--color-text);
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

.note {
  color: var(--color-muted);
  font-size: 0.875rem;
  max-width: 80ch;
}
</style>
