<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import SegmentSelector from '../components/SegmentSelector.vue'
import { useJson } from '../composables/useJson'
import type { AhpMatrices, FactorConfig, SegmentsConfig, SensitivitySummary } from '../types/data'

const route = useRoute()
const router = useRouter()

const { data: segmentsCfg } = useJson<SegmentsConfig>('json/segments.json')
const { data: ahp } = useJson<AhpMatrices>('json/ahp_matrices.json')

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
    ? 'weighted arithmetic mean (compensatory)'
    : 'weighted geometric mean (limiting-factor)',
)

// --- AHP weights bar --------------------------------------------------------
const ahpSegment = computed(() => ahp.value?.segments[selectedSegment.value] ?? null)
const ahpBarData = computed<PlotlyDatum[]>(() => {
  const seg = ahpSegment.value
  if (!seg) return []
  return [{ type: 'bar', orientation: 'h', x: [...seg.config_weights].reverse(), y: [...seg.factors].reverse() }]
})
const ahpTitle = computed(() => {
  const cr = ahpSegment.value?.consistency_ratio
  return cr === undefined ? 'AHP weights' : `AHP weights (CR=${cr.toFixed(4)})`
})

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
    <h1>Suitability Modelling</h1>
    <p>
      Fuzzy-membership + AHP knowledge-based suitability (Part 9). Each factor is
      standardized to [0,1] by a membership function, then combined by the
      {{ aggregation }}.
    </p>

    <SegmentSelector v-model="selectedSegment" :segments="segmentOrder" :labels="labels" />

    <div class="map-row">
      <MapPanel :raster-path="`suit_${selectedSegment}.pmtiles`">
        <template #legend>Suitability (0-1, red -&gt; green)</template>
      </MapPanel>
      <MapPanel :raster-path="`class_${selectedSegment}.pmtiles`">
        <template #legend>FAO class (N / S3 / S2 / S1)</template>
      </MapPanel>
    </div>

    <div class="chart-row">
      <div>
        <h2>{{ ahpTitle }}</h2>
        <PlotlyChart :data="ahpBarData" :layout="{ height: 260, margin: { l: 140 } }" />
      </div>
      <div>
        <h2>Fuzzy membership</h2>
        <select v-model="selectedFactor">
          <option v-for="f in factorOrder" :key="f" :value="f">{{ f }}</option>
        </select>
        <PlotlyChart
          :data="membershipCurve"
          :layout="{ height: 220, yaxis: { title: { text: 'membership μ(x)' }, range: [0, 1] } }"
        />
        <p v-if="factors[selectedFactor]" class="factor-ref">{{ factors[selectedFactor]?.ref }}</p>
      </div>
    </div>

    <h2>Sensitivity (±20% AHP perturbation)</h2>
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
