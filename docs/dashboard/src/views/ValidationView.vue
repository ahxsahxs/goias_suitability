<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed } from 'vue'
import DataTable from '../components/DataTable.vue'
import type { DataTableColumn } from '../components/DataTable.vue'
import PlotlyChart from '../components/PlotlyChart.vue'
import { useJson } from '../composables/useJson'
import type { ValidationScorecard } from '../types/data'

const { data: scorecard } = useJson<ValidationScorecard>('json/validation_scorecard.json')

interface ScorecardRow {
  segment: string
  auc: number
  boyce: number
}
const scorecardRows = computed<ScorecardRow[]>(() => {
  const auc = scorecard.value?.presence_auc_boyce ?? {}
  return Object.entries(auc).map(([segment, v]) => ({ segment, auc: v.auc, boyce: v.boyce }))
})
const scorecardColumns: DataTableColumn<ScorecardRow>[] = [
  { key: 'segment', label: 'Segmento' },
  { key: 'auc', label: 'AUC', format: (r) => r.auc.toFixed(3) },
  { key: 'boyce', label: 'Índice de Boyce', format: (r) => r.boyce.toFixed(3) },
]

const spearmanData = computed<PlotlyDatum[]>(() => {
  const sp = scorecard.value?.spearman_npp ?? {}
  const segs = Object.keys(sp)
  return [{ type: 'bar', x: segs, y: segs.map((s) => sp[s] ?? 0) }]
})

const gppGradientData = computed<PlotlyDatum[]>(() => {
  const g = scorecard.value?.within_crop_gpp_gradient ?? {}
  const crops = Object.keys(g)
  return [{ type: 'bar', x: crops, y: crops.map((c) => g[c]?.rho ?? 0) }]
})

const kappa = computed(() => scorecard.value?.rf_kappa ?? null)
</script>

<template>
  <section>
    <h1>Validação</h1>
    <p>
      Quão confiável é o modelo? Discriminação de presença (AUC/Boyce), correlação de
      produtividade (Spearman vs. NPP/GPP do MOD17), separação entre zonas (ANOVA), e
      uma checagem cruzada orientada por dados com floresta aleatória (Parte 14).
    </p>

    <h2>Painel de discriminação de presença</h2>
    <DataTable v-if="scorecardRows.length" :columns="scorecardColumns" :rows="scorecardRows" />

    <h2>Correlação de Spearman vs. NPP anual do MOD17 (municipal, n=247)</h2>
    <PlotlyChart
      :data="spearmanData"
      :layout="{ height: 280, yaxis: { title: { text: 'rho de Spearman' }, range: [-0.5, 0.6] } }"
    />
    <p class="note">
      O NPP mede produtividade de biomassa em pé, não rendimento agronômico, por
      isso pecuária/conservação pontuam mais alto — reportado como contexto de
      produtividade, não como validador primário de cultura. Outras culturas anuais
      não é significativo (p=0,09).
    </p>

    <h2>Gradiente de GPP dentro da cultura (janela de dossel na estação de crescimento)</h2>
    <PlotlyChart
      :data="gppGradientData"
      :layout="{ height: 240, yaxis: { title: { text: 'rho de Spearman' } } }"
    />

    <h2>Checagem cruzada com floresta aleatória</h2>
    <div v-if="kappa" class="kappa-block">
      <p>
        Kappa de Cohen = <strong>{{ kappa.soybean.toFixed(3) }}</strong>
        (n={{ kappa.n.toLocaleString() }}) &mdash; {{ kappa.note }} na escala de Landis &amp; Koch.
      </p>
      <p>
        Isso não contradiz a AUC de soja de 0,871 acima &mdash; respondem perguntas
        diferentes. A AUC pergunta se pixels onde a soja é de fato plantada tendem a
        pontuar mais alto que pixels aleatórios (sim, de forma consistente). O kappa
        pergunta se as duas classificações concordam sobre <em>qual</em> terra marcar
        como viável: o mapa baseado em conhecimento marca
        <strong>{{ kappa.knowledge_area_pct }}%</strong> do território como viável ou
        melhor, enquanto o classificador de floresta aleatória atribui alta
        probabilidade de presença a apenas <strong>{{ kappa.rf_area_pct }}%</strong>.
        Quando duas áreas comparadas diferem tanto em tamanho, a fórmula do kappa
        desconta uma fatia maior da concordância como "acaso", puxando o escore
        abaixo do que a AUC isoladamente sugeriria &mdash; mesmo que o modelo ainda
        aponte, na maior parte, para os lugares certos.
      </p>
    </div>
  </section>
</template>

<style scoped>
.note {
  color: var(--color-muted);
  font-size: 0.875rem;
}

.kappa-block {
  max-width: 70ch;
}
</style>
