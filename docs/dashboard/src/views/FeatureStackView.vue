<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref } from 'vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import { useJson } from '../composables/useJson'
import type { StackComposition } from '../types/data'

const { data: composition } = useJson<StackComposition>('json/stack_composition.json')

const mode = ref<'raw' | 'z'>('raw')

const chartData = computed<PlotlyDatum[]>(() => {
  const c = composition.value
  if (!c) return []
  const themes = Object.keys(c.themes)
  return [
    {
      type: 'bar',
      x: themes,
      y: themes.map((t) => c.themes[t] ?? 0),
      name: mode.value === 'raw' ? 'bandas brutas' : 'bandas padronizadas',
    },
  ]
})
</script>

<template>
  <section>
    <h1>Pilha de Atributos ({{ composition?.total_bands ?? 34 }} bandas)</h1>
    <p>
      Os seis STACK_THEMES contínuos se combinam em uma única imagem harmonizada de
      250 m (Parte 8). A cobertura da terra é deliberadamente excluída — apenas
      máscara/contexto, nunca empilhada ou agrupada.
    </p>

    <div class="mode-toggle" role="tablist">
      <button
        type="button"
        role="tab"
        :aria-selected="mode === 'raw'"
        :class="['mode-btn', { active: mode === 'raw' }]"
        @click="mode = 'raw'"
      >
        Bruto
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="mode === 'z'"
        :class="['mode-btn', { active: mode === 'z' }]"
        @click="mode = 'z'"
      >
        Padronizado (z-score)
      </button>
    </div>

    <PlotlyChart
      :data="chartData"
      :layout="{
        height: 320,
        xaxis: { title: { text: 'tema' } },
        yaxis: { title: { text: 'número de bandas' } },
        title: { text: mode === 'raw' ? 'feature_stack_250m' : 'feature_stack_250m_z' },
      }"
    />

    <p v-if="composition" class="note">{{ composition.note }}</p>
  </section>
</template>

<style scoped>
.mode-toggle {
  display: flex;
  gap: var(--space-2);
  margin-block: var(--space-3);
}

.mode-btn {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius);
  cursor: pointer;
  font: inherit;
}

.mode-btn.active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: white;
}

.note {
  color: var(--color-muted);
  font-size: 0.875rem;
}
</style>
