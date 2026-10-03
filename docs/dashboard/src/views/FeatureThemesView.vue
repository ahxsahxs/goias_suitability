<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import { useJson } from '../composables/useJson'
import { continuousBandLegend } from '../legends'
import type { BandPercentiles } from '../types/data'

interface ThemeDef {
  key: string
  label: string
  band: string
  part: string
  /** In features.STACK_THEMES, i.e. part of the feature stack the zoning clusters. */
  stacked: boolean
}

// One representative ("hero") band per theme — mirrors HERO_BANDS in
// tools/build_dashboard_assets.py. The remaining ~30 bands per theme are not
// shipped as a PNG gallery in this pass (see docs/dashboard_ux_plan.md §9).
// `stacked` mirrors features.STACK_THEMES. Four of the eight themes are built but
// deliberately kept OUT of the stack, for two different reasons:
//   - siting / conservation: routed straight into suitability as `sit_`/`cv_` extras,
//     so they never enter the clustering input;
//   - phenology / access: removed on 2026-10-02 because both encode the CURRENT state
//     of land use and infrastructure — the same circularity argument that keeps land
//     cover out. They stay here as built artifacts of Parts 6 and 7, not as inputs.
const THEMES: ThemeDef[] = [
  { key: 'climate', label: 'Clima', band: 'clim_aridity', part: 'Parte 2', stacked: true },
  { key: 'terrain', label: 'Relevo', band: 'terr_slope', part: 'Parte 3', stacked: true },
  { key: 'soil', label: 'Solo', band: 'soil_clay', part: 'Parte 4', stacked: true },
  { key: 'water', label: 'Água', band: 'water_dist', part: 'Parte 5', stacked: true },
  { key: 'phenology', label: 'Fenologia', band: 'phen_amplitude', part: 'Parte 6', stacked: false },
  { key: 'access', label: 'Acesso a mercados', band: 'access_logtt', part: 'Parte 7', stacked: false },
  { key: 'siting', label: 'Localização (solar/piscicultura)', band: 'sit_clearness', part: 'Parte 7c', stacked: false },
  { key: 'conservation', label: 'Conservação', band: 'cv_pa_dist', part: 'Parte 7d', stacked: false },
]

const route = useRoute()
const router = useRouter()

const selectedTheme = ref((route.params.theme as string) || THEMES[0]!.key)
watch(selectedTheme, (theme) => router.replace({ name: 'feature-themes', params: { theme } }))
watch(
  () => route.params.theme,
  (theme) => {
    if (typeof theme === 'string' && theme) selectedTheme.value = theme
  },
)

const current = computed(() => THEMES.find((t) => t.key === selectedTheme.value) ?? THEMES[0]!)

const { data: percentiles } = useJson<BandPercentiles>('json/band_percentiles.json')
const currentPercentiles = computed(() => percentiles.value?.[current.value.band] ?? null)

const legend = computed(() => {
  const p = currentPercentiles.value
  const title = `${current.value.band} (${current.value.part})`
  return continuousBandLegend(title, p?.p5 ?? 0, p?.p95 ?? 1)
})

const histogramData = computed<PlotlyDatum[]>(() => {
  const p = currentPercentiles.value
  if (!p) return []
  return [
    {
      type: 'box',
      name: current.value.band,
      q1: [p.p25],
      median: [p.p50],
      q3: [p.p75],
      lowerfence: [p.p5],
      upperfence: [p.p95],
      orientation: 'h',
    } as PlotlyDatum,
  ]
})
</script>

<template>
  <section>
    <h1>Temas de Atributos</h1>
    <p>
      Oito temas biofísicos (Partes 2-7d) harmonizados na grade de análise de 250 m.
      A cobertura da terra (Parte 7b) é apenas uma máscara — nunca uma entrada de
      viabilidade ou de agrupamento.
    </p>
    <p class="note">
      Quatro destes temas <strong>não</strong> entram na pilha de atributos agrupada pelo
      zoneamento (marcados com <span class="off-stack inline">∘</span>). Localização e
      conservação vão diretamente à aptidão, como extras <code>sit_</code> e <code>cv_</code>.
      Fenologia e acessibilidade saíram da análise em 02/10/2026: ambas codificam o
      <em>estado atual</em> do uso da terra e da infraestrutura — o mesmo argumento de
      circularidade que mantém a cobertura da terra de fora. Permanecem aqui como
      artefactos construídos das Partes 6 e 7.
    </p>

    <div class="theme-strip">
      <button
        v-for="t in THEMES"
        :key="t.key"
        type="button"
        :class="['theme-btn', { active: t.key === selectedTheme }]"
        :title="t.stacked ? `${t.part} — na pilha` : `${t.part} — fora da pilha`"
        @click="selectedTheme = t.key"
      >
        {{ t.label }}<span v-if="!t.stacked" class="off-stack">&nbsp;∘</span>
      </button>
    </div>

    <MapPanel :raster-path="`feat_${current.band}.pmtiles`">
      <template #legend><MapLegend :spec="legend" /></template>
    </MapPanel>

    <h2>Faixa de percentis (P5 / P25 / P50 / P75 / P95)</h2>
    <PlotlyChart :data="histogramData" :layout="{ height: 160 }" />
  </section>
</template>

<style scoped>
/* Marks a theme that is built but NOT in features.STACK_THEMES. */
.off-stack {
  opacity: 0.6;
  font-weight: 700;
}
.off-stack.inline {
  opacity: 1;
}

.theme-strip {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-block: var(--space-3);
}

.theme-btn {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius);
  cursor: pointer;
  font: inherit;
}

.theme-btn.active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: white;
}
</style>
