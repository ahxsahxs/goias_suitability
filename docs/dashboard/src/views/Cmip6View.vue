<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DataTable from '../components/DataTable.vue'
import type { DataTableColumn } from '../components/DataTable.vue'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import ScenarioSelector from '../components/ScenarioSelector.vue'
import type { Scenario } from '../components/ScenarioSelector.vue'
import SegmentSelector from '../components/SegmentSelector.vue'
import { useCsv } from '../composables/useCsv'
import { useManifest } from '../composables/useManifest'
import { fmtNum, fmtPp, fmtShare, fmtSigned, fmtRange } from '../format'
import { deltaLegend } from '../legends'
import type {
  Cmip6DowngradeRow,
  Cmip6ShiftMeanRow,
  Cmip6ShiftShareRow,
  Cmip6TransitionRow,
  Cmip6ZoneShiftRow,
} from '../types/data'

const route = useRoute()
const router = useRouter()
const { manifest, segmentKeys, segmentLabels, segmentLabel, sspLabel, windowLabel, scenarioLabel, zones, zoneName } =
  useManifest()

// Without route params, open on the scenario the thesis treats as its worst case
// (manifest.municipal_delta) and on the first segment; never on literals of our own.
const scenario = ref<Scenario>({
  ssp: (route.params.ssp as string) || '',
  window: (route.params.window as string) || '',
})
const selectedSegment = ref((route.params.segment as string) || '')
watch(
  manifest,
  (m) => {
    if (!m) return
    if (!scenario.value.ssp) scenario.value = { ssp: m.municipal_delta.ssp, window: m.municipal_delta.window }
    if (!selectedSegment.value) selectedSegment.value = m.segments[0]?.key ?? ''
  },
  { immediate: true },
)

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

const scenarioText = computed(() => scenarioLabel(scenario.value.ssp, scenario.value.window))
const inScenario = <T extends { ssp: string; window: string }>(r: T) =>
  r.ssp === scenario.value.ssp && r.window === scenario.value.window

// Segments with a shipped ΔS raster for this scenario (scanned at build time).
const mapSegments = computed(
  () => manifest.value?.delta_layers[scenario.value.ssp]?.[scenario.value.window] ?? [],
)
const hasLayer = computed(() => mapSegments.value.includes(selectedSegment.value))
const deltaPath = computed(
  () => `delta_${scenario.value.ssp}_${scenario.value.window}_${selectedSegment.value}.pmtiles`,
)
const deltaMapLegend = computed(() =>
  deltaLegend(segmentLabel(selectedSegment.value), scenarioText.value, manifest.value?.delta_domain ?? [-1, 1]),
)

const horizon = computed(() => {
  const w = manifest.value?.windows ?? []
  return w.length ? fmtRange(w[0]!.start, w[w.length - 1]!.end) : ''
})
const s2Break = computed(() => manifest.value?.fao_breaks[1] ?? null)

// --- tab:shift-mean ----------------------------------------------------------------
const { data: shiftMean } = useCsv<Cmip6ShiftMeanRow>('csv/cmip6_shift_mean.csv')
const combos = computed(() =>
  (manifest.value?.ssps ?? []).flatMap((s) => (manifest.value?.windows ?? []).map((w) => ({ ssp: s.key, window: w.key }))),
)
const shiftMeanData = computed<PlotlyDatum[]>(() => {
  const rows = shiftMean.value ?? []
  return combos.value.map((c) => ({
    type: 'bar',
    name: scenarioLabel(c.ssp, c.window),
    x: segmentKeys.value.map(segmentLabel),
    y: segmentKeys.value.map((s) => rows.find((r) => r.segment === s && r.ssp === c.ssp && r.window === c.window)?.delta_s ?? null),
  }))
})
interface MeanRow { segment: string; [combo: string]: string | number }
const meanRows = computed<MeanRow[]>(() =>
  segmentKeys.value.map((s) => {
    const row: MeanRow = { segment: segmentLabel(s) }
    combos.value.forEach((c) => {
      row[`${c.ssp}_${c.window}`] =
        (shiftMean.value ?? []).find((r) => r.segment === s && r.ssp === c.ssp && r.window === c.window)?.delta_s ?? Number.NaN
    })
    return row
  }),
)
const meanColumns = computed<DataTableColumn<MeanRow>[]>(() => [
  { key: 'segment', label: 'Segmento' },
  ...combos.value.map((c) => ({
    key: `${c.ssp}_${c.window}`,
    label: `${sspLabel(c.ssp)} ${windowLabel(c.window)}`,
    format: (r: MeanRow) => fmtSigned(Number(r[`${c.ssp}_${c.window}`]), 4),
  })),
])

// --- tab:shift-share + tab:downgrade-share (selected scenario) ------------------------
const { data: shiftShare } = useCsv<Cmip6ShiftShareRow>('csv/cmip6_shift_share.csv')
const { data: downgrade } = useCsv<Cmip6DowngradeRow>('csv/cmip6_downgrade.csv')
interface ShareRow {
  segment: string
  present: number
  future: number
  pp: number
  rel: number
  downgraded: number
}
const shareRows = computed<ShareRow[]>(() =>
  segmentKeys.value.flatMap((s) => {
    const sh = (shiftShare.value ?? []).find((r) => r.segment === s && inScenario(r))
    if (!sh) return []
    const dg = (downgrade.value ?? []).find((r) => r.segment === s && inScenario(r))
    return [{
      segment: s,
      present: sh.present_share,
      future: sh.future_share,
      pp: 100 * (sh.future_share - sh.present_share),
      rel: sh.present_share > 0 ? (sh.future_share - sh.present_share) / sh.present_share : Number.NaN,
      downgraded: dg?.downgrade_share ?? Number.NaN,
    }]
  }),
)
const shareColumns: DataTableColumn<ShareRow>[] = [
  { key: 'segment', label: 'Segmento', format: (r) => segmentLabel(r.segment) },
  { key: 'present', label: 'Apta no presente', format: (r) => fmtShare(r.present) },
  { key: 'future', label: 'Apta no futuro', format: (r) => fmtShare(r.future) },
  { key: 'pp', label: 'Variação', format: (r) => fmtPp(r.pp) },
  { key: 'rel', label: 'Variação relativa', format: (r) => (Number.isFinite(r.rel) ? `${fmtSigned(100 * r.rel, 1)}%` : '—') },
  { key: 'downgraded', label: 'Células rebaixadas', format: (r) => fmtShare(r.downgraded) },
]
const shareData = computed<PlotlyDatum[]>(() => {
  const rows = [...shareRows.value].reverse()
  const y = rows.map((r) => segmentLabel(r.segment))
  return [
    ...rows.map((r) => ({
      type: 'scatter', mode: 'lines', x: [100 * r.present, 100 * r.future], y: [segmentLabel(r.segment), segmentLabel(r.segment)],
      line: { color: '#9aa39a', width: 2 }, showlegend: false, hoverinfo: 'skip',
    }) as PlotlyDatum),
    { type: 'scatter', mode: 'markers', name: 'presente', x: rows.map((r) => 100 * r.present), y, marker: { color: '#5c6459', size: 10 } },
    { type: 'scatter', mode: 'markers', name: scenarioText.value, x: rows.map((r) => 100 * r.future), y, marker: { color: '#b2182b', size: 10 } },
  ]
})
const worstLoss = computed(() => [...shareRows.value].sort((a, b) => a.pp - b.pp)[0] ?? null)

// --- tab:zone-shift (selected scenario) -------------------------------------------------
const { data: zoneShift } = useCsv<Cmip6ZoneShiftRow>('csv/cmip6_zone_shift.csv')
const zoneShiftSegments = computed(() =>
  segmentKeys.value.filter((s) => (zoneShift.value ?? []).some((r) => r.segment === s && inScenario(r))),
)
const zoneShiftData = computed<PlotlyDatum[]>(() => {
  const rows = (zoneShift.value ?? []).filter(inScenario)
  const segs = zoneShiftSegments.value
  const z = zones.value.map((zz) =>
    segs.map((s) => rows.find((r) => r.segment === s && r.zone === zz.zone)?.delta_s ?? null),
  )
  const domain = manifest.value?.delta_domain ?? [-0.15, 0.15]
  const lim = Math.max(...z.flat().map((v) => Math.abs(v ?? 0)), 1e-4)
  return [{
    type: 'heatmap',
    x: segs.map(segmentLabel),
    y: zones.value.map((zz) => `Zona ${zz.zone} — ${zoneName(zz.zone)}`),
    z,
    zmin: -Math.min(lim, domain[1]),
    zmax: Math.min(lim, domain[1]),
    colorscale: [[0, '#b2182b'], [0.5, '#f7f7f7'], [1, '#2166ac']],
    text: z.map((row) => row.map((v) => fmtSigned(v, 3))),
    texttemplate: '%{text}',
    hovertemplate: '%{y}<br>%{x}: %{text}<extra></extra>',
    colorbar: { title: { text: 'ΔS' }, thickness: 10 },
  } as unknown as PlotlyDatum] // heatmap `text` is a 2-D matrix; @types/plotly.js only types 1-D
})

// --- tab:transition-othercrops (its own scenario, recorded in the CSV) -----------------
const { data: transition } = useCsv<Cmip6TransitionRow>('csv/cmip6_transition_othercrops.csv')
const transitionScenario = computed(() => {
  const r = transition.value?.[0]
  return r ? scenarioLabel(r.ssp, r.window) : ''
})
const faoCodes = computed(() => (manifest.value?.fao_classes ?? []).map((c) => c.code))
const transitionData = computed<PlotlyDatum[]>(() => {
  const rows = transition.value ?? []
  const codes = faoCodes.value
  const z = codes.map((p) => codes.map((f) => rows.find((r) => r.present === p && r.future === f)?.share_pct ?? 0))
  return [{
    type: 'heatmap',
    x: codes.map((c) => `${c} futuro`),
    y: codes.map((c) => `${c} presente`),
    z,
    colorscale: [[0, '#ffffff'], [1, '#7a9a75']],
    showscale: false,
    text: z.map((row) => row.map((v) => (v > 0 ? `${fmtNum(v, 1)}%` : '—'))),
    texttemplate: '%{text}',
    hovertemplate: '%{y} → %{x}: %{text}<extra></extra>',
  } as unknown as PlotlyDatum] // heatmap `text` is a 2-D matrix; @types/plotly.js only types 1-D
})
const transitionSummary = computed(() => {
  const rows = transition.value ?? []
  const codes = faoCodes.value
  const rank = (c: string) => codes.indexOf(c)
  const sum = (pred: (r: Cmip6TransitionRow) => boolean) => rows.filter(pred).reduce((a, r) => a + r.share_pct, 0)
  return {
    downgraded: sum((r) => rank(r.future) < rank(r.present)),
    upgraded: sum((r) => rank(r.future) > rank(r.present)),
    s1Present: sum((r) => r.present === 'S1'),
    s1Future: sum((r) => r.future === 'S1'),
  }
})
</script>

<template>
  <section>
    <h1>Mudança projetada pelo clima</h1>
    <p v-if="manifest">
      A aptidão futura é obtida pelo método dos fatores de mudança (<em>delta-change</em>): as
      anomalias mensais de precipitação (razão) e de temperatura máxima e mínima (diferença aditiva)
      de um conjunto de {{ manifest.gcms.length }} modelos climáticos globais do NEX-GDDP-CMIP6
      ({{ manifest.gcms.join(', ') }}) são aplicadas à normal climatológica
      {{ fmtRange(manifest.baseline.start, manifest.baseline.end) }}, e a aptidão é recalculada com os
      mesmos pesos e funções de pertinência. São {{ manifest.ssps.length }} cenários
      ({{ manifest.ssps.map((s) => s.label).join(' e ') }}) e {{ manifest.windows.length }} janelas
      ({{ manifest.windows.map((w) => fmtRange(w.start, w.end)).join(' e ') }}), cobrindo {{ horizon }}.
      ΔS = S<sub>futuro</sub> − S<sub>presente</sub>, com o presente rederivado pelo mesmo caminho de
      cálculo.
    </p>
    <p class="note">
      Radiação solar e umidade do solo são mantidas na linha de base, o que atenua parte do sinal da
      geração fotovoltaica e da pecuária; terreno, solo e água são estáticos. A concordância entre
      modelos quanto ao sinal da mudança tem pouco contraste espacial e não é mapeada aqui.
    </p>

    <ScenarioSelector v-model="scenario" />
    <SegmentSelector v-model="selectedSegment" :segments="segmentKeys" :labels="segmentLabels" />

    <div class="map-row">
      <MapPanel v-if="hasLayer" :raster-path="deltaPath">
        <template #legend><MapLegend :spec="deltaMapLegend" /></template>
      </MapPanel>
      <p v-else-if="scenario.ssp && selectedSegment" class="note">Não há camada de ΔS exportada para este segmento neste cenário.</p>
    </div>

    <h2>Mudança média de aptidão por segmento</h2>
    <p class="note">ΔS médio sobre a terra avaliada de GO e DF, nos quatro cenários.</p>
    <PlotlyChart
      :data="shiftMeanData"
      :layout="{
        height: 320,
        barmode: 'group',
        yaxis: { title: { text: 'ΔS médio' }, zeroline: true },
        legend: { orientation: 'h', y: -0.25 },
      }"
    />
    <DataTable :columns="meanColumns" :rows="meanRows" />

    <h2>Terra apta e rebaixamento de classe — {{ scenarioText }}</h2>
    <p class="note">
      Terra apta = classe S2 ou melhor (S ≥ {{ fmtNum(s2Break, 2) }}), em parcela da terra avaliada.
      Células rebaixadas = parcela que desce ao menos uma classe FAO.
      <template v-if="worstLoss && worstLoss.pp < 0">
        A maior perda de terra apta neste cenário é a de
        <strong>{{ segmentLabel(worstLoss.segment).toLowerCase() }}</strong>
        ({{ fmtShare(worstLoss.present) }} → {{ fmtShare(worstLoss.future) }}; {{ fmtPp(worstLoss.pp) }}).
      </template>
    </p>
    <PlotlyChart
      :data="shareData"
      :layout="{
        height: 360,
        margin: { l: 170 },
        yaxis: { dtick: 1 },
        xaxis: { title: { text: 'terra apta (% da terra avaliada)' }, ticksuffix: '%' },
        legend: { orientation: 'h', y: -0.25 },
      }"
    />
    <DataTable :columns="shareColumns" :rows="shareRows" />

    <h2>Mudança média por zona — {{ scenarioText }}</h2>
    <PlotlyChart
      v-if="zoneShiftSegments.length"
      :data="zoneShiftData"
      :layout="{ height: 80 + zones.length * 60, margin: { l: 300 } }"
    />
    <p v-else class="note">A decomposição por zona não foi calculada para este cenário.</p>

    <h2>Transições de classe — outras culturas anuais ({{ transitionScenario }})</h2>
    <p class="note">
      Parcela da terra avaliada em cada par de classes FAO presente → futuro.
      {{ fmtNum(transitionSummary.downgraded, 1) }}% da terra é rebaixada e
      {{ fmtNum(transitionSummary.upgraded, 1) }}% melhora de classe; a classe S1 passa de
      {{ fmtNum(transitionSummary.s1Present, 1) }}% para {{ fmtNum(transitionSummary.s1Future, 1) }}%.
    </p>
    <PlotlyChart :data="transitionData" :layout="{ height: 320, yaxis: { autorange: 'reversed' } }" />
  </section>
</template>

<style scoped>
.map-row {
  margin-block: var(--space-3);
}

.note {
  color: var(--color-muted);
  font-size: 0.875rem;
  max-width: 80ch;
}
</style>
