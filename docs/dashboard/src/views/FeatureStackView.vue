<script setup lang="ts">
import type { Data as PlotlyDatum, Layout } from 'plotly.js'
import { computed, ref } from 'vue'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import { useCsv } from '../composables/useCsv'
import { useJson } from '../composables/useJson'
import { zoneLegend } from '../legends'
import { zonePalette } from '../palettes'
import type { CategoricalLegend } from '../types/legend'
import type { PcaCompare, PcaVariant, SegmentsConfig, StackComposition, ZoneProfileRow } from '../types/data'

const { data: composition } = useJson<StackComposition>('json/stack_composition.json')
const { data: pca } = useJson<PcaCompare>('json/pca_compare.json')
const { data: segmentsCfg } = useJson<SegmentsConfig>('json/segments.json')
const { data: profiles } = useCsv<ZoneProfileRow>('csv/zone_profiles.csv')

type VariantKey = '34' | '15'
const VARIANTS: { key: VariantKey; title: string }[] = [
  { key: '34', title: 'Pilha completa — 34 bandas' },
  { key: '15', title: 'Subconjunto do zoneamento — 15 bandas ponderadas' },
]

// Band-name prefix -> theme label (same labels as FeatureThemesView).
const THEMES: { prefix: string; label: string }[] = [
  { prefix: 'clim', label: 'Clima' },
  { prefix: 'terr', label: 'Relevo' },
  { prefix: 'soil', label: 'Solo' },
  { prefix: 'water', label: 'Água' },
  { prefix: 'phen', label: 'Fenologia' },
  { prefix: 'access', label: 'Acesso a mercados' },
]
const themeLabel = (prefix: string) => THEMES.find((t) => t.prefix === prefix)?.label ?? prefix
const bandLabel = (band: string) => band.replace(/^[a-z]+_/, '')

const v34 = computed(() => pca.value?.variants['34'] ?? null)
const v15 = computed(() => pca.value?.variants['15'] ?? null)
const variant = (key: VariantKey) => (key === '34' ? v34.value : v15.value)

// --- 1. composition: 34 bands grouped by theme, the 15 zoning bands highlighted ---
const bandGroups = computed(() => {
  const full = v34.value
  const sub = v15.value
  if (!full || !sub) return []
  const weightOf = new Map(sub.bands.map((b, i) => [b, sub.weights[i]!]))
  return THEMES.map((t) => {
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
const pct = (x: number | undefined, digits = 0) => `${((x ?? 0) * 100).toFixed(digits)}%`
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
  VARIANTS.flatMap(({ key }) => {
    const v = variant(key)
    if (!v) return []
    let cum = 0
    const y = v.explained_variance_ratio.map((r) => (cum += r * 100))
    return [{
      type: 'scatter',
      mode: 'lines+markers',
      name: `${key} bandas (90% com ${v.n_pc_90} PCs)`,
      x: y.map((_, i) => i + 1),
      y,
    } as PlotlyDatum]
  }),
)
const screeLayout: Partial<Layout> = {
  height: 300,
  xaxis: { title: { text: 'nº de componentes principais' } },
  yaxis: { title: { text: 'variância acumulada (%)' }, range: [0, 101] },
  shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 90, y1: 90, line: { dash: 'dot', color: '#5c6459' } }],
  legend: { orientation: 'h', y: -0.3 },
}

// --- 3. PCA scatter ------------------------------------------------------------
const dims = ref<2 | 3>(2)
type ColorBy = 'zone' | 'terr_elev' | 'clim_aridity' | 'soil_clay'
const colorBy = ref<ColorBy>('zone')
const COLOR_OPTIONS: { key: ColorBy; label: string }[] = [
  { key: 'zone', label: 'Zona agroambiental' },
  { key: 'terr_elev', label: 'Altitude (m)' },
  { key: 'clim_aridity', label: 'Índice de aridez' },
  { key: 'soil_clay', label: 'Argila (%)' },
]

const zoneCount = computed(() => profiles.value?.length ?? 0)
const zoneLabels = computed<Record<number, string>>(() => {
  const segs = segmentsCfg.value?.segments ?? {}
  return Object.fromEntries(
    (profiles.value ?? []).map((p) => [p.zone, segs[p.comparative_segment]?.label ?? p.comparative_segment]),
  )
})
// Shared HTML legend under both panels — a Plotly legend per panel squeezes the plot.
const scatterZoneLegend = computed(() => zoneLegend(zoneCount.value, zoneLabels.value))
const fmtSil = (x: number | undefined) => (Math.abs(x ?? 0) < 0.005 ? '0,00' : (x ?? 0).toFixed(2).replace('.', ','))

function scatterData(key: VariantKey, showScale: boolean): PlotlyDatum[] {
  const pts = pca.value?.points
  if (!pts) return []
  const scores = key === '34' ? pts.pc34 : pts.pc15
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
    return Array.from({ length: zoneCount.value }, (_, z) => {
      const idx = pts.zone.flatMap((zz, i) => (zz === z ? [i] : []))
      return {
        ...base,
        ...coords(idx),
        name: `Zona ${z} — ${zoneLabels.value[z] ?? ''}`,
        showlegend: false,
        marker: { size, color: colors[z], opacity: 0.7 },
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
  return r === undefined ? `PC${j + 1}` : `PC${j + 1} (${(r * 100).toFixed(1)}%)`
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
    title: 'Composição RGB dos PCs',
    items: [
      { label: `R = ${pcTitle(key, 0)} — ${pcThemes(key, 0)}`, color: '#e41a1c' },
      { label: `G = ${pcTitle(key, 1)} — ${pcThemes(key, 1)}`, color: '#4daf4a' },
      { label: `B = ${pcTitle(key, 2)} — ${pcThemes(key, 2)}`, color: '#377eb8' },
    ],
    caption: 'cada PC esticado entre os percentis 2 e 98 da amostra',
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
  const n = variant(key)?.bands.length ?? 15
  return { height: 60 + n * 16, margin: { t: 8, r: 8, b: 40, l: 8 }, yaxis: { autorange: 'reversed', tickfont: { size: 10 } } }
}
</script>

<template>
  <section>
    <h1>Pilha de Atributos ({{ composition?.total_bands ?? 34 }} bandas)</h1>
    <p>
      Os seis temas contínuos formam uma única imagem harmonizada de 250 m (Parte 8),
      padronizada em z-score. A cobertura da terra é deliberadamente excluída — apenas
      máscara/contexto, nunca empilhada ou agrupada. O zoneamento (Parte 10), porém,
      <strong>não</strong> agrupa as 34 bandas: usa um subconjunto curado de 15, sem
      quase-duplicatas, com cada tema ponderado por 1/√(nº de bandas do tema) e
      descorrelacionado por PCA. Esta página compara os dois espaços.
    </p>

    <h2>Composição</h2>
    <div class="theme-grid">
      <div v-for="g in bandGroups" :key="g.prefix" class="theme-card">
        <p class="theme-head">
          <strong>{{ g.label }}</strong>
          <span class="muted">{{ g.kept }}/{{ g.bands.length }} no zoneamento<template v-if="g.weight"> · peso {{ g.weight.toFixed(2) }}</template></span>
        </p>
        <ul class="chips">
          <li v-for="b in g.bands" :key="b.band" :class="['chip', { kept: b.kept }]" :title="b.band">
            {{ bandLabel(b.band) }}
          </li>
        </ul>
      </div>
    </div>
    <p class="note">
      <span class="chip kept inline">destacadas</span> = as 15 bandas de <code>ZONING_BANDS</code>.
      <template v-if="composition">{{ composition.note }}</template>
    </p>

    <template v-if="pca">
      <h2>Variância explicada</h2>
      <p>
        Nas 34 bandas, os dois primeiros componentes são essencialmente climáticos
        (PC1: {{ pcThemes('34', 0) }}; PC2: {{ pcThemes('34', 1) }}) — os 14 índices
        climáticos colineares dominam a distância euclidiana, embora o território seja
        quase uniforme em clima. São precisos <strong>{{ v34?.n_pc_90 }} PCs</strong> para 90% da
        variância. No subconjunto ponderado, bastam <strong>{{ v15?.n_pc_90 }}</strong>, e os três
        primeiros já somam {{ pct(cum3('15')) }} (contra {{ pct(cum3('34')) }}), repartidos entre
        temas distintos (PC1: {{ pcThemes('15', 0) }}; PC3: {{ pcThemes('15', 2) }}).
      </p>
      <PlotlyChart :data="screeData" :layout="screeLayout" />

      <h2>Espaço PCA</h2>
      <p>
        {{ pca.points.zone.length.toLocaleString('pt-BR') }} pixels da amostra estratificada
        (n = {{ pca.n_sample.toLocaleString('pt-BR') }}, a mesma do zoneamento), projetados
        nos três primeiros componentes de cada espaço, coloridos pela zona final
        (<code>zones_present</code>). As zonas se separam no espaço de 15 bandas
        (silhueta em PC1–3 = {{ fmtSil(v15?.zone_silhouette_pc3) }}) e se sobrepõem no de 34
        (silhueta = {{ fmtSil(v34?.zone_silhouette_pc3) }}: em média, um pixel fica tão perto de
        outras zonas quanto da sua).
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
        GO+DF e compostos em RGB. Cores parecidas indicam pixels próximos no espaço PCA.
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
        Peso de cada banda em PC1–PC3 — é o que as cores do mapa acima significam
        (vermelho = PC1, verde = PC2, azul = PC3).
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
