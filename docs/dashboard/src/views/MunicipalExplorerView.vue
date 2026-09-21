<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MapLegend from '../components/MapLegend.vue'
import type { ChoroplethLayer } from '../components/MapPanel.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import StatChip from '../components/StatChip.vue'
import { useCsv } from '../composables/useCsv'
import { useJson } from '../composables/useJson'
import { gradientFromStops, zoneLegend } from '../legends'
import { zonePalette } from '../palettes'
import { useSelectionStore } from '../stores/useSelectionStore'
import type { MunicipalRankingRow, SegmentsConfig, ZoneProfileRow } from '../types/data'

const route = useRoute()
const router = useRouter()
const selection = useSelectionStore()

const { data: rows } = useCsv<MunicipalRankingRow>('csv/municipal_ranking.csv')
const { data: segmentsCfg } = useJson<SegmentsConfig>('json/segments.json')
// Zone count is read from the data, never hardcoded — zoning is K=10 today but has
// changed before (was K=7) and may again.
const { data: zoneProfiles } = useCsv<ZoneProfileRow>('csv/zone_profiles.csv')
const zoneCount = computed(() => zoneProfiles.value?.length ?? 0)
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

type ColorField = 'suit_soybean' | 'suit_sugarcane' | 'suit_other_crops' | 'zone' | 'delta_other_crops' | 'underused_soybean'

const COLOR_FIELD_LABELS_PT: Record<ColorField, string> = {
  suit_soybean: 'Aptidão: Soja',
  suit_sugarcane: 'Aptidão: Cana-de-açúcar',
  suit_other_crops: 'Aptidão: Outras culturas',
  zone: 'Zona',
  delta_other_crops: 'ΔS: Outras culturas (SSP5-8.5, 2051-70)',
  underused_soybean: 'Subutilização: Soja',
}

const colorField = ref<ColorField>('suit_soybean')
const choropleth = computed<ChoroplethLayer>(() => {
  if (colorField.value === 'zone') {
    const n = zoneCount.value || 10
    const colors = zonePalette(n)
    return {
      path: 'municipal_ranking.geojson',
      property: 'zone',
      stops: colors.map((color, i) => [i, color]),
    }
  }
  if (colorField.value === 'delta_other_crops') {
    return {
      path: 'municipal_ranking.geojson',
      property: colorField.value,
      stops: [
        [-0.1, '#b2182b'],
        [0, '#f7f7f7'],
        [0.1, '#2166ac'],
      ],
    }
  }
  if (colorField.value === 'underused_soybean') {
    return {
      path: 'municipal_ranking.geojson',
      property: colorField.value,
      stops: [
        [0, '#f7f7f7'],
        [1, '#d7301f'],
      ],
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

const mapLegend = computed(() => {
  if (colorField.value === 'zone') return zoneLegend(zoneCount.value || 10)
  if (colorField.value === 'delta_other_crops') {
    return gradientFromStops(COLOR_FIELD_LABELS_PT[colorField.value], choropleth.value.stops, (v) =>
      v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2),
    )
  }
  if (colorField.value === 'underused_soybean') {
    return gradientFromStops(COLOR_FIELD_LABELS_PT[colorField.value], choropleth.value.stops, (v) =>
      v >= 1 ? 'subutilizado' : 'não subutilizado',
    )
  }
  return gradientFromStops(COLOR_FIELD_LABELS_PT[colorField.value], choropleth.value.stops, (v) => v.toFixed(2))
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
    <p>Clique em um município no mapa, ou busque por nome, para ver seu perfil completo de aptidão.</p>

    <input v-model="search" type="search" placeholder="Buscar município..." class="search-input" />
    <ul v-if="matches.length" class="search-results">
      <li v-for="m in matches" :key="m.NM_MUN">
        <button type="button" @click="selectMunicipality(m.NM_MUN)">{{ m.NM_MUN }}</button>
      </li>
    </ul>

    <label class="color-field-label">
      Coropletia:
      <select v-model="colorField">
        <option value="suit_soybean">Aptidão: Soja</option>
        <option value="suit_sugarcane">Aptidão: Cana-de-açúcar</option>
        <option value="suit_other_crops">Aptidão: Outras culturas</option>
        <option value="zone">Zona</option>
        <option value="delta_other_crops">&Delta;S: Outras culturas (SSP5-8.5, 2051-70)</option>
        <option value="underused_soybean">Subutilização: Soja</option>
      </select>
    </label>

    <MapPanel :choropleth="choropleth" :outline="false" @feature-click="onFeatureClick">
      <template #legend><MapLegend :spec="mapLegend" /></template>
    </MapPanel>

    <div v-if="selected" class="selected-panel">
      <h2>{{ selected.NM_MUN }} ({{ selected.SIGLA_UF }})</h2>
      <div class="stat-row">
        <StatChip label="Zona" :value="selected.zone" />
        <StatChip label="Aptidão — soja" :value="selected.suit_soybean.toFixed(2)" />
        <StatChip
          label="&Delta;S outras culturas (2051-70)"
          :value="selected.delta_other_crops.toFixed(3)"
          hint="SSP5-8.5, 2051-2070 — aptidão futura menos aptidão presente"
        />
        <StatChip
          label="Subutilização: soja"
          :value="`${(100 * selected.underused_soybean).toFixed(0)}%`"
          hint="Parcela do município viável (S1/S2), mas não cultivada atualmente com soja"
        />
      </div>
      <PlotlyChart :data="barData" :layout="{ height: 300, xaxis: { range: [0, 1] } }" />
      <h3>&Delta;Aptidão por segmento (SSP5-8.5, 2051-2070)</h3>
      <PlotlyChart :data="deltaBarData" :layout="{ height: 260 }" />
    </div>
    <p v-else class="hint">Nenhum município selecionado ainda.</p>
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
