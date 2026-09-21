<script setup lang="ts">
import { computed } from 'vue'
import type { LegendSpec } from '../types/legend'

const props = defineProps<{ spec: LegendSpec }>()

const defaultFormat = (v: number): string => (Number.isInteger(v) ? String(v) : v.toFixed(2))

const gradientCss = computed(() => {
  if (props.spec.kind !== 'gradient') return ''
  const { stops } = props.spec
  if (stops.length === 0) return ''
  const lo = stops[0]![0]
  const hi = stops[stops.length - 1]![0]
  const span = hi - lo || 1
  const parts = stops.map(([v, color]) => `${color} ${(100 * (v - lo)) / span}%`)
  return `linear-gradient(to right, ${parts.join(', ')})`
})

const gradientTicks = computed(() => {
  if (props.spec.kind !== 'gradient') return []
  const { stops, format } = props.spec
  const fmt = format ?? defaultFormat
  // First, middle (if 3+ stops), and last — avoids a crowded axis for 5-stop ramps.
  const picks = stops.length <= 2 ? stops : [stops[0]!, stops[Math.floor((stops.length - 1) / 2)]!, stops[stops.length - 1]!]
  const seen = new Set<number>()
  return picks.filter((s) => (seen.has(s[0]) ? false : (seen.add(s[0]), true))).map(([v]) => fmt(v))
})
</script>

<template>
  <div class="map-legend">
    <p class="map-legend-title">{{ spec.title }}</p>

    <div v-if="spec.kind === 'gradient'" class="map-legend-gradient">
      <div class="map-legend-bar" :style="{ background: gradientCss }" />
      <div class="map-legend-ticks">
        <span v-for="(t, i) in gradientTicks" :key="i">{{ t }}</span>
      </div>
    </div>

    <ul v-else class="map-legend-swatches">
      <li v-for="item in spec.items" :key="item.label">
        <span class="map-legend-swatch" :style="{ background: item.color }" />
        {{ item.label }}
      </li>
    </ul>

    <p v-if="spec.caption" class="map-legend-caption">{{ spec.caption }}</p>
  </div>
</template>

<style scoped>
.map-legend {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  font-size: 0.8rem;
}

.map-legend-title {
  margin: 0 0 var(--space-2);
  font-weight: 600;
}

.map-legend-gradient {
  max-width: 320px;
}

.map-legend-bar {
  height: 12px;
  border-radius: 3px;
  border: 1px solid var(--color-border);
}

.map-legend-ticks {
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-1);
  color: var(--color-muted);
  font-size: 0.75rem;
}

.map-legend-swatches {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-3);
}

.map-legend-swatches li {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  white-space: nowrap;
}

.map-legend-swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 2px;
  border: 1px solid var(--color-border);
  flex-shrink: 0;
}

.map-legend-caption {
  margin: var(--space-2) 0 0;
  color: var(--color-muted);
  font-size: 0.75rem;
}
</style>
