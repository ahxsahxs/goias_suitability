<script setup lang="ts">
import Plotly from 'plotly.js-dist-min'
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    data: Plotly.Data[]
    layout?: Partial<Plotly.Layout>
    config?: Partial<Plotly.Config>
  }>(),
  { layout: () => ({}), config: () => ({ displayModeBar: false, responsive: true }) },
)

const container = ref<HTMLDivElement | null>(null)

const BASE_LAYOUT: Partial<Plotly.Layout> = {
  margin: { t: 24, r: 16, b: 40, l: 48 },
  font: { family: 'system-ui, sans-serif', size: 12, color: '#1b1f1a' },
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  xaxis: { automargin: true },
  yaxis: { automargin: true },
}

function mergedLayout(): Partial<Plotly.Layout> {
  return {
    ...BASE_LAYOUT,
    ...props.layout,
    xaxis: { ...BASE_LAYOUT.xaxis, ...props.layout?.xaxis },
    yaxis: { ...BASE_LAYOUT.yaxis, ...props.layout?.yaxis },
  }
}

onMounted(() => {
  if (!container.value) return
  void Plotly.newPlot(container.value, props.data, mergedLayout(), props.config)
})

watch(
  () => [props.data, props.layout],
  () => {
    if (!container.value) return
    void Plotly.react(container.value, props.data, mergedLayout(), props.config)
  },
  { deep: true },
)

onUnmounted(() => {
  if (container.value) Plotly.purge(container.value)
})
</script>

<template>
  <div ref="container" class="plotly-chart" />
</template>

<style scoped>
.plotly-chart {
  width: 100%;
  min-height: 280px;
}
</style>
