<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed } from 'vue'
import type { ZoneProfileRow } from '../types/data'
import PlotlyChart from './PlotlyChart.vue'

const props = defineProps<{
  profile: ZoneProfileRow
  segments: string[]
  labels: Record<string, string>
  totalN: number
}>()

const territoryShare = computed(() => (100 * props.profile.n) / props.totalN)

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
      comparativa: <strong>{{ labels[profile.comparative_segment] ?? profile.comparative_segment }}</strong>
      &middot; {{ territoryShare.toFixed(1) }}% do território ({{ profile.n }} células)
    </p>
    <PlotlyChart
      :data="barData"
      :layout="{ height: 220, xaxis: { title: { text: 'aptidão comparativa z-normalizada' } } }"
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
</style>
