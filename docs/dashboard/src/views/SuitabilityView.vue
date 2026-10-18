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
import { useJson } from '../composables/useJson'
import { useManifest } from '../composables/useManifest'
import { fmtNum, fmtShare } from '../format'
import { faoClassLegend, suitabilityLegend } from '../legends'
import type {
  AhpMatrices,
  AhpWeightRow,
  FactorConfig,
  FactorDiscriminationRow,
  FactorVarianceRow,
  FactorVarianceThemeRow,
  LambdaAucRow,
  LambdaSweepRow,
  SegmentsConfig,
  SensitivitySummary,
} from '../types/data'

const route = useRoute()
const router = useRouter()

const { manifest, segmentKeys, segmentLabels, segmentLabel, bandLabel } = useManifest()
const { data: segmentsCfg } = useJson<SegmentsConfig>('json/segments.json')
const { data: ahp } = useJson<AhpMatrices>('json/ahp_matrices.json')
const { data: ahpWeights } = useCsv<AhpWeightRow>('csv/ahp_weights.csv')
const { data: discrimination } = useCsv<FactorDiscriminationRow>('csv/factor_discrimination.csv')
const { data: lambdaSweep } = useCsv<LambdaSweepRow>('csv/lambda_sweep.csv')
const { data: lambdaAuc } = useCsv<LambdaAucRow>('csv/lambda_auc.csv')

const selectedSegment = ref((route.params.segment as string) || 'soybean')
watch(selectedSegment, (seg) => router.replace({ name: 'suitability', params: { segment: seg } }))
watch(
  () => route.params.segment,
  (seg) => {
    if (typeof seg === 'string' && seg) selectedSegment.value = seg
  },
)
const segName = computed(() => segmentLabel(selectedSegment.value))

const agg = computed(() => segmentsCfg.value?.aggregation ?? null)
const derivedHalf = computed(() => agg.value?.derived_half ?? 'calib')
const halfLabel = computed(() =>
  derivedHalf.value === 'calib' ? 'metade de calibração' : derivedHalf.value === 'val' ? 'metade de validação' : 'território inteiro',
)

const factors = computed<Record<string, FactorConfig>>(
  () => segmentsCfg.value?.segments[selectedSegment.value]?.factors ?? {},
)
const factorOrder = computed(() => Object.keys(factors.value))
const selectedFactor = ref('')
watch(
  factorOrder,
  (fs) => {
    if (fs.length > 0 && !fs.includes(selectedFactor.value)) selectedFactor.value = fs[0] ?? ''
  },
  { immediate: true },
)

const isArithmetic = computed(() => segmentsCfg.value?.segments[selectedSegment.value]?.aggregate === 'arithmetic')

const suitLegend = computed(() => suitabilityLegend(segName.value))
const classLegend = computed(() =>
  manifest.value ? faoClassLegend(manifest.value.fao_classes, manifest.value.fao_breaks) : null,
)

// --- weight derivation ----------------------------------------------------------
// Three columns, not one: the literature prior (w_lit), the regional discriminating
// power (σ(μ)), and the weight w = normalize(w_lit · σ(μ)^λ). Showing only the final
// weight would present a derived number as if it were an elicited one.
const ahpSegment = computed(() => ahp.value?.segments[selectedSegment.value] ?? null)
const weightRows = computed<AhpWeightRow[]>(() =>
  (ahpWeights.value ?? []).filter((r) => r.segment === selectedSegment.value),
)
const ahpBarData = computed<PlotlyDatum[]>(() => {
  const rows = [...weightRows.value].reverse()
  if (rows.length === 0) return []
  const y = rows.map((r) => bandLabel(r.factor))
  return [
    { type: 'bar', orientation: 'h', name: 'prioridade da literatura (w lit)', x: rows.map((r) => r.w_lit), y },
    { type: 'bar', orientation: 'h', name: 'poder discriminante σ(μ)', x: rows.map((r) => r.d), y },
    { type: 'bar', orientation: 'h', name: 'peso final (w)', x: rows.map((r) => r.w_final), y },
  ]
})

// --- membership curve -------------------------------------------------------------
// Mirrors src/membership.py: increasing [a,b], decreasing [a,b], range [a,b,c,d].
function membership(type: FactorConfig['type'], points: number[], x: number): number {
  const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
  if (type === 'increasing') {
    const [a, b] = points as [number, number]
    return clamp01((x - a) / (b - a))
  }
  if (type === 'decreasing') {
    const [a, b] = points as [number, number]
    return clamp01((b - x) / (b - a))
  }
  const [a, b, c, d] = points as [number, number, number, number]
  if (x <= a || x >= d) return 0
  if (x < b) return clamp01((x - a) / (b - a))
  if (x <= c) return 1
  return clamp01((d - x) / (d - c))
}
const selectedFactorCfg = computed<FactorConfig | undefined>(() => factors.value[selectedFactor.value])
const membershipCurve = computed<PlotlyDatum[]>(() => {
  const cfg = selectedFactorCfg.value
  if (!cfg) return []
  const [lo, hi] = [cfg.points[0] ?? 0, cfg.points[cfg.points.length - 1] ?? 1]
  const pad = (hi - lo) * 0.15 || 1
  const n = 100
  const xs = Array.from({ length: n }, (_, i) => lo - pad + ((hi - lo + 2 * pad) * i) / (n - 1))
  return [{ type: 'scatter', mode: 'lines', x: xs, y: xs.map((x) => membership(cfg.type, cfg.points, x)), line: { color: '#3f7d3a' } }]
})
const basisLabel = (b: string | undefined) => (b === 'literatura' ? 'limiares da literatura' : 'limiares empíricos')

// --- discrimination ---------------------------------------------------------------
interface DiscRow {
  factor: string
  label: string
  type: string
  anchor: string
  weight: number
  sigma_now: number
  sigma_horizon: number
  saturated: number
  vetoed: number
}
const discRows = computed<DiscRow[]>(() => {
  const m = manifest.value
  return (discrimination.value ?? [])
    .filter((r) => r.segment === selectedSegment.value && r.half === derivedHalf.value)
    .map((r) => {
      const cfg = factors.value[r.factor]
      return {
        factor: r.factor,
        label: bandLabel(r.factor),
        type: m?.membership_types[r.type] ?? r.type,
        anchor: cfg?.anchor ? (m?.anchor_rules[cfg.anchor.rule] ?? cfg.anchor.rule) : '—',
        weight: cfg?.weight ?? Number.NaN,
        sigma_now: r.sigma_mu_available,
        sigma_horizon: r.sigma_mu_horizon,
        saturated: r.frac_saturated,
        vetoed: r.frac_vetoed,
      }
    })
    .sort((a, b) => b.weight - a.weight)
})
const discColumns: DataTableColumn<DiscRow>[] = [
  { key: 'label', label: 'Fator' },
  { key: 'type', label: 'Pertinência' },
  { key: 'anchor', label: 'Ancoragem dos limiares' },
  { key: 'weight', label: 'Peso final', format: (r) => fmtNum(r.weight, 3) },
  { key: 'sigma_now', label: 'σ(μ) presente', format: (r) => fmtNum(r.sigma_now, 3) },
  { key: 'sigma_horizon', label: 'σ(μ) presente + horizonte', format: (r) => fmtNum(r.sigma_horizon, 3) },
  { key: 'saturated', label: 'Fração com μ = 1', format: (r) => fmtShare(r.saturated) },
  { key: 'vetoed', label: 'Fração com μ = 0', format: (r) => fmtShare(r.vetoed) },
]
const nullWeights = computed(() => discRows.value.filter((r) => r.weight === 0))
const nullBySaturation = computed(() => nullWeights.value.filter((r) => r.sigma_horizon === 0).length)

// --- λ sensitivity ----------------------------------------------------------------
const lambdaAdopted = computed(() => agg.value?.lambda_regional ?? null)
const sweepData = computed<PlotlyDatum[]>(() => {
  const rows = (lambdaSweep.value ?? []).filter(
    (r) => r.segment === selectedSegment.value && r.half === derivedHalf.value,
  )
  const byFactor = new Map<string, LambdaSweepRow[]>()
  rows.forEach((r) => byFactor.set(r.factor, [...(byFactor.get(r.factor) ?? []), r]))
  return [...byFactor.entries()].map(([factor, rs]) => {
    const sorted = rs.sort((a, b) => a.lambda - b.lambda)
    return {
      type: 'scatter',
      mode: 'lines+markers',
      name: bandLabel(factor),
      x: sorted.map((r) => r.lambda),
      y: sorted.map((r) => r.weight),
    } as PlotlyDatum
  })
})
const aucRows = computed(() =>
  (lambdaAuc.value ?? []).filter((r) => r.segment === selectedSegment.value).sort((a, b) => a.lambda - b.lambda),
)
const aucData = computed<PlotlyDatum[]>(() =>
  aucRows.value.length
    ? [{ type: 'scatter', mode: 'lines+markers', name: 'AUC', x: aucRows.value.map((r) => r.lambda), y: aucRows.value.map((r) => r.auc) }]
    : [],
)
const lambdaLine = computed(() =>
  lambdaAdopted.value === null
    ? []
    : [{
        type: 'line' as const, x0: lambdaAdopted.value, x1: lambdaAdopted.value, yref: 'paper' as const, y0: 0, y1: 1,
        line: { color: '#d7191c', width: 1, dash: 'dash' as const },
      }],
)

// --- climate vs soil/terrain (§sec:atlas-present, anx factor variance) ------------------
// raw_* = grouped by the factor's ORIGIN (clim_* = climatic), the reading the thesis
// uses ("fatores de origem climática"); soil moisture therefore counts as climate.
const { data: varTheme } = useCsv<FactorVarianceThemeRow>('csv/factor_variance_theme.csv')
const { data: varFactor } = useCsv<FactorVarianceRow>('csv/factor_variance.csv')
const varThemeData = computed<PlotlyDatum[]>(() => {
  const rows = [...(varTheme.value ?? [])].sort(
    (a, b) => segmentKeys.value.indexOf(b.segment) - segmentKeys.value.indexOf(a.segment),
  )
  const y = rows.map((r) => segmentLabel(r.segment))
  const clip = (v: number) => Math.max(0, v)
  return [
    { type: 'bar', orientation: 'h', name: 'clima', x: rows.map((r) => clip(r.raw_climate)), y, marker: { color: '#E69F00' } },
    { type: 'bar', orientation: 'h', name: 'solo e terreno', x: rows.map((r) => clip(r.raw_terrain_soil)), y, marker: { color: '#009E73' } },
    { type: 'bar', orientation: 'h', name: 'água, localização e conservação', x: rows.map((r) => clip(r.raw_other)), y, marker: { color: '#0072B2' } },
  ]
})
const varFactorRows = computed(() =>
  (varFactor.value ?? []).filter((r) => r.segment === selectedSegment.value).sort((a, b) => b.variance_share - a.variance_share),
)
const varFactorData = computed<PlotlyDatum[]>(() => [
  {
    type: 'bar',
    orientation: 'h',
    x: [...varFactorRows.value].reverse().map((r) => r.variance_share),
    y: [...varFactorRows.value].reverse().map((r) => bandLabel(r.factor)),
    text: [...varFactorRows.value].reverse().map((r) => fmtShare(r.variance_share, 0)),
    textposition: 'auto',
  },
])
const topFactor = computed(() => varFactorRows.value[0] ?? null)

// --- robustness band ---------------------------------------------------------------
const { data: sensitivity } = useJson<SensitivitySummary>(() => `json/sensitivity_${selectedSegment.value}.json`)
const sensitivityBox = computed<PlotlyDatum[]>(() => {
  const s = sensitivity.value
  if (!s) return []
  return [
    {
      type: 'box',
      name: '',
      q1: [s.p25],
      median: [s.p50],
      q3: [s.p75],
      lowerfence: [s.p5],
      upperfence: [s.p95],
      orientation: 'h',
      hoverinfo: 'x',
    } as PlotlyDatum,
  ]
})
</script>

<template>
  <section>
    <h1>Aptidão do presente</h1>
    <p>
      A aptidão é avaliada por conhecimento especialista, segmento a segmento. Cada fator é
      padronizado em [0,&nbsp;1] por uma função de pertinência <em>fuzzy</em> e os fatores são
      combinados pela média geométrica ponderada (regra de fator limitante); a conservação, por
      ser um índice de valor, usa a média aritmética ponderada (compensatória). A aptidão contínua
      é classificada nas classes FAO S1, S2, S3 e N.
    </p>

    <SegmentSelector v-model="selectedSegment" :segments="segmentKeys" :labels="segmentLabels" />
    <p class="note">
      Agregação de <strong>{{ segName }}</strong>:
      {{ isArithmetic ? 'média aritmética ponderada (compensatória)' : 'média geométrica ponderada (fator limitante)' }}.
    </p>

    <div class="map-row">
      <MapPanel :raster-path="`suit_${selectedSegment}.pmtiles`">
        <template #legend><MapLegend :spec="suitLegend" /></template>
      </MapPanel>
      <MapPanel :raster-path="`class_${selectedSegment}.pmtiles`">
        <template #legend><MapLegend v-if="classLegend" :spec="classLegend" /></template>
      </MapPanel>
    </div>

    <div class="chart-row">
      <div>
        <h2>Ponderação AHP com adaptação regional</h2>
        <p class="note">
          w = normalização(w<sub>lit</sub> · σ(μ)<sup>λ</sup>), com λ = {{ fmtNum(lambdaAdopted, 2) }}
          fixado a priori e σ(μ) medido na terra disponível da {{ halfLabel }}.
          <template v-if="ahpSegment">
            Razão de consistência da matriz de comparação:
            RC = {{ fmtNum(ahpSegment.derived.consistency_ratio, 4) }}
            (limite {{ fmtNum(ahp?.scale.cr_threshold, 2) }}).
          </template>
        </p>
        <PlotlyChart
          :data="ahpBarData"
          :layout="{ height: 140 + weightRows.length * 60, barmode: 'group', margin: { l: 200 }, yaxis: { dtick: 1 }, legend: { orientation: 'h', y: -0.15 } }"
        />
      </div>
      <div>
        <h2>Função de pertinência</h2>
        <label class="field">
          Fator:
          <select v-model="selectedFactor">
            <option v-for="f in factorOrder" :key="f" :value="f">{{ bandLabel(f) }}</option>
          </select>
        </label>
        <PlotlyChart
          :data="membershipCurve"
          :layout="{
            height: 220,
            xaxis: { title: { text: bandLabel(selectedFactor) } },
            yaxis: { title: { text: 'pertinência μ' }, range: [0, 1.05] },
          }"
        />
        <p v-if="selectedFactorCfg" class="factor-ref">
          <span class="badge">{{ manifest?.membership_types[selectedFactorCfg.type] ?? selectedFactorCfg.type }}</span>
          <span class="badge">{{ basisLabel(selectedFactorCfg.basis) }}</span>
          <span v-if="selectedFactorCfg.anchor" class="badge">
            {{ manifest?.anchor_rules[selectedFactorCfg.anchor.rule] ?? selectedFactorCfg.anchor.rule }}
          </span>
          {{ selectedFactorCfg.note }}
          <template v-if="selectedFactorCfg.source">
            <em>
              Fonte: {{ selectedFactorCfg.source
              }}<template v-if="selectedFactorCfg.locator">, {{ selectedFactorCfg.locator }}</template>.
            </em>
          </template>
        </p>
      </div>
    </div>

    <h2>Discriminação dos fatores</h2>
    <p class="note">
      Um fator só diferencia o território se a sua pertinência varia. σ(μ) é o desvio-padrão da
      pertinência na terra disponível da {{ halfLabel }}, no presente e no presente somado ao
      horizonte CMIP6 mais quente; um fator saturado (μ = 1) hoje ainda recebe peso se o clima
      projetado o tirar do patamar ótimo.
      <template v-if="nullWeights.length">
        Em {{ segName.toLowerCase() }}, {{ nullWeights.length }}
        {{ nullWeights.length === 1 ? 'fator tem' : 'fatores têm' }} peso nulo<template v-if="nullBySaturation"
          >, {{ nullBySaturation === nullWeights.length ? 'todos' : nullBySaturation }} por μ ≡ 1 no presente e no
          horizonte</template
        >.
      </template>
    </p>
    <DataTable v-if="discRows.length" :columns="discColumns" :rows="discRows" />

    <h2>Sensibilidade ao expoente λ</h2>
    <div class="chart-row">
      <div>
        <PlotlyChart
          :data="sweepData"
          :layout="{
            height: 280,
            xaxis: { title: { text: 'λ' } },
            yaxis: { title: { text: 'peso final' } },
            shapes: lambdaLine,
            legend: { orientation: 'h', y: -0.3 },
          }"
        />
      </div>
      <div v-if="aucData.length">
        <PlotlyChart
          :data="aucData"
          :layout="{
            height: 280,
            xaxis: { title: { text: 'λ' } },
            yaxis: { title: { text: 'AUC de presença (metade de validação)' } },
            shapes: lambdaLine,
          }"
        />
      </div>
      <p v-else class="note">
        A AUC em função de λ só é calculada para os segmentos com validador de presença.
      </p>
    </div>

    <h2>Clima versus solo e terreno</h2>
    <p class="note">
      Parcela da variância espacial da aptidão atribuída a cada grupo de fatores, por segmento
      (fatores agrupados pela origem: a umidade do solo, derivada do balanço hídrico climático, conta
      como clima). Nos segmentos de cultivo, os fatores climáticos saturam e a estrutura espacial do
      atlas vem do solo e do terreno.
    </p>
    <PlotlyChart
      :data="varThemeData"
      :layout="{
        height: 380,
        barmode: 'stack',
        margin: { l: 160, b: 110 },
        xaxis: { title: { text: 'parcela da variância espacial' }, range: [0, 1.02], tickformat: '.0%' },
        yaxis: { dtick: 1 },
        legend: { orientation: 'h', y: -0.3 },
      }"
    />
    <p v-if="topFactor" class="note">
      Em {{ segName.toLowerCase() }}, o fator dominante é <strong>{{ bandLabel(topFactor.factor) }}</strong>,
      com {{ fmtShare(topFactor.variance_share, 0) }} da variância espacial.
    </p>
    <PlotlyChart
      :data="varFactorData"
      :layout="{ height: 100 + varFactorRows.length * 36, margin: { l: 220 }, yaxis: { dtick: 1 }, xaxis: { tickformat: '.0%', range: [0, 1.05], title: { text: 'parcela da variância espacial' } } }"
    />

    <h2>Faixa de robustez (perturbação de ±{{ fmtNum((agg?.sensitivity_delta ?? 0) * 100, 0) }}% nos pesos)</h2>
    <p class="note">
      Distribuição, no território, de S<sub>máx</sub> − S<sub>mín</sub>: a amplitude da aptidão de
      cada célula quando cada peso é perturbado isoladamente. Caixa = intervalo interquartil;
      bigodes = percentis 5 e 95.
    </p>
    <PlotlyChart :data="sensitivityBox" :layout="{ height: 160, xaxis: { title: { text: 'S máx − S mín' } } }" />
  </section>
</template>

<style scoped>
.map-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
  margin-block: var(--space-3);
}

.badge {
  display: inline-block;
  padding: 0.1em 0.5em;
  margin-right: 0.4em;
  border-radius: 0.5em;
  background: var(--surface-2, #e8e8e8);
  font-size: 0.85em;
}

.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
  margin-block: var(--space-4);
}

.factor-ref {
  font-size: 0.8rem;
  color: var(--color-muted);
}

.note {
  color: var(--color-muted);
  font-size: 0.875rem;
  max-width: 80ch;
}

.field {
  font-size: 0.875rem;
}

@media (max-width: 720px) {
  .map-row,
  .chart-row {
    grid-template-columns: 1fr;
  }
}
</style>
