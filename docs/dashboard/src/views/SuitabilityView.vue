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
import { faoClassLegend, suitabilityLegend } from '../legends'
import type {
  AhpMatrices,
  AhpWeightRow,
  FactorConfig,
  SegmentsConfig,
  SensitivitySummary,
} from '../types/data'

const route = useRoute()
const router = useRouter()

const { data: segmentsCfg } = useJson<SegmentsConfig>('json/segments.json')
const { data: ahp } = useJson<AhpMatrices>('json/ahp_matrices.json')
const { data: ahpWeights } = useCsv<AhpWeightRow>('csv/ahp_weights.csv')

const segmentOrder = computed(() => (segmentsCfg.value ? Object.keys(segmentsCfg.value.segments) : []))
const labels = computed<Record<string, string>>(() =>
  segmentsCfg.value
    ? Object.fromEntries(Object.entries(segmentsCfg.value.segments).map(([k, v]) => [k, v.label]))
    : {},
)

const selectedSegment = ref((route.params.segment as string) || 'soybean')
watch(selectedSegment, (seg) => router.replace({ name: 'suitability', params: { segment: seg } }))
watch(
  () => route.params.segment,
  (seg) => {
    if (typeof seg === 'string' && seg) selectedSegment.value = seg
  },
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

const aggregation = computed(() =>
  segmentsCfg.value?.segments[selectedSegment.value]?.aggregate === 'arithmetic'
    ? 'média aritmética ponderada (compensatória)'
    : 'média geométrica ponderada (fator limitante)',
)

const suitLegend = computed(() => suitabilityLegend(labels.value[selectedSegment.value] ?? selectedSegment.value))
const classLegend = computed(() => faoClassLegend())

// --- weight derivation panel ------------------------------------------------
// Three columns, not one: the literature prior (w_lit), the regional
// discriminating power (d = sigma(mu)), and the weight that results from
// w = normalize(w_lit * d^lambda). Showing only the final weight is what let the
// earlier version present a derived number as if it were an elicited one.
const ahpSegment = computed(() => ahp.value?.segments[selectedSegment.value] ?? null)

const weightRows = computed<AhpWeightRow[]>(() =>
  (ahpWeights.value ?? []).filter((r) => r.segment === selectedSegment.value),
)

const ahpBarData = computed<PlotlyDatum[]>(() => {
  const rows = [...weightRows.value].reverse()
  if (rows.length === 0) return []
  const y = rows.map((r) => r.factor)
  return [
    { type: 'bar', orientation: 'h', name: 'w_lit (literatura)', x: rows.map((r) => r.w_lit), y },
    { type: 'bar', orientation: 'h', name: 'd = σ(μ)', x: rows.map((r) => r.d), y },
    { type: 'bar', orientation: 'h', name: 'w final', x: rows.map((r) => r.w_final), y },
  ]
})

const sensitivityDelta = computed(() => segmentsCfg.value?.aggregation.sensitivity_delta ?? 0.2)
const lambdaRegional = computed(() => segmentsCfg.value?.aggregation.lambda_regional ?? 0.5)

const ahpTitle = computed(() => {
  const d = ahpSegment.value?.derived
  if (!d) return 'Derivação dos pesos'
  return `Derivação dos pesos — RC=${d.consistency_ratio.toFixed(3)}, `
    + `fração ancorada ${(d.anchored_fraction * 100).toFixed(0)}%, λ=${lambdaRegional.value}`
})

const selectedFactorCfg = computed<FactorConfig | undefined>(() => factors.value[selectedFactor.value])

// --- Membership curve --------------------------------------------------------
function membership(type: FactorConfig['type'], points: number[], x: number): number {
  const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
  if (type === 'increasing') {
    const [a, b] = points as [number, number]
    return clamp01((x - a) / (b - a))
  }
  if (type === 'decreasing') {
    const [a, b] = points as [number, number]
    return clamp01((b - x) / (b - a))
  }
  // range: [a, b, c, d] — ramp up a->b, plateau, ramp down c->d
  // NB: this mirrors src/membership.py. A `gate` factor uses the same shapes; it
  // differs only in how it is combined (multiplicative, no weight).
  const [a, b, c, d] = points as [number, number, number, number]
  if (x <= a || x >= d) return 0
  if (x < b) return clamp01((x - a) / (b - a))
  if (x <= c) return 1
  return clamp01((d - x) / (d - c))
}

const membershipCurve = computed<PlotlyDatum[]>(() => {
  const cfg = factors.value[selectedFactor.value]
  if (!cfg) return []
  const [lo, hi] = [cfg.points[0] ?? 0, cfg.points[cfg.points.length - 1] ?? 1]
  const pad = (hi - lo) * 0.15 || 1
  const n = 100
  const xs = Array.from({ length: n }, (_, i) => lo - pad + ((hi - lo + 2 * pad) * i) / (n - 1))
  const ys = xs.map((x) => membership(cfg.type, cfg.points, x))
  return [{ type: 'scatter', mode: 'lines', x: xs, y: ys, line: { color: '#3f7d3a' } }]
})

// --- Sensitivity range (percentiles, not a full histogram) -------------------
const { data: sensitivity } = useJson<SensitivitySummary>(
  () => `json/sensitivity_${selectedSegment.value}.json`,
)
const sensitivityBox = computed<PlotlyDatum[]>(() => {
  const s = sensitivity.value
  if (!s) return []
  return [
    {
      type: 'box',
      name: 'Smax - Smin',
      q1: [s.p25],
      median: [s.p50],
      q3: [s.p75],
      lowerfence: [s.p5],
      upperfence: [s.p95],
      orientation: 'h',
    } as PlotlyDatum,
  ]
})
</script>

<template>
  <section>
    <h1>Modelagem de Viabilidade</h1>
    <p>
      Viabilidade baseada em conhecimento, com pertinência fuzzy + AHP (Parte 9). Cada
      fator é padronizado para [0,1] por uma função de pertinência e então combinado
      pela {{ aggregation }}.
    </p>

    <SegmentSelector v-model="selectedSegment" :segments="segmentOrder" :labels="labels" />

    <div class="map-row">
      <MapPanel :raster-path="`suit_${selectedSegment}.pmtiles`">
        <template #legend><MapLegend :spec="suitLegend" /></template>
      </MapPanel>
      <MapPanel :raster-path="`class_${selectedSegment}.pmtiles`">
        <template #legend><MapLegend :spec="classLegend" /></template>
      </MapPanel>
    </div>

    <div class="chart-row">
      <div>
        <h2>{{ ahpTitle }}</h2>
        <PlotlyChart
          :data="ahpBarData"
          :layout="{ height: 300, barmode: 'group', legend: { orientation: 'h', y: -0.18 } }"
        />
      </div>
      <div>
        <h2>Pertinência fuzzy</h2>
        <select v-model="selectedFactor">
          <option v-for="f in factorOrder" :key="f" :value="f">{{ f }}</option>
        </select>
        <PlotlyChart
          :data="membershipCurve"
          :layout="{ height: 220, yaxis: { title: { text: 'pertinência μ(x)' }, range: [0, 1] } }"
        />
        <p v-if="selectedFactorCfg" class="factor-ref">
          <span class="badge">{{ selectedFactorCfg.role === 'gate' ? 'porta' : 'limitante' }}</span>
          <span class="badge">limiares: {{ selectedFactorCfg.basis }}</span>
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

    <h2>Sensibilidade (perturbação AHP de ±{{ (sensitivityDelta * 100).toFixed(0) }}%)</h2>
    <PlotlyChart :data="sensitivityBox" :layout="{ height: 160 }" />
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

@media (max-width: 720px) {
  .map-row,
  .chart-row {
    grid-template-columns: 1fr;
  }
}
</style>
