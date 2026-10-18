<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import { useJson } from '../composables/useJson'
import { useManifest } from '../composables/useManifest'
import { fmtNum } from '../format'
import { continuousBandLegend } from '../legends'
import type { BandPercentiles } from '../types/data'

// One representative band per theme, from manifest.hero_bands (HERO_BANDS in
// tools/build_dashboard_assets.py). `stacked` = the theme is in features.STACK_THEMES;
// siting and conservation are side images routed straight into suitability.
const { manifest, themeLabel, bandLabel } = useManifest()
const themes = computed(() => manifest.value?.hero_bands ?? [])
const nStacked = computed(() => themes.value.filter((t) => t.stacked).length)

const route = useRoute()
const router = useRouter()

const selectedTheme = ref((route.params.theme as string) || 'climate')
watch(selectedTheme, (theme) => router.replace({ name: 'feature-themes', params: { theme } }))
watch(
  () => route.params.theme,
  (theme) => {
    if (typeof theme === 'string' && theme) selectedTheme.value = theme
  },
)

// Bookmarks to removed themes (/feature-themes/phenology, /access) must not silently
// render the first theme as though it were the requested one.
const match = computed(() => themes.value.find((t) => t.theme === selectedTheme.value) ?? null)
const unknownTheme = computed(() => themes.value.length > 0 && match.value === null)
const current = computed(() => match.value ?? themes.value[0] ?? null)

const { data: percentiles } = useJson<BandPercentiles>('json/band_percentiles.json')
const currentPercentiles = computed(() => (current.value ? percentiles.value?.[current.value.band] ?? null : null))

const legend = computed(() => {
  const p = currentPercentiles.value
  if (!current.value || !p) return null
  return continuousBandLegend(bandLabel(current.value.band), p.p5, p.p95)
})

const boxData = computed<PlotlyDatum[]>(() => {
  const p = currentPercentiles.value
  if (!p || !current.value) return []
  return [
    {
      type: 'box',
      name: '',
      q1: [p.p25],
      median: [p.p50],
      q3: [p.p75],
      lowerfence: [p.p5],
      upperfence: [p.p95],
      orientation: 'h',
      hoverinfo: 'x',
    } as PlotlyDatum,
  ]
})
</script>

<template>
  <section>
    <h1>Temas biofísicos</h1>
    <p>
      Os atributos de entrada são organizados por tema e harmonizados na grade de análise. Os
      {{ nStacked }} temas contínuos (clima, terreno, solo e água) formam o conjunto padronizado de
      {{ manifest?.stack.total_bands ?? '…' }} bandas; as imagens laterais de localização e de
      conservação (marcadas com <span class="off-stack inline">∘</span>) entram apenas na aptidão
      dos segmentos que as usam, nunca no agrupamento. A cobertura da terra é usada somente como
      máscara e contexto.
    </p>

    <p v-if="unknownTheme" class="note unknown">
      O tema <code>{{ selectedTheme }}</code> não existe. Fenologia da vegetação e acessibilidade a
      mercados foram removidas do modelo, por medirem o resultado do uso e não a capacidade do
      lugar. Abaixo está <strong>{{ current ? themeLabel(current.theme) : '' }}</strong>, não o tema
      pedido.
    </p>

    <div class="theme-strip">
      <button
        v-for="t in themes"
        :key="t.theme"
        type="button"
        :class="['theme-btn', { active: t.theme === current?.theme }]"
        :title="t.stacked ? 'no conjunto de bandas' : 'imagem lateral, fora do conjunto de bandas'"
        @click="selectedTheme = t.theme"
      >
        {{ themeLabel(t.theme) }}<span v-if="!t.stacked" class="off-stack">&nbsp;∘</span>
      </button>
    </div>

    <template v-if="current">
      <p class="note">Banda representativa: <strong>{{ bandLabel(current.band) }}</strong>.</p>
      <MapPanel :raster-path="`feat_${current.band}.pmtiles`">
        <template #legend><MapLegend v-if="legend" :spec="legend" /></template>
      </MapPanel>

      <h2>Distribuição no território</h2>
      <p v-if="currentPercentiles" class="note">
        Mediana {{ fmtNum(currentPercentiles.p50, 2) }}; intervalo interquartil
        {{ fmtNum(currentPercentiles.p25, 2) }} a {{ fmtNum(currentPercentiles.p75, 2) }}; bigodes nos
        percentis 5 e 95.
      </p>
      <PlotlyChart
        :data="boxData"
        :layout="{ height: 160, xaxis: { title: { text: bandLabel(current.band) } } }"
      />
    </template>
  </section>
</template>

<style scoped>
/* Same convention as ValidationView/FeatureStackView: `.note` is defined per view,
   there is no global rule for it. */
.note {
  color: var(--color-muted);
  font-size: 0.875rem;
  max-width: 70ch;
}

/* Shown only when the route names a theme that does not exist, so the page never
   presents Clima as if it were the theme the viewer asked for. */
.note.unknown {
  color: var(--color-text);
  border-left: 3px solid var(--color-border);
  padding-inline-start: var(--space-3);
}

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
