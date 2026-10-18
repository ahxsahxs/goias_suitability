<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed } from 'vue'
import DataTable from '../components/DataTable.vue'
import type { DataTableColumn } from '../components/DataTable.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import { useJson } from '../composables/useJson'
import { useManifest } from '../composables/useManifest'
import { fmtInt, fmtNum, fmtP, fmtPct, fmtSigned } from '../format'
import type { ValidationScorecard } from '../types/data'

const { data: scorecard } = useJson<ValidationScorecard>('json/validation_scorecard.json')
const { segmentKeys, segmentLabel, zoneName } = useManifest()

// Every metric is scored on ONE half of the spatial split (scorecard.half), the
// held-out one the thesis quotes. Order rows by the thesis' segment order.
const halfLabel = computed(() =>
  scorecard.value?.half === 'val' ? 'metade de validação' : scorecard.value?.half === 'calib' ? 'metade de calibração' : 'território inteiro',
)
const ordered = <T,>(rec: Record<string, T> | undefined) =>
  segmentKeys.value.filter((s) => rec && s in rec).map((s) => [s, rec![s]!] as const)

interface PresenceRow { segment: string; auc: number; boyce: number; presences: number | null }
const presenceRows = computed<PresenceRow[]>(() =>
  ordered(scorecard.value?.presence_auc_boyce).map(([segment, v]) => ({
    segment, auc: v.auc, boyce: v.boyce, presences: v.presences,
  })),
)
const presenceColumns: DataTableColumn<PresenceRow>[] = [
  { key: 'segment', label: 'Segmento', format: (r) => segmentLabel(r.segment) },
  { key: 'auc', label: 'AUC', format: (r) => fmtNum(r.auc, 3) },
  { key: 'boyce', label: 'Índice de Boyce', format: (r) => fmtNum(r.boyce, 3) },
  { key: 'presences', label: 'Presenças', format: (r) => fmtInt(r.presences) },
]
const weakestBoyce = computed(() => [...presenceRows.value].sort((a, b) => a.boyce - b.boyce)[0] ?? null)

const spearmanRows = computed(() =>
  ordered(scorecard.value?.spearman_npp)
    .map(([s, rho]) => ({ s, rho, p: scorecard.value?.spearman_npp_p?.[s] }))
    .sort((a, b) => b.rho - a.rho),
)
const spearmanData = computed<PlotlyDatum[]>(() => {
  const rows = spearmanRows.value
  return [{
    type: 'bar',
    x: rows.map((r) => segmentLabel(r.s)),
    y: rows.map((r) => r.rho),
    text: rows.map((r) => fmtSigned(r.rho, 2)),
    textposition: 'outside',
    hovertext: rows.map((r) => fmtP(r.p)),
    hoverinfo: 'x+text',
    marker: { color: rows.map((r) => (r.rho < 0 ? '#b2182b' : '#3f7d3a')) },
  }]
})
const spearmanRange = computed(() => {
  const v = spearmanRows.value.map((r) => r.rho)
  if (!v.length) return undefined
  return [Math.min(0, ...v) - 0.1, Math.max(0, ...v) + 0.1]
})
const allSignificant = computed(() => spearmanRows.value.every((r) => r.p !== undefined && r.p < 0.01))

const gppRows = computed(() => ordered(scorecard.value?.within_crop_gpp_gradient))
const gppData = computed<PlotlyDatum[]>(() => [{
  type: 'bar',
  x: gppRows.value.map(([s]) => segmentLabel(s)),
  y: gppRows.value.map(([, g]) => g.rho),
  text: gppRows.value.map(([, g]) => `${fmtSigned(g.rho, 3)} (n = ${fmtInt(g.n)})`),
  textposition: 'outside',
  hoverinfo: 'x+text',
  marker: { color: gppRows.value.map(([, g]) => (g.rho < 0 ? '#b2182b' : '#3f7d3a')) },
}])
const negativeGpp = computed(() => gppRows.value.filter(([, g]) => g.rho < 0).map(([s]) => segmentLabel(s).toLowerCase()))

const anova = computed(() => scorecard.value?.zone_anova ?? null)
const anovaData = computed<PlotlyDatum[]>(() => {
  const z = anova.value?.zones ?? []
  return [{
    type: 'bar',
    x: z.map((r) => `Zona ${r.zone}`),
    y: z.map((r) => r.mean_npp),
    text: z.map((r) => `${fmtNum(r.mean_npp, 3)} (n = ${fmtInt(r.n)})`),
    textposition: 'outside',
    hovertext: z.map((r) => zoneName(r.zone)),
    hoverinfo: 'x+text',
  }]
})

const kappa = computed(() => scorecard.value?.rf_kappa ?? null)
const soyAuc = computed(() => scorecard.value?.presence_auc_boyce.soybean?.auc ?? null)
</script>

<template>
  <section>
    <h1>Validação</h1>
    <p>
      A aptidão do presente é confrontada com o uso atual da terra (MapBiomas) e com a produtividade
      observada pelo MODIS MOD17. Todos os valores desta página são medidos na
      <strong>{{ halfLabel }}</strong> da partição espacial em blocos, isto é, em território que não
      participou da estimação de nenhum parâmetro do modelo.
    </p>

    <h2>Discriminação por presença</h2>
    <p class="note">
      A AUC mede se as células onde a cultura é plantada pontuam mais alto que as demais; o índice de
      Boyce, se a frequência de presenças cresce com a aptidão.
    </p>
    <DataTable v-if="presenceRows.length" :columns="presenceColumns" :rows="presenceRows" />
    <p v-if="weakestBoyce" class="note">
      O Boyce de {{ segmentLabel(weakestBoyce.segment).toLowerCase() }}
      ({{ fmtNum(weakestBoyce.boyce, 3) }}) deve ser lido com cautela: o segmento modela milho, algodão
      e sorgo, mas o MapBiomas não distingue milho nem sorgo, que ficam diluídos na classe de mosaico
      de culturas. É uma incompatibilidade entre o segmento e o seu validador, e não necessariamente
      um defeito do modelo. A piscicultura não tem validador de presença.
    </p>

    <h2>Correlação com a NPP anual do MOD17</h2>
    <p class="note">
      Correlação de Spearman entre a aptidão média municipal e a NPP média plurianual em terra
      cultivada e pastagem (n = {{ scorecard?.spearman_npp_n_municipalities ?? '—' }} municípios<template
        v-if="allSignificant">; todos os coeficientes com p &lt; 0,01</template>). A NPP mede a
      produtividade da biomassa, e não o rendimento agronômico; serve como <em>proxy</em> de contexto,
      e não como validador das culturas. A correlação negativa da piscicultura é esperada, já que a NPP
      descreve vegetação terrestre.
    </p>
    <PlotlyChart
      :data="spearmanData"
      :layout="{ height: 300, yaxis: { title: { text: 'ρ de Spearman' }, range: spearmanRange, zeroline: true } }"
    />

    <h2>Gradiente de GPP dentro da cultura</h2>
    <p class="note">
      Correlação de Spearman entre a aptidão e a GPP de outubro a março, apenas nas células onde cada
      cultura é de fato plantada: dentro dos plantios, a aptidão mais alta corresponde a maior
      produtividade?
      <template v-if="negativeGpp.length">
        O sinal negativo em {{ negativeGpp.join(' e ') }} contradiz o modelo; a explicação mais
        provável é um artefato do validador, pois a GPP do MODIS subestima a eficiência de uso da luz
        em lavouras intensamente manejadas.
      </template>
    </p>
    <PlotlyChart
      :data="gppData"
      :layout="{ height: 280, yaxis: { title: { text: 'ρ de Spearman' }, zeroline: true } }"
    />

    <h2>Produtividade por zona agroambiental</h2>
    <p v-if="anova" class="note">
      NPP média do MOD17 (unidades escalonadas) por zona. ANOVA de um fator:
      F = {{ fmtNum(anova.f, 1) }}, {{ fmtP(anova.p_approx) }}. As médias se ordenam com a
      altitude: o zoneamento capta um gradiente de produtividade observada, e não apenas um gradiente
      das variáveis de entrada.
    </p>
    <PlotlyChart :data="anovaData" :layout="{ height: 280, yaxis: { title: { text: 'NPP média' } } }" />

    <h2>Verificação cruzada orientada por dados</h2>
    <div v-if="kappa" class="kappa-block">
      <p>
        Uma floresta aleatória treinada na metade de calibração, com presença de soja e o conjunto
        completo de bandas, é comparada ao mapa baseado em conhecimento (classe S2 ou melhor) na
        {{ halfLabel }}: κ de Cohen = <strong>{{ fmtNum(kappa.soybean, 3) }}</strong>
        (n = {{ fmtInt(kappa.n) }}), {{ kappa.note }}.
      </p>
      <p>
        O valor não contradiz a AUC da soja ({{ fmtNum(soyAuc, 3) }}): as duas medidas respondem a
        perguntas diferentes. A AUC verifica se a soja é plantada onde a aptidão é mais alta; o κ
        verifica se as duas classificações marcam a <em>mesma</em> terra. O mapa baseado em
        conhecimento classifica {{ fmtPct(kappa.knowledge_area_pct) }} da terra como apta, enquanto a
        floresta aleatória atribui alta probabilidade de presença a apenas
        {{ fmtPct(kappa.rf_area_pct) }}. Quando as duas áreas diferem tanto, o κ máximo atingível cai,
        e o índice fica abaixo do que a AUC sugeriria. Um mapa descreve onde a terra é capaz; o outro,
        onde a soja é de fato plantada.
      </p>
    </div>
  </section>
</template>

<style scoped>
.note {
  color: var(--color-muted);
  font-size: 0.875rem;
  max-width: 80ch;
}

.kappa-block {
  max-width: 80ch;
}
</style>
