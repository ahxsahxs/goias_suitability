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

const realizedFracs = computed(() =>
  (['soybean', 'sugarcane', 'other_crops', 'pasture', 'native'] as const)
    .map((role) => ({ role, frac: Number(props.profile[`rl_${role}_frac`] ?? 0) }))
    .filter((r) => r.frac > 0)
    .sort((a, b) => b.frac - a.frac),
)
</script>

<template>
  <div class="zone-card">
    <h3>Zone {{ profile.zone }}</h3>
    <p class="zone-meta">
      comparative: <strong>{{ labels[profile.comparative_segment] ?? profile.comparative_segment }}</strong>
      &middot; {{ territoryShare.toFixed(1) }}% of territory ({{ profile.n }} cells)
    </p>
    <PlotlyChart
      :data="barData"
      :layout="{ height: 220, xaxis: { title: { text: 'z-normalized comparative suitability' } } }"
    />
    <p class="zone-realized">
      Realized composition:
      <span v-for="r in realizedFracs" :key="r.role">
        {{ (100 * r.frac).toFixed(0) }}% {{ r.role }}&nbsp;
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
