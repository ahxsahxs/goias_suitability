<script setup lang="ts">
import { computed } from 'vue'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import StatChip from '../components/StatChip.vue'
import { useJson } from '../composables/useJson'
import { zoneLegend } from '../legends'
import type { HomeStats } from '../types/data'

const { data: stats, error, loading } = useJson<HomeStats>('json/home_stats.json')
const legend = computed(() => zoneLegend(stats.value?.n_zones ?? 10))
</script>

<template>
  <section>
    <h1>Viabilidade Agrícola de Goiás &amp; Zoneamento CMIP6</h1>
    <p>
      Um atlas a 250 m do potencial biofísico para sete segmentos de uso da terra em
      Goiás + DF (~340.000 km²), agrupados em zonas agroambientais. Pertinência fuzzy
      + pesos AHP nos moldes da FAO &rarr; viabilidade; agrupamento não supervisionado
      &rarr; zoneamento; fatores de mudança CMIP6 &rarr; a projeção futura.
    </p>

    <nav class="rq-cards">
      <RouterLink to="/zoning" class="rq-card">
        <strong>QP1</strong>
        <span>Zoneamento e segmentação</span>
      </RouterLink>
      <RouterLink to="/municipal" class="rq-card">
        <strong>QP2</strong>
        <span>Potencial vs. realizado</span>
      </RouterLink>
      <RouterLink to="/cmip6" class="rq-card">
        <strong>QP3</strong>
        <span>Projeção (mudança CMIP6)</span>
      </RouterLink>
    </nav>

    <MapPanel raster-path="zones_present.pmtiles">
      <template #legend><MapLegend :spec="legend" /></template>
    </MapPanel>

    <p v-if="loading">carregando estatísticas…</p>
    <p v-else-if="error" role="alert">Falha: {{ error.message }}</p>
    <div v-else-if="stats" class="stat-row">
      <StatChip label="zonas" :value="stats.n_zones" />
      <StatChip label="segmentos" :value="stats.n_segments" />
      <StatChip label="municípios" :value="stats.n_municipalities" />
      <StatChip label="viabilidade média — soja" :value="stats.mean_suit_soybean.toFixed(2)" />
      <StatChip
        label="maior zona"
        :value="`Z${stats.top_zone} (${stats.top_zone_share_pct}%)`"
      />
      <StatChip
        v-if="stats.underused_soybean_pct !== null"
        label="soja subutilizada"
        :value="`${stats.underused_soybean_pct}%`"
        hint="Viável (S1/S2), mas não cultivada atualmente com soja"
      />
      <StatChip
        v-if="stats.kappa_soybean !== null"
        label="κ floresta aleatória vs. conhecimento"
        :value="stats.kappa_soybean.toFixed(3)"
        hint="Kappa de Cohen, presença de soja — ver Validação para o painel completo"
      />
      <StatChip
        v-if="stats.auc_soybean !== null"
        label="AUC — soja"
        :value="stats.auc_soybean.toFixed(3)"
      />
    </div>
  </section>
</template>

<style scoped>
.rq-cards {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-block: var(--space-4);
}

.rq-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  text-decoration: none;
  color: var(--color-text);
  min-width: 160px;
}

.rq-card.disabled {
  color: var(--color-muted);
  cursor: default;
}

.stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-block: var(--space-4);
}
</style>
