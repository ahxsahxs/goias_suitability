<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { ChoroplethLayer } from '../components/MapPanel.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import StatChip from '../components/StatChip.vue'
import { useCsv } from '../composables/useCsv'
import { useJson } from '../composables/useJson'
import { useSelectionStore } from '../stores/useSelectionStore'
import type { MunicipalRankingRow, SegmentsConfig } from '../types/data'

const route = useRoute()
const router = useRouter()
const selection = useSelectionStore()

const { data: rows } = useCsv<MunicipalRankingRow>('csv/municipal_ranking.csv')
const { data: segmentsCfg } = useJson<SegmentsConfig>('json/segments.json')
const segmentOrder = computed(() => (segmentsCfg.value ? Object.keys(segmentsCfg.value.segments) : []))
const labels = computed<Record<string, string>>(() =>
  segmentsCfg.value
    ? Object.fromEntries(Object.entries(segmentsCfg.value.segments).map(([k, v]) => [k, v.label]))
    : {},
)

const search = ref('')
const matches = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return []
  return (rows.value ?? []).filter((r) => r.NM_MUN.toLowerCase().includes(q)).slice(0, 8)
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

const colorField = ref<'suit_soybean' | 'suit_sugarcane' | 'suit_other_crops' | 'zone'>('suit_soybean')
const choropleth = computed<ChoroplethLayer>(() => {
  if (colorField.value === 'zone') {
    return {
      path: 'municipal_ranking.geojson',
      property: 'zone',
      stops: Array.from({ length: 10 }, (_, i) => [i, `hsl(${(i * 36) % 360}, 60%, 55%)`]),
    }
  }
  return {
    path: 'municipal_ranking.geojson',
    property: colorField.value,
    stops: [
      [0, '#d7191c'],
      [0.5, '#ffffbf'],
      [1, '#1a9641'],
    ],
  }
})

function onFeatureClick(properties: Record<string, unknown>): void {
  const name = properties.NM_MUN
  if (typeof name === 'string') selectMunicipality(name)
}

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
</script>

<template>
  <section>
    <h1>Municipal Explorer</h1>
    <p>Click a municipality on the map, or search by name, to read its full suitability profile.</p>

    <input v-model="search" type="search" placeholder="Search municipality..." class="search-input" />
    <ul v-if="matches.length" class="search-results">
      <li v-for="m in matches" :key="m.NM_MUN">
        <button type="button" @click="selectMunicipality(m.NM_MUN)">{{ m.NM_MUN }}</button>
      </li>
    </ul>

    <label class="color-field-label">
      Choropleth:
      <select v-model="colorField">
        <option value="suit_soybean">Suitability: Soybean</option>
        <option value="suit_sugarcane">Suitability: Sugarcane</option>
        <option value="suit_other_crops">Suitability: Other crops</option>
        <option value="zone">Zone</option>
      </select>
    </label>

    <MapPanel :choropleth="choropleth" :outline="false" @feature-click="onFeatureClick">
      <template #legend>Colored by {{ colorField }}</template>
    </MapPanel>

    <div v-if="selected" class="selected-panel">
      <h2>{{ selected.NM_MUN }} ({{ selected.SIGLA_UF }})</h2>
      <div class="stat-row">
        <StatChip label="Zone" :value="selected.zone" />
        <StatChip label="Soybean suitability" :value="selected.suit_soybean.toFixed(2)" />
      </div>
      <PlotlyChart :data="barData" :layout="{ height: 300, xaxis: { range: [0, 1] } }" />
    </div>
    <p v-else class="hint">No municipality selected yet.</p>
  </section>
</template>

<style scoped>
.search-input {
  width: 100%;
  max-width: 360px;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font: inherit;
  margin-block: var(--space-2);
}

.search-results {
  list-style: none;
  padding: 0;
  margin: 0 0 var(--space-3);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.search-results button {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius);
  cursor: pointer;
  font: inherit;
}

.color-field-label {
  display: block;
  margin-block: var(--space-2);
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
