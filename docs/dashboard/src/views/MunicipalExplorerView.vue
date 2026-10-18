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
import { useManifest } from '../composables/useManifest'
import { fmtInt, fmtNum, fmtShare, fmtSigned } from '../format'
import { deltaLegend, suitabilityLegend } from '../legends'
import { PAL_DIV, PAL_SUIT, PAL_UNDERUSED } from '../palettes'
import { useSelectionStore } from '../stores/useSelectionStore'
import type { MunicipalRankingRow } from '../types/data'

const route = useRoute()
const router = useRouter()
const selection = useSelectionStore()

const { manifest, segmentKeys: segmentOrder, segmentLabels: labels, scenarioLabel, zoneName } = useManifest()
const { data: rows, loading } = useCsv<MunicipalRankingRow>('csv/municipal_ranking.csv')

// The ranking bakes in ONE scenario (manifest.municipal_delta — MUNICIPAL_DELTA in
// build_dashboard_assets.py). Which segments carry a delta_/underused_ column is read
// from the CSV header itself, never from a list kept here.
const deltaScenario = computed(() => {
  const d = manifest.value?.municipal_delta
  return d ? scenarioLabel(d.ssp, d.window) : ''
})
const columnsWith = (prefix: string) =>
  segmentOrder.value.filter((s) => rows.value?.length && `${prefix}${s}` in rows.value[0]!)

type Theme = 'suit' | 'delta' | 'underused'
const THEME_LABELS = computed<Record<Theme, string>>(() => ({
  suit: 'Aptidão',
  delta: `ΔS (${deltaScenario.value})`,
  underused: 'Terra apta sem o uso',
}))

const theme = ref<Theme>('suit')
const themeSegments = computed<Record<Theme, string[]>>(() => ({
  suit: segmentOrder.value,
  delta: columnsWith('delta_'),
  underused: columnsWith('underused_'),
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
  if (theme.value === 'underused') return fmtShare(value, 0)
  if (theme.value === 'delta') return fmtSigned(value, 3)
  return fmtNum(value, 2)
}
const deltaDomain = computed<[number, number]>(() => manifest.value?.delta_domain ?? [-0.15, 0.15])

const choropleth = computed<ChoroplethLayer>(() => {
  if (theme.value === 'delta') {
    return {
      path: 'municipal_ranking.geojson',
      property: metricKey.value,
      stops: [
        [deltaDomain.value[0], PAL_DIV[0]!],
        [0, PAL_DIV[1]!],
        [deltaDomain.value[1], PAL_DIV[2]!],
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
  if (theme.value === 'delta') return deltaLegend(segmentLabel.value, deltaScenario.value, deltaDomain.value)
  if (theme.value === 'underused') {
    const n = PAL_UNDERUSED.length
    return {
      kind: 'gradient' as const,
      title: `Fração do município apta e sem o uso — ${segmentLabel.value}`,
      stops: PAL_UNDERUSED.map((c, i) => [i / (n - 1), c] as [number, string]),
      format: (v: number) => fmtShare(v, 0),
    }
  }
  return suitabilityLegend(segmentLabel.value)
})

const tableColumns = computed<DataTableColumn<MunicipalRankingRow>[]>(() => [
  { key: 'NM_MUN', label: 'Município' },
  { key: metricKey.value, label: `${THEME_LABELS.value[theme.value]}: ${segmentLabel.value}`, format: (r) => formatMetric(Number(r[metricKey.value])) },
])

const barData = computed<PlotlyDatum[]>(() => {
  const r = selected.value
  if (!r) return []
  return [
    {
      type: 'bar',
      x: segmentOrder.value.map((s) => r[`suit_${s}` as keyof MunicipalRankingRow] as number),
      y: segmentOrder.value.map((s) => labels.value[s] ?? s),
      text: segmentOrder.value.map((s) => fmtNum(r[`suit_${s}` as keyof MunicipalRankingRow] as number, 2)),
      textposition: 'outside',
      cliponaxis: false,
      hoverinfo: 'y+text',
      orientation: 'h',
    },
  ]
})

const deltaBarData = computed<PlotlyDatum[]>(() => {
  const r = selected.value
  if (!r) return []
  const segs = themeSegments.value.delta
  const val = (s: string) => r[`delta_${s}` as keyof MunicipalRankingRow] as number
  return [
    {
      type: 'bar',
      x: segs.map(val),
      y: segs.map((s) => labels.value[s] ?? s),
      text: segs.map((s) => fmtSigned(val(s), 3)),
      textposition: 'outside',
      cliponaxis: false,
      hoverinfo: 'y+text',
      orientation: 'h',
      marker: { color: segs.map((s) => (val(s) < 0 ? PAL_DIV[0]! : PAL_DIV[2]!)) },
    },
  ]
})
</script>

<template>
  <section>
    <h1>Unidades municipais de decisão</h1>
    <p>
      Médias municipais de aptidão, de mudança projetada (ΔS) e da fração de terra apta sem o uso
      correspondente, para as {{ fmtInt(rows?.length ?? manifest?.aoi.n_municipalities) }} unidades
      municipais de GO e DF. Selecione uma linha da tabela ou um município no mapa para ver o seu
      perfil.
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
        <input v-model="search" type="search" placeholder="Buscar município…" aria-label="Buscar município" class="search-input" />
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
        <StatChip :label="zoneName(selected.zone) || 'zona agroambiental (média arredondada)'" :value="`Zona ${selected.zone}`" />
        <StatChip
          :label="`${THEME_LABELS[theme]} — ${segmentLabel}`"
          :value="formatMetric(Number(selected[metricKey]))"
        />
      </div>
      <h3>Aptidão média por segmento</h3>
      <PlotlyChart :data="barData" :layout="{ height: 300, margin: { l: 170 }, xaxis: { range: [0, 1], title: { text: 'aptidão (0–1)' } } }" />
      <h3>Mudança projetada por segmento ({{ deltaScenario }})</h3>
      <PlotlyChart :data="deltaBarData" :layout="{ height: 280, margin: { l: 170 }, xaxis: { title: { text: 'ΔS médio' }, zeroline: true } }" />
    </div>
    <p v-else class="hint">Selecione um município na tabela ou no mapa.</p>
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
