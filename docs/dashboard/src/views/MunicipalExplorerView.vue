<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DataTable from '../components/DataTable.vue'
import type { DataTableColumn } from '../components/DataTable.vue'
import MapLegend from '../components/MapLegend.vue'
import type { ChoroplethLayer } from '../components/MapPanel.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import SegmentSelector from '../components/SegmentSelector.vue'
import StatChip from '../components/StatChip.vue'
import { useCsv } from '../composables/useCsv'
import { useJson } from '../composables/useJson'
import { deltaLegend, suitabilityLegend, underusedLegend } from '../legends'
import { PAL_DIV, PAL_SUIT, PAL_UNDERUSED } from '../palettes'
import { useSelectionStore } from '../stores/useSelectionStore'
import type { MunicipalRankingRow, SegmentsConfig } from '../types/data'

// Delta is off delta_ssp585_2051_2070 only (the ranking CSV/geojson bake in the
// hottest scenario/window, not a full SSP x window matrix — see CLAUDE.md §6).
const DELTA_SSP = 'ssp585'
const DELTA_WINDOW = '2051-70'
// Only these 5 segments have a delta_<segment> column (matches Cmip6View.vue's
// DELTA_SEGMENTS) and these 4 have an underused_<crop> column (matches
// RealizedUseView.vue's UNDERUSED_CROPS) — cattle/conservation/solar have no
// realized-role counterpart by construction, so underused_* doesn't exist for them.
const DELTA_SEGMENTS = ['soybean', 'sugarcane', 'other_crops', 'conservation', 'solar']
const UNDERUSED_CROPS = ['soybean', 'sugarcane', 'other_crops', 'pisciculture']

type Theme = 'suit' | 'delta' | 'underused'
const THEME_LABELS: Record<Theme, string> = {
  suit: 'Viabilidade',
  delta: `ΔViabilidade (${DELTA_SSP.toUpperCase()}, ${DELTA_WINDOW})`,
  underused: 'Subutilização',
}

const route = useRoute()
const router = useRouter()
const selection = useSelectionStore()

const { data: rows, loading } = useCsv<MunicipalRankingRow>('csv/municipal_ranking.csv')
const { data: segmentsCfg } = useJson<SegmentsConfig>('json/segments.json')
const segmentOrder = computed(() => (segmentsCfg.value ? Object.keys(segmentsCfg.value.segments) : []))
const labels = computed<Record<string, string>>(() =>
  segmentsCfg.value
    ? Object.fromEntries(Object.entries(segmentsCfg.value.segments).map(([k, v]) => [k, v.label]))
    : {},
)

const theme = ref<Theme>('suit')
const themeSegments = computed<Record<Theme, string[]>>(() => ({
  suit: segmentOrder.value,
  delta: DELTA_SEGMENTS,
  underused: UNDERUSED_CROPS,
}))
const selectedSegment = ref('soybean')
watch(theme, () => {
  const list = themeSegments.value[theme.value]
  if (!list.includes(selectedSegment.value)) selectedSegment.value = list[0] ?? ''
})

const search = ref('')
const filteredRows = computed(() => {
  const q = search.value.trim().toLowerCase()
  const all = rows.value ?? []
  return q ? all.filter((r) => r.NM_MUN.toLowerCase().includes(q)) : all
})

if (typeof route.params.name === 'string' && route.params.name) selection.select(route.params.name)

const selected = computed(() => rows.value?.find((r) => r.NM_MUN === selection.selectedMunicipality) ?? null)

function selectMunicipality(name: string): void {
  selection.select(name)
  search.value = ''
  router.replace({ name: 'municipal', params: { name } })
}

watch(
  () => route.params.name,
  (name) => {
    if (typeof name === 'string' && name) selection.select(name)
  },
)

function onFeatureClick(properties: Record<string, unknown>): void {
  const name = properties.NM_MUN
  if (typeof name === 'string') selectMunicipality(name)
}

const metricKey = computed(
  () => `${theme.value === 'suit' ? 'suit' : theme.value === 'delta' ? 'delta' : 'underused'}_${selectedSegment.value}` as keyof MunicipalRankingRow,
)

const segmentLabel = computed(() => labels.value[selectedSegment.value] ?? selectedSegment.value)

function formatMetric(value: number): string {
  if (theme.value === 'underused') return `${(100 * value).toFixed(0)}%`
  if (theme.value === 'delta') return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2)
  return value.toFixed(2)
}

const choropleth = computed<ChoroplethLayer>(() => {
  if (theme.value === 'delta') {
    return {
      path: 'municipal_ranking.geojson',
      property: metricKey.value,
      stops: [
        [-0.15, PAL_DIV[0]!],
        [0, PAL_DIV[1]!],
        [0.15, PAL_DIV[2]!],
      ],
    }
  }
  if (theme.value === 'underused') {
    return {
      path: 'municipal_ranking.geojson',
      property: metricKey.value,
      stops: [
        [0, PAL_UNDERUSED[0]!],
        [1, PAL_UNDERUSED[1]!],
      ],
    }
  }
  const n = PAL_SUIT.length
  return {
    path: 'municipal_ranking.geojson',
    property: metricKey.value,
    stops: PAL_SUIT.map((color, i) => [i / (n - 1), color]),
  }
})

const mapLegend = computed(() => {
  if (theme.value === 'delta') return deltaLegend(segmentLabel.value, DELTA_SSP, DELTA_WINDOW)
  if (theme.value === 'underused') return underusedLegend(segmentLabel.value)
  return suitabilityLegend(segmentLabel.value)
})

const tableColumns = computed<DataTableColumn<MunicipalRankingRow>[]>(() => [
  { key: 'NM_MUN', label: 'Município' },
  { key: metricKey.value, label: `${THEME_LABELS[theme.value]}: ${segmentLabel.value}`, format: (r) => formatMetric(Number(r[metricKey.value])) },
])

const barData = computed<PlotlyDatum[]>(() => {
  const r = selected.value
  if (!r) return []
  return [
    {
      type: 'bar',
      x: segmentOrder.value.map((s) => r[`suit_${s}` as keyof MunicipalRankingRow] as number),
      y: segmentOrder.value.map((s) => labels.value[s] ?? s),
      orientation: 'h',
    },
  ]
})

const deltaBarData = computed<PlotlyDatum[]>(() => {
  const r = selected.value
  if (!r) return []
  return [
    {
      type: 'bar',
      x: segmentOrder.value.map((s) => r[`delta_${s}` as keyof MunicipalRankingRow] as number),
      y: segmentOrder.value.map((s) => labels.value[s] ?? s),
      orientation: 'h',
      marker: {
        color: segmentOrder.value.map((s) => ((r[`delta_${s}` as keyof MunicipalRankingRow] as number) < 0 ? '#b2182b' : '#2166ac')),
      },
    },
  ]
})
</script>

<template>
  <section>
    <h1>Explorador Municipal</h1>
    <p>
      Ranking dos 247 municípios por viabilidade, mudança climática ou subutilização, por
      segmento. Clique numa linha da tabela ou num município no mapa para ver seu perfil completo.
    </p>

    <SegmentSelector v-model="theme" :segments="['suit', 'delta', 'underused']" :labels="THEME_LABELS" />
    <SegmentSelector v-model="selectedSegment" :segments="themeSegments[theme]" :labels="labels" />

    <p v-if="loading">Carregando dados municipais…</p>

    <div class="explorer-row">
      <div class="map-col">
        <MapPanel
          :choropleth="choropleth"
          :outline="false"
          :highlight-municipality="selected?.NM_MUN ?? null"
          @feature-click="onFeatureClick"
        >
          <template #legend><MapLegend :spec="mapLegend" /></template>
        </MapPanel>
      </div>
      <div class="table-col">
        <input v-model="search" type="search" placeholder="Buscar município..." class="search-input" />
        <div class="table-scroll">
          <DataTable
            :columns="tableColumns"
            :rows="filteredRows"
            row-key="NM_MUN"
            :selected-value="selected?.NM_MUN ?? null"
            sortable
            :initial-sort-key="metricKey"
            initial-sort-dir="desc"
            @row-click="(row) => selectMunicipality(row.NM_MUN)"
          />
        </div>
      </div>
    </div>

    <div v-if="selected" class="selected-panel">
      <h2>{{ selected.NM_MUN }} ({{ selected.SIGLA_UF }})</h2>
      <div class="stat-row">
        <StatChip label="Zona" :value="selected.zone" />
        <StatChip
          :label="`${THEME_LABELS[theme]} — ${segmentLabel}`"
          :value="formatMetric(Number(selected[metricKey]))"
        />
      </div>
      <PlotlyChart :data="barData" :layout="{ height: 300, xaxis: { range: [0, 1] } }" />
      <h3>&Delta;Viabilidade por segmento (SSP5-8.5, 2051-2070)</h3>
      <PlotlyChart :data="deltaBarData" :layout="{ height: 260 }" />
    </div>
    <p v-else class="hint">Nenhum município selecionado ainda.</p>
  </section>
</template>

<style scoped>
.search-input {
  width: 100%;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font: inherit;
  margin-block: var(--space-2);
}

.explorer-row {
  display: flex;
  gap: var(--space-3);
  margin-block: var(--space-3);
  align-items: flex-start;
}

.map-col {
  flex: 1.4;
  min-width: 0;
}

.table-col {
  flex: 1;
  min-width: 0;
}

.table-scroll {
  max-height: 480px;
  overflow-y: auto;
}

@media (max-width: 720px) {
  .explorer-row {
    flex-direction: column;
  }
}

.selected-panel {
  margin-top: var(--space-4);
}

.stat-row {
  display: flex;
  gap: var(--space-3);
  margin-block: var(--space-3);
}

.hint {
  color: var(--color-muted);
}
</style>
