<script setup lang="ts">
import type { Data as PlotlyDatum, Layout } from 'plotly.js'
import { computed, ref } from 'vue'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import { useJson } from '../composables/useJson'
import { useManifest } from '../composables/useManifest'
import { fmtInt, fmtNum, fmtShare } from '../format'
import { zoneLegend } from '../legends'
import { zonePalette } from '../palettes'
import type { CategoricalLegend } from '../types/legend'
import type { PcaCompare, PcaVariant, StackComposition } from '../types/data'

const { data: composition } = useJson<StackComposition>('json/stack_composition.json')
const { data: pca } = useJson<PcaCompare>('json/pca_compare.json')
const { manifest, zones, zoneVocation, themeLabel: themeName, bandLabel: bandName } = useManifest()

// Variant keys are semantic, never band counts — they must match the keys written by
// tools/build_dashboard_assets.py and they also name the pca_rgb_<key>.pmtiles raster.
// Keys spelling a count ('34'/'15') silently stopped matching when the stack went
// 34 -> 29 bands and ZONING_BANDS 15 -> 13; every count below is read from the data.
type VariantKey = 'full' | 'curated'

// Band-name prefix -> theme key: the naming convention of src/zoning._theme_of (and of
// build_stack_composition). Labels come from the manifest.
const PREFIX_THEME: Record<string, string> = { clim: 'climate', terr: 'terrain', soil: 'soil', water: 'water' }
const THEMES = computed(() =>
  Object.keys(composition.value?.themes ?? {}).map((theme) => ({
    prefix: Object.keys(PREFIX_THEME).find((p) => PREFIX_THEME[p] === theme) ?? theme,
    label: themeName(theme),
  })),
)
const themeLabel = (prefix: string) => themeName(PREFIX_THEME[prefix] ?? prefix)
const bandLabel = (band: string) => bandName(band)

const vFull = computed(() => pca.value?.variants.full ?? null)
const vCurated = computed(() => pca.value?.variants.curated ?? null)
const variant = (key: VariantKey) => (key === 'full' ? vFull.value : vCurated.value)
const nBands = (key: VariantKey) => variant(key)?.bands.length ?? null

const VARIANTS = computed<{ key: VariantKey; title: string }[]>(() => [
  { key: 'full', title: `Conjunto completo — ${nBands('full') ?? '—'} bandas` },
  { key: 'curated', title: `Subconjunto do zoneamento — ${nBands('curated') ?? '—'} bandas ponderadas` },
])

// --- 1. composition: the whole stack grouped by theme, the zoning bands highlighted ---
const bandGroups = computed(() => {
  const full = vFull.value
  const sub = vCurated.value
  if (!full || !sub) return []
  const weightOf = new Map(sub.bands.map((b, i) => [b, sub.weights[i]!]))
  return THEMES.value.map((t) => {
    const bands = full.bands.filter((b) => b.startsWith(`${t.prefix}_`))
    return {
      ...t,
      bands: bands.map((b) => ({ band: b, kept: weightOf.has(b) })),
      kept: bands.filter((b) => weightOf.has(b)).length,
      weight: weightOf.get(bands.find((b) => weightOf.has(b)) ?? ''),
    }
  })
})

// Share of a PC's (unit-norm) loading vector carried by each theme: Σ loading² per theme.
function themeShares(v: PcaVariant, j: number): { label: string; share: number }[] {
  const acc = new Map<string, number>()
  v.loadings.forEach((l, i) => acc.set(v.themes[i]!, (acc.get(v.themes[i]!) ?? 0) + l[j]! ** 2))
  return [...acc.entries()]
    .map(([prefix, share]) => ({ label: themeLabel(prefix), share }))
    .sort((a, b) => b.share - a.share)
}
const pct = (x: number | undefined, digits = 0) => fmtShare(x ?? 0, digits)
/** e.g. "clima 64%, solo 16%" — the themes that make up ≥80% of the PC. */
function pcThemes(key: VariantKey, j: number): string {
  const v = variant(key)
  if (!v) return ''
  const out: string[] = []
  let cum = 0
  for (const t of themeShares(v, j)) {
    if (cum >= 0.8) break
    out.push(`${t.label.toLowerCase()} ${pct(t.share)}`)
    cum += t.share
  }
  return out.join(', ')
}
const cum3 = (key: VariantKey) => variant(key)?.explained_variance_ratio.slice(0, 3).reduce((a, b) => a + b, 0)

// --- 2. explained variance ---------------------------------------------------------
const screeData = computed<PlotlyDatum[]>(() =>
  VARIANTS.value.flatMap(({ key }) => {
    const v = variant(key)
    if (!v) return []
    let cum = 0
    const y = v.explained_variance_ratio.map((r) => (cum += r * 100))
    return [{
      type: 'scatter',
      mode: 'lines+markers',
      name: `${v.bands.length} bandas (${varKeepPct.value} com ${v.n_pc_90} CPs)`,
      x: y.map((_, i) => i + 1),
      y,
    } as PlotlyDatum]
  }),
)
// The variance share the zoning PCA keeps (zoning.fit_pca's var_keep, via the manifest).
const varKeep = computed(() => manifest.value?.stack.pca_var_keep ?? null)
const varKeepPct = computed(() => fmtShare(varKeep.value ?? Number.NaN, 0))
const screeLayout = computed<Partial<Layout>>(() => ({
  height: 300,
  xaxis: { title: { text: 'número de componentes principais' } },
  yaxis: { title: { text: 'variância acumulada (%)' }, range: [0, 101] },
  shapes: varKeep.value === null
    ? []
    : [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 100 * varKeep.value, y1: 100 * varKeep.value, line: { dash: 'dot', color: '#5c6459' } }],
  legend: { orientation: 'h', y: -0.3 },
}))

// --- 3. PCA scatter ------------------------------------------------------------
const dims = ref<2 | 3>(2)
type ColorBy = 'zone' | 'terr_elev' | 'clim_aridity' | 'soil_clay'
const colorBy = ref<ColorBy>('zone')
const COLOR_OPTIONS: { key: ColorBy; label: string }[] = [
  { key: 'zone', label: 'Zona agroambiental' },
  { key: 'terr_elev', label: 'Elevação (m)' },
  { key: 'clim_aridity', label: 'Índice de aridez (P/ETP)' },
  { key: 'soil_clay', label: 'Teor de argila (%)' },
]

const zoneCount = computed(() => zones.value.length)
// Keyed by the 1-based zone id, like pca_compare.json's points.zone and the manifest.
const zoneLabels = computed<Record<number, string>>(() =>
  Object.fromEntries(zones.value.map((z) => [z.zone, zoneVocation(z.zone)])),
)
// Shared HTML legend under both panels — a Plotly legend per panel squeezes the plot.
const scatterZoneLegend = computed(() => zoneLegend(zoneCount.value, zoneLabels.value))
const fmtSil = (x: number | undefined) => fmtNum(x, 2)

function scatterData(key: VariantKey, showScale: boolean): PlotlyDatum[] {
  const pts = pca.value?.points
  if (!pts) return []
  const scores = key === 'full' ? pts.pc_full : pts.pc_curated
  const three = dims.value === 3
  const coords = (idx: number[]) => ({
    x: idx.map((i) => scores[i]![0]),
    y: idx.map((i) => scores[i]![1]),
    ...(three ? { z: idx.map((i) => scores[i]![2]) } : {}),
  })
  const base = { type: three ? 'scatter3d' : 'scattergl', mode: 'markers', hoverinfo: 'name' }
  const size = three ? 2 : 4

  if (colorBy.value === 'zone') {
    const colors = zonePalette(zoneCount.value || 1)
    // points.zone is 1-based; palette slot z-1 paints zone z (see legends.zoneLegend)
    return Array.from({ length: zoneCount.value }, (_, i) => {
      const z = i + 1
      const idx = pts.zone.flatMap((zz, j) => (zz === z ? [j] : []))
      return {
        ...base,
        ...coords(idx),
        name: `Zona ${z} — ${zoneLabels.value[z] ?? ''}`,
        showlegend: false,
        marker: { size, color: colors[i], opacity: 0.7 },
      } as PlotlyDatum
    })
  }
  const values = pts[colorBy.value]
  const idx = values.map((_, i) => i)
  return [{
    ...base,
    ...coords(idx),
    name: COLOR_OPTIONS.find((o) => o.key === colorBy.value)!.label,
    showlegend: false,
    marker: {
      size,
      color: values,
      colorscale: 'Viridis',
      opacity: 0.8,
      showscale: showScale,
      colorbar: { thickness: 10, len: 0.8 },
    },
  } as PlotlyDatum]
}

function pcTitle(key: VariantKey, j: number): string {
  const r = variant(key)?.explained_variance_ratio[j]
  return r === undefined ? `CP${j + 1}` : `CP${j + 1} (${fmtShare(r, 1)})`
}

function scatterLayout(key: VariantKey): Partial<Layout> {
  const common = { height: 400, margin: { t: 8, r: 8, b: 40, l: 48 } }
  if (dims.value === 3) {
    return {
      ...common,
      scene: {
        xaxis: { title: { text: pcTitle(key, 0) } },
        yaxis: { title: { text: pcTitle(key, 1) } },
        zaxis: { title: { text: pcTitle(key, 2) } },
      },
    }
  }
  return {
    ...common,
    xaxis: { title: { text: pcTitle(key, 0) }, zeroline: false },
    yaxis: { title: { text: pcTitle(key, 1) }, zeroline: false },
  }
}

// --- 4. RGB maps -----------------------------------------------------------------
function rgbLegend(key: VariantKey): CategoricalLegend {
  return {
    kind: 'categorical',
    title: 'Composição RGB dos componentes principais',
    items: [
      { label: `R = ${pcTitle(key, 0)} — ${pcThemes(key, 0)}`, color: '#e41a1c' },
      { label: `G = ${pcTitle(key, 1)} — ${pcThemes(key, 1)}`, color: '#4daf4a' },
      { label: `B = ${pcTitle(key, 2)} — ${pcThemes(key, 2)}`, color: '#377eb8' },
    ],
    caption: 'cada componente esticado entre os percentis 2 e 98 da amostra',
  }
}

// --- 5. loadings heatmap ---------------------------------------------------------
function loadingsData(key: VariantKey): PlotlyDatum[] {
  const v = variant(key)
  if (!v) return []
  return [{
    type: 'heatmap',
    x: [0, 1, 2].map((j) => pcTitle(key, j)),
    y: v.bands.map((b, i) => `${bandLabel(b)} · ${themeLabel(v.themes[i]!)}`),
    z: v.loadings,
    colorscale: 'RdBu',
    zmid: 0,
    zmin: -0.7,
    zmax: 0.7,
    colorbar: { thickness: 10, title: { text: 'carga' } },
    hovertemplate: '%{y}<br>%{x}: %{z:.2f}<extra></extra>',
  } as PlotlyDatum]
}
function loadingsLayout(key: VariantKey): Partial<Layout> {
  const n = variant(key)?.bands.length ?? 0
  return { height: 60 + n * 18, margin: { t: 8, r: 8, b: 40, l: 8 }, yaxis: { autorange: 'reversed', tickfont: { size: 10 } } }
}
</script>

<template>
  <section>
    <h1>Conjunto de {{ composition?.total_bands ?? nBands('full') }} bandas</h1>
    <p>
      Os {{ THEMES.length }} temas contínuos formam um único conjunto harmonizado na grade de
      {{ manifest?.grid_m ?? '…' }}&nbsp;m e padronizado por escore <em>z</em>. A cobertura da terra é
      deliberadamente excluída: serve apenas de máscara e contexto. O zoneamento, porém,
      <strong>não</strong> agrupa as {{ nBands('full') }} bandas: usa um subconjunto selecionado de
      {{ nBands('curated') }}, sem quase-duplicatas, com cada banda dividida por √(número de bandas
      do seu tema) e descorrelacionada por análise de componentes principais (ACP). Esta página
      compara os dois espaços.
    </p>

    <h2>Composição</h2>
    <div class="theme-grid">
      <div v-for="g in bandGroups" :key="g.prefix" class="theme-card">
        <p class="theme-head">
          <strong>{{ g.label }}</strong>
          <span class="muted">{{ g.kept }}/{{ g.bands.length }} no zoneamento<template v-if="g.weight"> · peso {{ fmtNum(g.weight, 2) }}</template></span>
        </p>
        <ul class="chips">
          <li v-for="b in g.bands" :key="b.band" :class="['chip', { kept: b.kept }]" :title="b.band">
            {{ bandLabel(b.band) }}
          </li>
        </ul>
      </div>
    </div>
    <p class="note">
      <span class="chip kept inline">destacadas</span> = as {{ nBands('curated') }} bandas do
      zoneamento.
      <template v-if="composition">{{ composition.note }}</template>
    </p>

    <template v-if="pca">
      <h2>Variância explicada</h2>
      <p>
        Nas {{ nBands('full') }} bandas, os dois primeiros componentes são dominados pelo clima
        (CP1: {{ pcThemes('full', 0) }}; CP2: {{ pcThemes('full', 1) }}): os
        {{ composition?.themes.climate ?? '…' }} índices climáticos, colineares entre si, pesam
        mais na distância euclidiana, embora o território seja quase uniforme em clima. São
        necessários <strong>{{ vFull?.n_pc_90 }} componentes</strong> para {{ varKeepPct }} da variância. No
        subconjunto ponderado bastam <strong>{{ vCurated?.n_pc_90 }}</strong>, e os três primeiros já
        somam {{ pct(cum3('curated')) }} (contra {{ pct(cum3('full')) }}), repartidos entre temas
        distintos (CP1: {{ pcThemes('curated', 0) }}; CP3: {{ pcThemes('curated', 2) }}).
      </p>
      <PlotlyChart :data="screeData" :layout="screeLayout" />

      <h2>Espaço dos componentes principais</h2>
      <p>
        {{ fmtInt(pca.points.zone.length) }} pixels da amostra estratificada
        (n = {{ fmtInt(pca.n_sample) }}, a mesma do zoneamento), projetados nos três primeiros
        componentes de cada espaço e coloridos pela zona agroambiental. A silhueta das zonas nos
        três primeiros componentes é {{ fmtSil(vCurated?.zone_silhouette_pc3) }} no espaço de
        {{ nBands('curated') }} bandas e {{ fmtSil(vFull?.zone_silhouette_pc3) }} no de
        {{ nBands('full') }}; valores próximos de zero indicam que, em média, um pixel está tão perto
        de outras zonas quanto da sua.
      </p>
      <div class="controls">
        <div class="mode-toggle" role="tablist">
          <button
            v-for="d in [2, 3] as const"
            :key="d"
            type="button"
            role="tab"
            :aria-selected="dims === d"
            :class="['mode-btn', { active: dims === d }]"
            @click="dims = d"
          >
            {{ d }}D
          </button>
        </div>
        <label>
          Cor:
          <select v-model="colorBy">
            <option v-for="o in COLOR_OPTIONS" :key="o.key" :value="o.key">{{ o.label }}</option>
          </select>
        </label>
      </div>
      <div class="pair">
        <figure v-for="(v, i) in VARIANTS" :key="v.key">
          <figcaption>{{ v.title }}</figcaption>
          <PlotlyChart :data="scatterData(v.key, i === 1)" :layout="scatterLayout(v.key)" />
        </figure>
      </div>
      <MapLegend v-if="colorBy === 'zone'" :spec="scatterZoneLegend" />

      <h2>Distribuição espacial</h2>
      <p>
        Os três primeiros componentes de cada espaço, calculados para todos os pixels de
        GO e DF e compostos em RGB. Cores parecidas indicam pixels próximos no espaço PCA.
        A legenda de cada mapa diz quais temas compõem cada canal.
      </p>
      <div class="pair">
        <figure v-for="v in VARIANTS" :key="v.key">
          <figcaption>{{ v.title }}</figcaption>
          <MapPanel :raster-path="`pca_rgb_${v.key}.pmtiles`" :raster-opacity="1">
            <template #legend><MapLegend :spec="rgbLegend(v.key)" /></template>
          </MapPanel>
        </figure>
      </div>

      <h2>Cargas dos componentes</h2>
      <p>
        Carga de cada banda nos três primeiros componentes, que define as cores do mapa acima
        (vermelho = CP1, verde = CP2, azul = CP3).
      </p>
      <div class="pair">
        <figure v-for="v in VARIANTS" :key="v.key">
          <figcaption>{{ v.title }}</figcaption>
          <PlotlyChart :data="loadingsData(v.key)" :layout="loadingsLayout(v.key)" />
        </figure>
      </div>
    </template>
  </section>
</template>

<style scoped>
.theme-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-3);
}

.theme-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: var(--space-2) var(--space-3);
}

.theme-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-1);
  margin: 0 0 var(--space-2);
}

.muted {
  color: var(--color-muted);
  font-size: 0.8rem;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.chip {
  padding: 1px 6px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  font-size: 0.75rem;
  color: var(--color-muted);
}

.chip.kept {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: white;
}

.chip.inline {
  display: inline-block;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-block: var(--space-3);
}

.mode-toggle {
  display: flex;
  gap: var(--space-2);
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

.pair {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr));
  gap: var(--space-3);
}

.pair figure {
  margin: 0;
  min-width: 0;
  overflow: hidden;
}

figcaption {
  font-weight: 600;
  font-size: 0.9rem;
  margin-bottom: var(--space-1);
}

.note {
  color: var(--color-muted);
  font-size: 0.875rem;
}
</style>
