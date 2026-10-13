<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed } from 'vue'
import type { ZoneProfileRow } from '../types/data'
import PlotlyChart from './PlotlyChart.vue'

const props = defineProps<{
  profile: ZoneProfileRow
  segments: string[]
  labels: Record<string, string>
  /**
   * Share of the AOI this zone covers, from csv/zone_area.csv (a pixelArea()
   * group reduce). Passed in rather than derived here: this card used to compute
   * it as profile.n / totalN, but `n` counts rows of a stratified sample, which
   * put zone 1 at 37.9% of the territory when its area share is 46.4% and zone 3
   * at 22.7% when it is 15.2%. See CLAUDE.md §9.
   */
  areaShare: number
}>()

// Below this z-gap between a zone's first and second comparative segment, both are
// shown: the rule §sec:zoning-results states in prose, and the same threshold
// tools/make_figures.py carries as ZONE_PAIR_MARGIN for fig_4_3's legend. Keep the
// two in step -- they are two surfaces of one editorial rule.
const ZONE_PAIR_MARGIN = 0.25

const segLabel = (s: string) => props.labels[s] ?? s
const showsPair = computed(() => props.profile.comparative_margin < ZONE_PAIR_MARGIN)
const vocation = computed(() =>
  showsPair.value
    ? `${segLabel(props.profile.comparative_segment)} / ${segLabel(props.profile.comparative_segment_2)}`
    : segLabel(props.profile.comparative_segment),
)

const barData = computed<PlotlyDatum[]>(() => [
  {
    type: 'bar',
    orientation: 'h',
    x: props.segments.map((s) => Number(props.profile[`rel_suit_${s}`] ?? 0)),
    y: props.segments.map((s) => props.labels[s] ?? s),
  },
])

const REALIZED_ROLE_LABELS_PT: Record<string, string> = {
  soybean: 'soja',
  sugarcane: 'cana-de-açúcar',
  other_crops: 'outras culturas',
  pasture: 'pastagem',
  native: 'vegetação nativa',
}

const realizedFracs = computed(() =>
  (['soybean', 'sugarcane', 'other_crops', 'pasture', 'native'] as const)
    .map((role) => ({ role, frac: Number(props.profile[`rl_${role}_frac`] ?? 0) }))
    .filter((r) => r.frac > 0)
    .sort((a, b) => b.frac - a.frac),
)
</script>

<template>
  <div class="zone-card">
    <h3>Zona {{ profile.zone }}</h3>
    <p class="zone-meta">
      comparativa: <strong>{{ vocation }}</strong>
      (margem {{ profile.comparative_margin.toFixed(2).replace('.', ',') }})
      &middot; {{ areaShare.toFixed(1).replace('.', ',') }}% do território
      &middot; {{ profile.n }} células na amostra
    </p>
    <p v-if="showsPair" class="zone-note">
      A margem entre os dois primeiros segmentos é estreita: a zona é melhor lida pelo par do que
      por um rótulo único.
    </p>
    <PlotlyChart
      :data="barData"
      :layout="{
        height: 220,
        xaxis: { title: { text: 'viabilidade relativa (desvio da média dos sete segmentos)' } },
      }"
    />
    <p class="zone-realized">
      Composição realizada:
      <span v-for="r in realizedFracs" :key="r.role">
        {{ (100 * r.frac).toFixed(0) }}% {{ REALIZED_ROLE_LABELS_PT[r.role] ?? r.role }}&nbsp;
      </span>
    </p>
  </div>
</template>

<style scoped>
.zone-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: var(--space-3);
  background: var(--color-surface);
}

.zone-meta {
  color: var(--color-muted);
  font-size: 0.875rem;
}

.zone-realized {
  font-size: 0.8rem;
  color: var(--color-muted);
}

.zone-note {
  font-size: 0.8rem;
  color: var(--color-muted);
  font-style: italic;
}
</style>
